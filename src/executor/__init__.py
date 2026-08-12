"""src/executor — runs approved, structured runbook intents.

This is the only part of Raiden allowed to mutate cloud state. It never
accepts free-form shell commands from the LLM — only a runbook name plus
validated parameters. Every invocation requires an explicit confirmation
callback to return True before anything runs.
"""
from .executor import (
    RunbookRunner,
    RunbookError,
    RunbookNotAllowedError,
    RunbookValidationError,
    RunbookNotFoundError,
)

__all__ = [
    "RunbookRunner",
    "RunbookError",
    "RunbookNotAllowedError",
    "RunbookValidationError",
    "RunbookNotFoundError",
]

