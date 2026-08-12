"""Read-only CLI tool wrappers exposed to the investigator agent.

Hard safety rule: every command run here must be a read/describe/list/logs
style command. Anything that could mutate cloud state is rejected before
it ever reaches subprocess, regardless of what the model asked for.

These are plain Python callables decorated with @tool (LangChain) so they
can be bound directly to the LLM for tool-calling.
"""
from __future__ import annotations

import shlex
import subprocess

from langchain_core.tools import tool

# Verbs considered safe (read-only) per CLI. This is a denylist-of-the-gaps
# approach inverted into an allowlist: if the subcommand isn't recognisably
# read-only, we refuse to run it.
_ALLOWED_AWS_VERBS = {"describe", "list", "get", "logs", "sts"}
_ALLOWED_GCLOUD_VERBS = {"describe", "list", "logging"}
_ALLOWED_KUBECTL_VERBS = {"get", "describe", "logs", "top"}
_ALLOWED_GH_VERBS = {"run", "pr", "repo", "workflow"}  # read-only subflags enforced below


class ToolExecutionError(Exception):
    """Raised when a command is rejected or fails."""


def _run(command: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise ToolExecutionError(f"CLI not found: {command[0]}. Is it installed and on PATH?") from e
    except subprocess.TimeoutExpired as e:
        raise ToolExecutionError(f"Command timed out after {timeout}s: {' '.join(command)}") from e

    if result.returncode != 0:
        raise ToolExecutionError(
            f"Command failed (exit {result.returncode}): {' '.join(command)}\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _guard_readonly(cli: str, args: list[str], allowed_verbs: set[str]) -> None:
    if not args:
        raise ToolExecutionError(f"No subcommand supplied for {cli}.")
    verb = args[0].lower()
    if verb not in allowed_verbs and not any(v in verb for v in allowed_verbs):
        raise ToolExecutionError(
            f"Refusing to run '{cli} {verb}' — only read-only verbs {sorted(allowed_verbs)} are permitted."
        )
    write_flags = {"--force", "-y", "--yes", "--no-input"}
    if any(flag in args for flag in write_flags):
        raise ToolExecutionError(f"Refusing to run '{cli} {' '.join(args)}' — write-style flag detected.")


def _safe_invoke(cli: str, command_args: str, allowed_verbs: set[str]) -> str:
    """Run a guarded read-only CLI command, returning errors as text instead
    of raising — so the agent sees "ERROR: ..." as tool output and can adapt
    (try another tool, note the CLI isn't installed, etc.) instead of the
    whole investigation crashing."""
    try:
        parsed = shlex.split(command_args)
        _guard_readonly(cli, parsed, allowed_verbs)
        return _run([cli, *parsed])
    except ToolExecutionError as e:
        return f"ERROR: {e}"


@tool("aws_cli")
def aws_cli(command_args: str) -> str:
    """Run a READ-ONLY aws CLI command. `command_args` is the full argument
    string after `aws`, e.g. "ecs describe-services --cluster prod --services my-svc".
    Only describe/list/get/logs/sts subcommands are permitted."""
    return _safe_invoke("aws", command_args, _ALLOWED_AWS_VERBS)


@tool("gcloud_cli")
def gcloud_cli(command_args: str) -> str:
    """Run a READ-ONLY gcloud CLI command. `command_args` is the full argument
    string after `gcloud`, e.g. "run services describe my-svc --region us-central1".
    Only describe/list/logging subcommands are permitted."""
    return _safe_invoke("gcloud", command_args, _ALLOWED_GCLOUD_VERBS)


@tool("kubectl_cli")
def kubectl_cli(command_args: str) -> str:
    """Run a READ-ONLY kubectl command. `command_args` is the full argument
    string after `kubectl`, e.g. "get pods -n prod". Only get/describe/logs/top
    subcommands are permitted."""
    return _safe_invoke("kubectl", command_args, _ALLOWED_KUBECTL_VERBS)


@tool("gh_cli")
def gh_cli(command_args: str) -> str:
    """Run a READ-ONLY gh (GitHub) CLI command, for CI run history, recent
    commits, and deployment events. `command_args` is the full argument
    string after `gh`, e.g. "run list --limit 10"."""
    return _safe_invoke("gh", command_args, _ALLOWED_GH_VERBS)

READ_ONLY_TOOLS = [aws_cli, gcloud_cli, kubectl_cli, gh_cli]
