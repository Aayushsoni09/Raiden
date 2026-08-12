#!/usr/bin/env bash
set -euo pipefail

echo "==> Checking for Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama not found. Install it from https://ollama.com/download and re-run this script."
  exit 1
fi

echo "==> Pulling local model (llama3.1:8b)"
ollama pull llama3.1:8b

echo "==> Installing Python dependencies"
python3 -m pip install -r requirements.txt

echo "==> Checking GCP auth (Phase 1: GCP only)"
gcloud auth application-default print-access-token >/dev/null 2>&1 \
  && echo "GCP ADC OK" \
  || echo "WARNING: gcloud ADC not configured. Run: gcloud auth application-default login"

echo "==> Setup complete. Try: python -m src.investigator (after adding a catalog entry)"
