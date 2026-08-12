#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <catalog/*.yaml ...>"
  echo "  Defaults to checking every catalog entry when no paths given."
  paths=(catalog/*.yaml)
  # Skip schema file — it isn't a real catalog entry.
  paths=("${paths[@]/catalog\/_schema.yaml/}")
else
  paths=("$@")
fi

cd "$(dirname "$0")/.." && python3 -m scripts.catalog_drift "${paths[@]}"
