# Contributing to Raiden

Thanks for contributing! Short version, see below for detail.

- All changes via PR — branch protection blocks direct pushes to `main`.
- New cloud provider support → add a `providers/<name>/` directory
  implementing three methods: `describe(resource_ref) -> dict`,
  `list(resource_type, filters) -> list[dict]`, `logs(resource_ref, since) -> str`.
  All must be read-only.
- New runbooks → YAML only, under `runbooks/`. No shell scripts that take
  free-form input. Run `python scripts/lint_runbooks.py runbooks/` locally
  before opening a PR.
- Update `docs/THREAT_MODEL.md` whenever your PR adds a new capability
  that touches a write path (`src/executor/`, `runbooks/`).
- Tests required for any change under `src/executor/`.

## Local dev setup

```bash
./scripts/setup.sh
source .venv/bin/activate
pytest tests/unit/
```

## Adding a runbook

1. Copy an existing file in `runbooks/` as a starting point.
2. `name:` must match the filename (without `.yaml`).
3. `params:` is a JSON-Schema object — keep it minimal and required-only
   where it matters.
4. `command:` is a list of argv tokens; `{param}` placeholders are
   filled via `str.format`, so keep tokens separate (don't concatenate
   user input into a single string token).
5. Never write a runbook that shells out to `terraform apply`/`destroy`,
   any delete operation, or IAM modification — these are hardcoded-forbidden
   and CI will reject the PR.
6. Add the runbook name to a project's `runbooks_allowed` in its catalog
   entry — it's inert until explicitly allowed per project.

