"""LLM-drafted infrastructure commands, for explicit human review before execution.

This is Raiden's opt-in "full DevOps agent" mode: instead of only running
predefined runbooks, the LLM can propose an arbitrary CLI command for a
request like "make an instance in ap-south-1". Proposing is all this
module does — it never executes anything. src/executor/executor.py's
validate_free_form()/execute() still require explicit human confirmation,
and hardcoded-forbidden verbs/binaries/IAM commands still apply regardless
of what gets proposed here.

Because a local model can't look up real values (AMI ids, VPC ids, etc.),
always review/edit the proposed command before confirming it.
"""

import json
import re

from langchain_ollama import ChatOllama

DEFAULT_MODEL = "qwen2.5:7b"

ACTION_PROMPT = """You are Raiden, a DevOps assistant that drafts a single CLI command \
to fulfill an infrastructure request. You only draft commands for a human to review — \
you never execute anything yourself.

Allowed CLIs: aws, gcloud, kubectl, gh.
You must NEVER propose a command that deletes, terminates, destroys, removes, \
deregisters, detaches, or revokes any resource, and NEVER propose any `iam`/IAM-related \
command. Those are hardcoded off regardless of what you propose.

Project context:
{project_context}

Request: {request}

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"command": ["<argv0>", "<argv1>", ...], "explanation": "<one sentence>"}}

The "command" must be a list of argv tokens (not a shell string) for exactly one of the \
allowed CLIs above. Use the project's region/account context above where relevant. If \
you don't have enough information to draft a safe, specific command, set "command" to \
an empty list and explain what's missing in "explanation".
"""


class ActionProposalError(Exception):
    pass


def _project_context(catalog_entry):
    lines = [f"id: {catalog_entry['id']}"]
    for cloud in catalog_entry.get("clouds", []):
        lines.append(f"- provider={cloud.get('provider')} regions={cloud.get('regions')}")
    return "\n".join(lines)


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ActionProposalError(f"Model did not return a JSON object: {text!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ActionProposalError(f"Model returned invalid JSON: {text!r}") from e


def propose_action(request, catalog_entry, model=DEFAULT_MODEL):
    """Returns (command: list[str], explanation: str). command may be empty
    if the model didn't have enough information to propose something safe."""
    llm = ChatOllama(model=model, temperature=0)
    prompt = ACTION_PROMPT.format(
        project_context=_project_context(catalog_entry),
        request=request,
    )
    response = llm.invoke(prompt)
    data = _extract_json(response.content)

    command = data.get("command", [])
    if not isinstance(command, list) or not all(isinstance(tok, str) for tok in command):
        raise ActionProposalError(f"Model's 'command' field was not a list of strings: {command!r}")

    return command, data.get("explanation", "")
