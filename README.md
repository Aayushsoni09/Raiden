# ⚡ Raiden (雷電)

> A voice-driven, local-first DevOps agent that investigates and remediates your cloud incidents — across AWS and GCP — without you touching a console.

You say what's broken. Raiden figures out what went wrong, tells you why, and asks before it fixes anything.

---

## What this is

Raiden is a persistent Claude Code session running on your local machine, wired up to your existing AWS/GCP CLIs and a YAML catalog of your projects. It listens, investigates, proposes, and acts — only on your say-so.

No dashboards. No extra SaaS subscriptions. No Slack bots. Just your terminal and your voice.

**What it's not:** an always-on cloud service, a magic root-cause oracle, or a replacement for understanding your own infrastructure. It's a tool that does the tedious `aws describe-*` and `gcloud logging read` loops for you, then hands you a ranked list of what probably went wrong.

---

## How it works

```
You speak
    │
    ▼
Speech-to-Text (local Whisper or cloud STT)
    │
    ▼
Claude Code session (your terminal, persistent)
    ├── reads catalog.yaml  →  resolves project name to account + region + services
    ├── runs aws / gcloud / kubectl CLI commands (already authed as you)
    ├── reads logs, metrics, recent deployments, IAM changes
    └── produces ranked hypotheses with supporting + disconfirming evidence
    │
    ▼
Text-to-Speech (Piper TTS local, or ElevenLabs/Google TTS)
    │  "Looks like the ECS task failed health checks after the 14:32 deploy.
    │   Secret Manager permission was removed. Want me to redeploy the
    │   previous revision?"
    ▼
You say "yes"
    │
    ▼
Raiden runs the approved CLI command
    │
    ▼
Verifies the fix → tells you outcome → logs everything locally
```

### The catalog is the real product

Before Raiden can investigate anything, it needs to know what "my-app" means in terms of actual cloud resources. That mapping lives in `catalog/my-app.yaml`:

```yaml
id: my-app
aliases: [my-app, "my app", myapp]
clouds:
  - provider: aws
    account_id: "123456789012"
    regions: [ap-south-1]
    services:
      - { type: ecs, cluster: prod-cluster, service: my-app-service }
      - { type: dynamodb }
repos:
  - { url: github.com/org/my-app-api, deploy: github-actions }
domains: [my-app.com, api.my-app.com]
runbooks_allowed: [restart_ecs_service, rollback_ecs_task_def]
runbooks_forbidden: [any_delete, iam_modify]
llm_egress_approved: false   # flip to true only after client contract sign-off
```

No LLM is involved in tenant resolution. Project names map by exact/fuzzy match against aliases. If it's ambiguous, Raiden asks before doing anything.

---

## What Raiden will and won't do automatically

| Action | Behaviour |
|---|---|
| Read logs, metrics, describe resources | Automatic, no prompt |
| DNS checks, HTTP health probes | Automatic |
| What changed in last 24h (CI, deployments, CloudTrail) | Automatic |
| Restart a service / pod (non-production) | Auto with notification + auto-rollback on failure |
| Redeploy / rollback in production | Always asks first |
| Rotate a secret | Always asks first |
| Modify IAM | Never. Raiden proposes the command; you run it. |
| Delete anything | Never. |
| `terraform apply` | Never from voice. Propose only. |

The rule of thumb: if getting it wrong could take down a client's production system or expose their data, Raiden doesn't do it autonomously. It tells you exactly what to run and why.

---

## Stack

| Component | What we use | Why |
|---|---|---|
| LLM + agent loop | Claude Code (persistent session) | Already on your machine, MCP-native, subagent support, permission hooks |
| Cloud — AWS | `aws` CLI (already installed and authed) | Zero setup. Upgrade to AWS Agent Toolkit MCP later for IAM condition keys on writes. |
| Cloud — GCP | `gcloud` CLI + ADC | Same. `@google-cloud/gcloud-mcp` and `observability-mcp` are drop-in upgrades. |
| Kubernetes | `kubectl` | Existing kubeconfigs work as-is |
| GitHub | `gh` CLI | CI run history, deployment events, recent commits |
| STT | Whisper (local, `whisper.cpp` for speed) | Free, works offline, no audio leaving your machine |
| TTS | Piper TTS (local) | Free, fast, offline |
| Catalog | Git-backed YAML | Reviewable, driftable, auditable. PRs required to change blast-radius config. |
| Evidence store | SQLite (local, per-session) | No infra needed at MVP |
| Audit log | Append-only local file | CloudTrail/Cloud Audit Logs capture the actual API calls anyway |

