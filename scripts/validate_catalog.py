#!/usr/bin/env python3
"""Validate catalog YAML files against catalog/_schema.yaml.

Usage:
    python scripts/validate_catalog.py catalog/_schema.yaml catalog/example-project.yaml [more files...]
    python scripts/validate_catalog.py catalog/_schema.yaml catalog/*.yaml
"""
from __future__ import annotations

import sys

import yaml
from jsonschema import Draft7Validator


def main(argv: list[str]) -> int:
    """argv is sys.argv[1:] — schema path followed by one or more catalog file paths."""
    if len(argv) < 2:
        print("Usage: validate_catalog.py <schema.yaml> <catalog-file.yaml> [...]", file=sys.stderr)
        return 2

    schema_path, *catalog_paths = argv

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    validator = Draft7Validator(schema)

    exit_code = 0
    for path in catalog_paths:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errors:
            exit_code = 1
            print(f"FAIL {path}")
            for err in errors:
                loc = "/".join(str(p) for p in err.path) or "<root>"
                print(f"  - {loc}: {err.message}")
        else:
            print(f"OK   {path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

