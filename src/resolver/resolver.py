"""Project name -> catalog entry resolution. No LLM involved."""

from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

# WRatio is lenient enough that a single shared word (e.g. "project") in a
# long freeform report can score 80+ against an unrelated alias. 90 keeps
# genuine near-exact alias mentions matching while rejecting single-word
# coincidental overlaps.
FUZZY_MATCH_THRESHOLD = 90

# If the best-scoring entry beats the runner-up by at least this many WRatio
# points, treat it as a clear winner instead of ambiguous.
AMBIGUITY_MARGIN = 10


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
        query_norm, alias_to_entry.keys(), scorer=fuzz.WRatio, limit=len(alias_to_entry) or 1
    )
    good_matches = [m for m in matches if m[1] >= FUZZY_MATCH_THRESHOLD]

    if not good_matches:
        raise ProjectNotFoundError(f"No catalog entry matches '{query}'")

    # Best (alias, score) per entry — an entry may have multiple aliases
    # above threshold; keep the one that matched best.
    best_by_entry = {}
    entry_by_id = {}
    for alias, score, _ in good_matches:
        entry = alias_to_entry[alias]
        entry_id = entry["id"]
        entry_by_id[entry_id] = entry
        if entry_id not in best_by_entry or score > best_by_entry[entry_id][1]:
            best_by_entry[entry_id] = (alias, score)

    ranked = sorted(best_by_entry.items(), key=lambda kv: kv[1][1], reverse=True)

    if len(ranked) == 1:
        return entry_by_id[ranked[0][0]]

    top_id, (top_alias, top_score) = ranked[0]
    runner_up_id, (runner_up_alias, runner_up_score) = ranked[1]

    if top_score - runner_up_score >= AMBIGUITY_MARGIN:
        return entry_by_id[top_id]

    # A near-tie where one winning alias is a superset phrase of the other
    # (e.g. "example project aws" contains "example project") almost always
    # means the longer, more specific alias is the intended match — the
    # shorter one only scored well because it's a substring of the longer.
    if runner_up_alias in top_alias:
        return entry_by_id[top_id]
    if top_alias in runner_up_alias:
        return entry_by_id[runner_up_id]

    tied_ids = [entry_id for entry_id, (_, score) in ranked if top_score - score < AMBIGUITY_MARGIN]
    raise AmbiguousProjectError(query, tied_ids)
