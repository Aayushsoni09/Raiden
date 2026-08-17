# Threat model

Status: draft — expand as capabilities are added. Update whenever a PR
adds a new capability that touches a write path (executor, runbooks,
action proposer).

## Trust boundaries

1. **Investigator (LLM process)** — read-only. Holds no write credentials.
   Runs locally via Ollama; no data leaves the machine unless
   `llm_egress_approved: true` is set for the project *and* you've
   switched to a remote model provider (not done by default in this POC).
2. **Executor** — the only component that can mutate cloud state. In its
   default (runbook) mode it accepts only `(runbook_id, params)` tuples,
   never free-form shell text from the model. Per-project opt-in
   (`free_form_actions_allowed: true`) additionally allows an LLM-drafted
   command through `validate_free_form()` — see "Free-form action mode"
   below for what changes and what still doesn't. In both modes, every
   run requires an explicit human confirmation before subprocess ever
   executes anything.
3. **Catalog** — git-backed, human-reviewed (CODEOWNERS on `_schema.yaml`).
   Determines which runbooks — and whether free-form actions at all — are
   reachable per project.
4. **Audit log** — append-only local JSONL. Not a security control by
   itself (local files can be deleted), but supports post-incident review
   and is required reading before disputing "what did Raiden do".

## Free-form action mode (opt-in, per project)

`src/investigator/action_proposer.py` lets the LLM draft an arbitrary
`aws`/`gcloud`/`kubectl`/`gh` command from a natural-language request
(e.g. "make an instance in ap-south-1"), for a human to review and
confirm. This is a materially larger trust boundary than the runbook-only
model: the LLM is now authoring the actual command that may run, not
just filling in parameters for a human-reviewed template. What still
holds regardless of this mode:

- **Per-project opt-in, default off.** `free_form_actions_allowed` must
  be explicitly `true` in a catalog entry; every new entry defaults to
  `false`.
- **Binary allowlist.** Only `aws`, `gcloud`, `kubectl`, `gh` can be
  invoked — never an arbitrary shell, script interpreter, or other
  binary, regardless of what the model proposes.
- **Hardcoded-forbidden verbs and IAM stay absolute.** Any command
  containing `delete`/`terminate`/`destroy`/`remove`/`deregister`/
  `detach`/`revoke` as a substring, or invoking `iam` as a subcommand, is
  rejected by `RunbookExecutor.validate_free_form()` — even if the model
  proposed it and even after a human edits the command in the frontend's
  review step. This was verified directly: asking the model to "make an
  admin user" produced an `aws iam create-user` proposal, and clicking
  confirm on it in the frontend still raised `RunbookNotAllowedError`
  rather than executing.
- **Review-before-confirm, with editing.** A local model cannot look up
  real AMI/VPC/subnet ids, current pricing, or account-specific defaults
  — in testing, a request for an EC2 instance in a named region correctly
  identified the instance type and role but omitted the `--region` flag
  entirely and invented a plausible-looking but unverified AMI id. The
  frontend's Act mode shows the exact command and lets you edit it before
  confirming; treat every free-form proposal as a first draft, not a
  ready-to-run command.

This is a best-effort, non-exhaustive safety net, not a guarantee — the
substring-based verb list can't catch every destructive operation across
three different CLIs' vocabularies. Free-form mode should only be enabled
for catalog entries where you're comfortable reviewing every proposed
command yourself before confirming.

## Key risks and mitigations (POC scope)

| Risk | Mitigation |
|---|---|
| LLM hallucinates a destructive command (runbook mode) | Executor only accepts predefined runbook ids + schema-validated params; no shell string ever reaches subprocess from the LLM directly. |
| LLM proposes a destructive or IAM command (free-form mode) | `validate_free_form()` hardcodes-rejects forbidden verbs, `iam` subcommands, and any binary outside the aws/gcloud/kubectl/gh allowlist, regardless of catalog config or human edits to the command. |
| LLM tries a write-capable CLI verb via investigator tools | `src/investigator/tools.py` only defines read functions (describe/list/logs) per CLI; there is no code path for the investigator to invoke a write verb. |
| Wrong project's resources get touched | Resolver never guesses on ambiguous matches — raises `AmbiguousProjectError` instead of picking one. |
| A runbook is quietly upgraded to do something destructive | CI (`lint_runbooks.py`) rejects `terraform apply/destroy` substrings and hardcoded-forbidden ids (`any_delete`, `iam_modify`) at lint time; `executor.py` re-checks the rendered command at propose time. |
| Free-form command has a wrong/hallucinated parameter (e.g. AMI id) | No automated mitigation — the frontend requires reviewing and allows editing the exact command before confirming; this is a known limitation of drafting commands with a small local model. |
| Client data leaves their environment via the LLM | `llm_egress_approved` defaults to `false` on every catalog entry; local Ollama model means this is moot until you deliberately swap to a hosted model. |
| Credentials committed to the repo | `catalog/*.yaml` (except schema/examples) and `.env`/`*.pem`/`*.key`/`credentials/` are gitignored; CI runs `bandit` on `src/`. |

## Out of scope for this POC

- Multi-tenant credential isolation (assumes operator's local CLI auth is
  already scoped correctly per account).
- Sandboxing subprocess execution (relies on OS-level user permissions).
- Remote/hosted LLM support (not wired up; would need explicit design for
  egress approval enforcement before being added).
- Validating free-form command correctness against live cloud state
  (e.g. confirming an AMI id actually exists in the target region) —
  the human reviewer is the only check for this today.
