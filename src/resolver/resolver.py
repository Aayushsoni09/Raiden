"""Project name -> catalog entry resolution. No LLM involved."""

from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

FUZZY_MATCH_THRESHOLD = 80


class AmbiguousProjectError(Exception):
    def __init__(self, query, candidates):
        self.query = query
        self.candidates = candidates
        super().__init__(f"'{query}' matches multiple projects: {candidates}")


class ProjectNotFoundError(Exception):
    pass


def load_catalog(catalog_dir):
    catalog_dir = Path(catalog_dir)
    entries = []
    for path in catalog_dir.glob("*.yaml"):
        if path.name.startswith("_"):
            continue
        with open(path, "r", encoding="utf-8") as f:
            entries.append(yaml.safe_load(f))
    return entries


def resolve_project(query, catalog_dir):
    entries = load_catalog(catalog_dir)
    query_norm = query.strip().lower()

    alias_to_entry = {}
    for entry in entries:
        for alias in entry.get("aliases", []):
            alias_to_entry[alias.strip().lower()] = entry

    if query_norm in alias_to_entry:
        return alias_to_entry[query_norm]

    matches = process.extract(
        query_norm, alias_to_entry.keys(), scorer=fuzz.WRatio, limit=5
    )
    good_matches = [m for m in matches if m[1] >= FUZZY_MATCH_THRESHOLD]

    if not good_matches:
        raise ProjectNotFoundError(f"No catalog entry matches '{query}'")

    matched_entries = {
        alias_to_entry[alias]["id"]: alias_to_entry[alias] for alias, _, _ in good_matches
    }

    if len(matched_entries) > 1:
        raise AmbiguousProjectError(query, list(matched_entries.keys()))

    return next(iter(matched_entries.values()))