---

## Repo structure

```
raiden/
├── README.md
├── LICENSE                    # Apache-2.0
├── catalog/                   # One YAML per project. Never commit real account IDs.
│   ├── _schema.yaml           # Validated schema + field docs
│   ├── example-project.yaml   # Safe synthetic example
│   └── .gitignore             # ← catalog/*.yaml ignored by default; you add yours locally
├── src/
│   ├── resolver/              # project name → catalog entry (no LLM)
│   ├── investigator/          # Agent loop, subagent definitions, hypothesis ranking
│   ├── executor/              # Runbook runner — accepts structured intents only, not free-form commands
│   ├── voice/
│   │   ├── stt/               # Whisper wrapper
│   │   └── tts/               # Piper wrapper
│   └── audit/                 # Append-only local log
├── runbooks/                  # YAML-defined, parameterised. Executor runs these, nothing else.
│   ├── restart_ecs_service.yaml
│   ├── rollback_ecs_task_def.yaml
│   ├── restart_cloud_run.yaml
│   └── rollback_cloud_run.yaml
├── prompts/                   # System prompts, few-shot examples
├── scripts/
│   ├── setup.sh               # One-shot local setup
│   └── catalog-drift.sh       # Nightly: verify catalog resources actually exist
├── tests/
│   ├── unit/
│   ├── integration/           # Dry-run against fake resources
│   └── fixtures/              # Sample CLI outputs for offline testing
├── docs/
│   ├── THREAT_MODEL.md        # Read before contributing
│   ├── CONTRIBUTING.md
│   ├── SECURITY.md
│   └── ADR/                   # Architecture decision records
└── .github/
    ├── workflows/
    │   ├── ci.yml             # Lint, test, catalog validation on every PR
    │   └── drift-check.yml    # Nightly catalog drift
    └── CODEOWNERS
```

---

## Getting started

### Prerequisites

Make sure these are installed and working before anything else:

```bash
# Check your CLIs are authed
aws sts get-caller-identity
gcloud auth application-default print-access-token
kubectl cluster-info   # if you use k8s
gh auth status

# Claude Code
claude --version

# Whisper (choose one)
pip install openai-whisper           # Python, heavier
brew install whisper-cpp             # macOS, faster

# Piper TTS (local voice output)
pip install piper-tts
```

### 1. Clone and set up

```bash
git clone https://github.com/your-org/raiden
cd raiden
./scripts/setup.sh
```

### 2. Create your first catalog entry

Copy the example and fill in your project:

```bash
cp catalog/example-project.yaml catalog/myproject.yaml
# Edit catalog/myproject.yaml — see _schema.yaml for every field explained
```

Don't commit real account IDs to the repo. `catalog/*.yaml` is gitignored by default. Keep your real catalogs locally or in a private fork.

### 3. Validate the catalog

```bash
./scripts/catalog-drift.sh catalog/myproject.yaml
```

This checks that the resources listed actually exist in the cloud accounts. Fix any drift before relying on it during an incident.

### 4. Run a text-mode investigation (no voice yet)

```bash
claude   # start a session
# then type:
> the api service is down
```

Get comfortable with the text loop before adding voice. The voice layer is just STT → text and text → TTS on top of the same thing.

### 5. Add voice

```bash
# test STT
python src/voice/stt/transcribe.py --mic

# test TTS
echo "investigating the api service" | python src/voice/tts/speak.py

# full voice loop
python src/voice/loop.py
```

---

## Security model

A few things that are non-negotiable:

**Raiden never holds a write credential in the same process as the LLM.** The investigator is read-only. By default, the executor accepts only validated, parameterised runbook intents. A project can opt in to a broader "free-form action" mode (`free_form_actions_allowed: true`) where the LLM drafts an `aws`/`gcloud`/`kubectl`/`gh` command from a request — this is off by default, requires human review (and lets you edit the command) before confirming, and hardcoded-forbidden verbs/IAM checks still apply regardless. See `docs/THREAT_MODEL.md` for the full trust-boundary writeup.

