"""Runbook runner.

Loads YAML-defined, parameterised runbooks from runbooks/ and executes
them via subprocess — nothing else. The LLM never gets to construct the
shell command; it can only propose a runbook name + params, which are
validated against the runbook's own JSON-Schema-style `params` block and
against the catalog entry's allow/deny lists before anything runs.

Hardcoded, non-overridable rule: `any_delete` and `iam_modify` runbook
names are always rejected, and `terraform apply` is never invoked from
here at all (no runbook may shell out to `terraform apply` — enforced
in scripts/lint_runbooks.py at CI time too).
"""
from __future__ import annotations

import glob
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

import yaml
from jsonschema import validate as jsonschema_validate
from jsonschema import ValidationError

from src.audit import AuditLogger
from src.resolver import CatalogEntry

HARDCODED_FORBIDDEN = {"any_delete", "iam_modify"}
FORBIDDEN_COMMAND_SUBSTRINGS = ["terraform apply", "terraform destroy"]

ConfirmCallback = Callable[[str], bool]


class RunbookError(Exception):
    pass


class RunbookNotFoundError(RunbookError):
    def __init__(self, name: str):
        super().__init__(f"No runbook named '{name}' found under runbooks/.")


class RunbookNotAllowedError(RunbookError):
    def __init__(self, name: str, project: str):
        super().__init__(f"Runbook '{name}' is not allowed for project '{project}'.")


class RunbookValidationError(RunbookError):
    pass


@dataclass
class RunbookDefinition:
    name: str
    description: str
    command_template: list[str]
    params_schema: dict[str, Any]
    confirm_message_template: str
    source_path: str

    @classmethod
    def from_file(cls, path: str) -> "RunbookDefinition":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        name = data["name"]
        command_template = data["command"]
        full_command = " ".join(command_template)
        for forbidden in FORBIDDEN_COMMAND_SUBSTRINGS:
            if forbidden in full_command:
                raise RunbookValidationError(
                    f"Runbook '{name}' contains forbidden command '{forbidden}' — refusing to load."
                )
        return cls(
            name=name,
            description=data.get("description", ""),
            command_template=command_template,
            params_schema=data.get("params", {"type": "object", "properties": {}}),
            confirm_message_template=data.get("confirm_message", f"Run runbook '{name}'?"),
            source_path=path,
        )


class RunbookRunner:
    def __init__(self, runbooks_dir: str = "runbooks", audit_logger: AuditLogger | None = None):
        self.runbooks_dir = runbooks_dir
        self.audit = audit_logger or AuditLogger()
        self._definitions: dict[str, RunbookDefinition] = {}
        self.reload()

    def reload(self) -> None:
        self._definitions = {}
        for path in sorted(glob.glob(os.path.join(self.runbooks_dir, "*.yaml"))):
            definition = RunbookDefinition.from_file(path)
            self._definitions[definition.name] = definition

    def get(self, name: str) -> RunbookDefinition:
        if name not in self._definitions:
            raise RunbookNotFoundError(name)
        return self._definitions[name]

    def run(
        self,
        name: str,
        params: dict[str, Any],
        catalog_entry: CatalogEntry,
        confirm: ConfirmCallback,
    ) -> str:
        """Validate, confirm, then execute a runbook. Returns command stdout.

        `confirm` is called with a human-readable summary and must return
        True for execution to proceed — this is the "always asks first"
        gate for anything that mutates production.
        """
        if name in HARDCODED_FORBIDDEN:
            raise RunbookNotAllowedError(name, catalog_entry.id)

        if not catalog_entry.is_runbook_allowed(name):
            self.audit.log("runbook.rejected", project=catalog_entry.id, runbook=name, reason="not_allowed")
            raise RunbookNotAllowedError(name, catalog_entry.id)

        definition = self.get(name)

        try:
            jsonschema_validate(instance=params, schema=definition.params_schema)
        except ValidationError as e:
            raise RunbookValidationError(f"Invalid params for runbook '{name}': {e.message}") from e

        command = [part.format(**params) for part in definition.command_template]
        confirm_message = definition.confirm_message_template.format(**params)

        self.audit.log(
            "approval.request",
            project=catalog_entry.id,
            runbook=name,
            params=params,
            command=" ".join(shlex.quote(c) for c in command),
        )

        approved = confirm(confirm_message)
        self.audit.log("approval.decision", project=catalog_entry.id, runbook=name, approved=approved)

        if not approved:
            raise RunbookError(f"Runbook '{name}' was not approved by the user.")

        self.audit.log("runbook.execute", project=catalog_entry.id, runbook=name, command=command)
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        self.audit.log(
            "runbook.result",
            project=catalog_entry.id,
            runbook=name,
            returncode=result.returncode,
            stdout=result.stdout[-4000:],
            stderr=result.stderr[-4000:],
        )
        if result.returncode != 0:
            raise RunbookError(f"Runbook '{name}' failed (exit {result.returncode}): {result.stderr.strip()}")
        return result.stdout.strip()

