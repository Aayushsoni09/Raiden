"""Executor for both predefined runbooks and (opt-in, per-project) LLM-drafted
free-form commands. In both paths, no command reaches subprocess without an
explicit confirm() call by the human operator, and a fixed set of
hardcoded-forbidden verbs/binaries/IAM commands can never be bypassed by
catalog configuration.
"""

import subprocess
from pathlib import Path

import yaml
from jsonschema import ValidationError as SchemaValidationError
from jsonschema import validate as validate_schema

from scripts._shell import resolve
from src.audit import AuditLog

FORBIDDEN_RUNBOOKS = {"any_delete", "iam_modify"}

# Best-effort, non-exhaustive: substrings of destructive verbs across
# aws/gcloud/kubectl subcommands, checked against the full rendered command.
# This is the only backstop once free-form commands are allowed, so treat it
# as defense-in-depth rather than a guarantee — review every proposed
# command yourself before confirming.
FORBIDDEN_COMMAND_SUBSTRINGS = [
    "terraform apply", "terraform destroy",
    "delete", "terminate", "destroy", "remove", "deregister", "detach", "revoke",
]

# Free-form mode may only invoke these CLIs — never an arbitrary binary
# (bash, rm, curl, python, ...).
ALLOWED_FREE_FORM_BINARIES = {"aws", "gcloud", "kubectl", "gh"}


class RunbookNotAllowedError(Exception):
    pass


def _check_forbidden_command(command, label):
    rendered = " ".join(command).lower()
    for forbidden in FORBIDDEN_COMMAND_SUBSTRINGS:
        if forbidden in rendered:
            raise RunbookNotAllowedError(f"{label} contains forbidden operation '{forbidden}'")
    if any(tok.lower() == "iam" for tok in command):
        raise RunbookNotAllowedError(f"{label} invokes 'iam' — IAM commands are hardcoded off")


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
        _check_forbidden_command(command, f"'{runbook_id}'")

        self.audit.record(
            "runbook_proposed",
            runbook_id=runbook_id,
            project=catalog_entry["id"],
            command=command,
        )
        return command, runbook.get("requires_confirmation", True)

    def validate_free_form(self, command, catalog_entry):
        """Gate an LLM-drafted command before it's shown to the human for
        confirmation. Returns the command unchanged if it passes."""
        if not catalog_entry.get("free_form_actions_allowed", False):
            raise RunbookNotAllowedError(
                f"free-form actions are not enabled for '{catalog_entry['id']}' "
                "(set free_form_actions_allowed: true in its catalog entry)"
            )
        if not command:
            raise ValueError("command is empty")

        binary = command[0].lower()
        if binary not in ALLOWED_FREE_FORM_BINARIES:
            raise RunbookNotAllowedError(
                f"'{binary}' is not in the allowed free-form binaries {sorted(ALLOWED_FREE_FORM_BINARIES)}"
            )
        _check_forbidden_command(command, "command")

        self.audit.record(
            "free_form_proposed",
            project=catalog_entry["id"],
            command=command,
        )
        return command

    def execute(self, command, confirmed):
        if not confirmed:
            raise PermissionError("Execution requires explicit confirmation")

        resolved_command = [resolve(command[0]), *command[1:]]
        result = subprocess.run(resolved_command, capture_output=True, text=True, timeout=60)
        self.audit.record(
            "command_executed",
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return result
