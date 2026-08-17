# Security Policy

## Reporting a vulnerability

This is a POC repo; if you find a security issue (e.g. a way for the
executor to run an unapproved command, a runbook or free-form action that
bypasses the hardcoded-forbidden list, or a proposed command that executes
without confirmation), please open a private security advisory on GitHub
rather than a public issue.

## Scope

See `docs/THREAT_MODEL.md` for what's in/out of scope for this POC,
including the "Free-form action mode" section describing the trust
boundary of LLM-drafted commands.

## Non-negotiables

- The executor (`src/executor/`) must never run a command — runbook or
  free-form — without an explicit human confirmation step.
- `any_delete`, `iam_modify`, any `terraform apply`/`destroy` command, and
  (in free-form mode) any command containing `delete`/`terminate`/
  `destroy`/`remove`/`deregister`/`detach`/`revoke` or invoking `iam` are
  hardcoded-forbidden and must remain so regardless of catalog
  configuration or human edits to a proposed command.
- Free-form mode (`src/investigator/action_proposer.py`) may only invoke
  `aws`, `gcloud`, `kubectl`, or `gh` — never an arbitrary binary.
- `llm_egress_approved` and `free_form_actions_allowed` must both default
  to `false` for every new catalog entry.
