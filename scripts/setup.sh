#!/usr/bin/env bash
# One-shot local setup for Raiden POC.
# Uses only free/open-source components:
#   - Ollama (local LLM runtime) + an open model (llama3.1)
#   - Python deps from requirements.txt
set -euo pipefail

echo "== Raiden setup =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ first." >&2
  exit 1
fi

echo "-- Creating virtualenv (.venv) --"
python3 -m venv .venv
source .venv/bin/activate

echo "-- Installing Python dependencies --"
pip install --upgrade pip
pip install -r requirements.txt

if command -v ollama >/dev/null 2>&1; then
  echo "-- Ollama found. Pulling default model (llama3.1) --"
  ollama pull llama3.1 || echo "Model pull failed/skipped; pull manually with 'ollama pull llama3.1'."
else
  echo "-- Ollama not found --"
  echo "   Install it (free, local, no API key needed):"
  echo "     macOS:  brew install ollama"
  echo "     other:  https://ollama.com/download"
  echo "   Then run: ollama pull llama3.1"
fi

echo ""
echo "-- Checking CLI auth (informational only) --"
aws sts get-caller-identity >/dev/null 2>&1 && echo "aws: authed" || echo "aws: not authed / not installed"
gcloud auth application-default print-access-token >/dev/null 2>&1 && echo "gcloud: authed" || echo "gcloud: not authed / not installed"
kubectl cluster-info >/dev/null 2>&1 && echo "kubectl: reachable" || echo "kubectl: not reachable / not installed"
gh auth status >/dev/null 2>&1 && echo "gh: authed" || echo "gh: not authed / not installed"

echo ""
echo "== Setup done =="
echo "Next: cp catalog/example-project.yaml catalog/myproject.yaml and edit it."
echo "Then: source .venv/bin/activate && python -m src.main catalog list"

