#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$#" -eq 0 ]; then
  # Real per-project catalogs are gitignored (never checked out in CI) —
  # only default to files that aren't the synthetic examples/schema, so
  # this doesn't fail nightly against fake resources that were never meant
  # to exist. Pass explicit paths (e.g. catalog/example-project.yaml) to
  # check the examples deliberately.
  shopt -s nullglob
  paths=()
  for f in catalog/*.yaml; do
    case "$(basename "$f")" in
      _schema.yaml|example-project.yaml|example-project-aws.yaml) continue ;;
      *) paths+=("$f") ;;
    esac
  done
  shopt -u nullglob

  if [ "${#paths[@]}" -eq 0 ]; then
    echo "No real catalog entries found (catalog/*.yaml is gitignored except the examples/schema) — nothing to check."
    exit 0
  fi
else
  paths=("$@")
fi

python3 -m scripts.catalog_drift "${paths[@]}"
