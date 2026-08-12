"""Runbook executor. Accepts only structured, parameterised runbook intents —
never free-form shell commands from the model. Every run requires an explicit
confirm() call by the human operator before the command is executed.
"""

import subprocess
from pathlib import Path

import yaml
from jsonschema import ValidationError as SchemaValidationError
from jsonschema import validate as validate_schema

from scripts._shell import resolve
from src.audit import AuditLog

FORBIDDEN_RUNBOOKS = {"any_delete", "iam_modify"}
FORBIDDEN_COMMAND_SUBSTRINGS = ["terraform apply", "terraform destroy"]


class RunbookNotAllowedError(Exception):
    pass


class RunbookExecutor:
    def __init__(self, runbooks_dir="runbooks", audit_log_path="audit/session.jsonl"):
        self.runbooks_dir = Path(runbooks_dir)
        self.audit = AuditLog(audit_log_path)

    def _load_runbook(self, runbook_id):
        path = self.runbooks_dir / f"{runbook_id}.yaml"
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def propose(self, runbook_id, params, catalog_entry):
        if runbook_id in FORBIDDEN_RUNBOOKS:
            raise RunbookNotAllowedError(f"'{runbook_id}' is hardcoded off")

        allowed = set(catalog_entry.get("runbooks_allowed", []))
        if runbook_id not in allowed:
            raise RunbookNotAllowedError(
                f"'{runbook_id}' is not in runbooks_allowed for {catalog_entry['id']}"
            )

        runbook = self._load_runbook(runbook_id)

        try:
            validate_schema(instance=params, schema=runbook["params"])
        except SchemaValidationError as e:
            raise ValueError(f"Invalid params for '{runbook_id}': {e.message}") from e

        command = [part.format(**params) for part in runbook["command"]]

        rendered = " ".join(command)
        for forbidden in FORBIDDEN_COMMAND_SUBSTRINGS:
            if forbidden in rendered:
                raise RunbookNotAllowedError(
                    f"'{runbook_id}' command contains forbidden operation '{forbidden}'"
                )

        self.audit.record(
            "runbook_proposed",
            runbook_id=runbook_id,
            project=catalog_entry["id"],
            command=command,
        )
        return command, runbook.get("requires_confirmation", True)

    def execute(self, command, confirmed):
        if not confirmed:
            raise PermissionError("Runbook execution requires explicit confirmation")

        resolved_command = [resolve(command[0]), *command[1:]]
        result = subprocess.run(resolved_command, capture_output=True, text=True, timeout=60)
        self.audit.record(
            "runbook_executed",
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return result
