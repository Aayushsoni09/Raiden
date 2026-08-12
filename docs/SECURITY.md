# Security Policy

## Reporting a vulnerability

This is a POC repo; if you find a security issue (e.g. a way for the
executor to run an unapproved command, or a runbook that bypasses the
hardcoded-forbidden list), please open a private security advisory on
GitHub rather than a public issue.

## Scope

See `docs/THREAT_MODEL.md` for what's in/out of scope for this POC.

## Non-negotiables

- The executor (`src/executor/`) must never accept free-form shell
  commands from the LLM — only `(runbook_id, params)`.
- `any_delete`, `iam_modify`, and any `terraform apply`/`destroy`
  command are hardcoded-forbidden and must remain so regardless of
  catalog configuration.
- `llm_egress_approved` must default to `false` for every new catalog
  entry.