**The catalog has a `llm_egress_approved` field.** If it's `false`, Raiden refuses to send that project's telemetry to any model provider. This defaults to `false` on every new catalog entry. You flip it only after your client has contractually agreed that their logs can leave their environment.

**IAM changes, deletions, and `terraform apply` are hardcoded off.** Not configurable. If you need to do those things, Raiden will propose the exact command; you copy-paste and run it yourself.

**Everything gets logged.** Your local `audit/` directory gets every input, hypothesis, approval, and command with a timestamp. CloudTrail and Cloud Audit Logs capture the actual API calls on the cloud side. If something goes wrong, you have a full trail.

---

## Contributing

See `docs/CONTRIBUTING.md` for the full guide. Short version:

- All contributions via PR — no direct pushes to `main` (branch protection is on, see below)
- New cloud provider support → add a `providers/<name>/` directory implementing the three-method interface in `docs/CONTRIBUTING.md`
- New runbooks → YAML only, in `runbooks/`. No shell scripts that take free-form input.
- The `THREAT_MODEL.md` gets updated whenever you add a new capability that touches write paths
- Tests required for any executor path change

---

## GitHub repo policies — branch protection setup

Do this right after you create the repo. It takes 5 minutes and saves you from the "oops I pushed to main" moment.

### Step 1 — go to branch protection settings

`Settings → Branches → Add branch ruleset` (or `Add rule` on older GitHub UI)

Set the branch name pattern to `main`.

### Step 2 — enable these settings

| Setting | Value | Why |
|---|---|---|
| Restrict pushes that create matching branches | ✅ on | Nobody accidentally creates `main` from a fork |
| Require a pull request before merging | ✅ on | All changes go through PR |
| Required approvals | 1 (or 0 if solo) | At least one review for external contributors |
| Dismiss stale pull request approvals when new commits are pushed | ✅ on | Approval on old code doesn't carry forward |
| Require review from Code Owners | ✅ on | CODEOWNERS file controls who reviews what |
| Require status checks to pass before merging | ✅ on | CI must pass |
| Status checks: add `ci` | your CI job name | Blocks merge if tests fail |
| Require branches to be up to date before merging | ✅ on | No merging stale PRs |
| Do not allow bypassing the above settings | ✅ on | **This one matters** — without it, repo admins can still push directly |
| Restrict who can push to matching branches | Add only yourself (or your org's bot account) | External contributors physically cannot push |

### Step 3 — CODEOWNERS file

Create `.github/CODEOWNERS`:

```
# Everything requires review from the core maintainer
*                   @your-github-username

# Runbooks and executor paths need extra scrutiny
/runbooks/          @your-github-username
/src/executor/      @your-github-username
/catalog/_schema.yaml @your-github-username
```

This means any PR touching the executor or runbooks needs your explicit approval regardless of what else is configured.

### Step 4 — set up the required CI status check

Your `ci.yml` should run on every PR:

```yaml
name: ci
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint runbooks
        run: python scripts/lint_runbooks.py runbooks/
      - name: Validate catalog schema
        run: python scripts/validate_catalog.py catalog/_schema.yaml catalog/example-project.yaml
      - name: Unit tests
        run: pytest tests/unit/
      - name: Security scan
        run: pip install bandit && bandit -r src/
```

Add the job name `test` (or whatever you name it) as a required status check in the branch protection settings.

### Step 5 — verify it actually works

```bash
# Try to push directly to main as yourself
git checkout main
echo "test" >> README.md
git add . && git commit -m "test direct push"
git push origin main
# Should be rejected: "remote: error: GH006: Protected branch update failed"
```

If it goes through, check that "Do not allow bypassing the above settings" is enabled — admins bypass protection by default unless that's explicitly turned off.

### For external contributors — what they'll experience

When someone forks and opens a PR:
1. CI runs automatically on their PR
2. They can't merge until CI passes and you've approved
3. If they push more commits after your approval, the approval is dismissed and they need re-review
4. They physically cannot push to `main` regardless of what permissions they think they have

That's the whole thing. No bots, no extra apps, just native GitHub branch protection.

---

## Name

**Raiden (雷電)** — Japanese for "thunderbolt". Fast response, decisive action, and it sounds cool when your TTS says it back to you.

---

## License

Apache-2.0. See `LICENSE`.
