# Threat model

Status: draft — expand as capabilities are added. Update whenever a PR
adds a new capability that touches a write path (executor, runbooks).

## Trust boundaries

1. **Investigator (LLM process)** — read-only. Holds no write credentials.
   Runs locally via Ollama; no data leaves the machine unless
   `llm_egress_approved: true` is set for the project *and* you've
   switched to a remote model provider (not done by default in this POC).
2. **Executor** — the only component that can mutate cloud state. Accepts
   only `(runbook_id, params)` tuples, never free-form shell text from
   the model. Every run requires an explicit human confirmation.
3. **Catalog** — git-backed, human-reviewed (CODEOWNERS on `_schema.yaml`).
   Determines which runbooks are even reachable per project.
4. **Audit log** — append-only local JSONL. Not a security control by
   itself (local files can be deleted), but supports post-incident review
   and is required reading before disputing "what did Raiden do".

## Key risks and mitigations (POC scope)

| Risk | Mitigation |
|---|---|
| LLM hallucinates a destructive command | Executor only accepts predefined runbook ids + schema-validated params; no shell string ever reaches subprocess from the LLM directly. |
| LLM tries a write-capable CLI verb via investigator tools | `src/investigator/tools.py` only defines read functions (describe/list/logs) per CLI; there is no code path for the investigator to invoke a write verb. |
| Wrong project's resources get touched | Resolver never guesses on ambiguous matches — raises `AmbiguousProjectError` instead of picking one. |
| A runbook is quietly upgraded to do something destructive | CI (`lint_runbooks.py`) rejects `terraform apply/destroy` substrings and hardcoded-forbidden ids (`any_delete`, `iam_modify`) at lint time; `executor.py` re-checks the rendered command at propose time. |
| Client data leaves their environment via the LLM | `llm_egress_approved` defaults to `false` on every catalog entry; local Ollama model means this is moot until you deliberately swap to a hosted model. |
| Credentials committed to the repo | `catalog/*.yaml` (except schema/examples) and `.env`/`*.pem`/`*.key`/`credentials/` are gitignored; CI runs `bandit` on `src/`. |

## Out of scope for this POC

- Multi-tenant credential isolation (assumes operator's local CLI auth is
  already scoped correctly per account).
- Sandboxing subprocess execution (relies on OS-level user permissions).
- Remote/hosted LLM support (not wired up; would need explicit design for
  egress approval enforcement before being added).
