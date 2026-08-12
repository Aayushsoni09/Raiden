#!/usr/bin/env python3
"""Lint runbooks/*.yaml for the required shape and hardcoded safety rules.

Enforces (in addition to src/executor/executor.py's runtime checks):
  - required fields: name, command, params
  - name matches filename
  - no 'terraform apply' / 'terraform destroy' anywhere in the command
  - name is not in the hardcoded-forbidden set (any_delete, iam_modify)

Usage:
    python scripts/lint_runbooks.py runbooks/
"""
from __future__ import annotations

import glob
import os
import sys

import yaml

HARDCODED_FORBIDDEN = {"any_delete", "iam_modify"}
FORBIDDEN_SUBSTRINGS = ["terraform apply", "terraform destroy"]
REQUIRED_FIELDS = ["name", "command", "params"]


def lint_file(path: str) -> list[str]:
    errors = []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return [f"{path}: not a YAML mapping"]

    for field_name in REQUIRED_FIELDS:
        if field_name not in data:
            errors.append(f"{path}: missing required field '{field_name}'")

    name = data.get("name")
    expected_name = os.path.splitext(os.path.basename(path))[0]
    if name and name != expected_name:
        errors.append(f"{path}: name '{name}' does not match filename '{expected_name}'")

    if name in HARDCODED_FORBIDDEN:
        errors.append(f"{path}: runbook name '{name}' is in the hardcoded-forbidden set")

    command = data.get("command", [])
    full_command = " ".join(str(c) for c in command)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        if forbidden in full_command:
            errors.append(f"{path}: command contains forbidden operation '{forbidden}'")

    return errors


def main(argv: list[str]) -> int:
    directory = argv[0] if argv else "runbooks/"
    files = sorted(glob.glob(os.path.join(directory, "*.yaml")))
    if not files:
        print(f"No runbook YAML files found in {directory}")
        return 0

    all_errors: list[str] = []
    for path in files:
        errors = lint_file(path)
        if errors:
            all_errors.extend(errors)
        else:
            print(f"OK   {path}")

    for err in all_errors:
        print(f"FAIL {err}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

