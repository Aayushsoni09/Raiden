"""Project name -> catalog entry resolution.

Deliberately dumb: exact match, then fuzzy match on aliases. No LLM.
Ambiguity is surfaced to the caller instead of silently picking a winner —
getting this wrong means investigating (or worse, acting on) the wrong
client's infrastructure.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Any

import yaml
from rapidfuzz import fuzz, process

DEFAULT_MATCH_THRESHOLD = 80  # 0-100, rapidfuzz score
AMBIGUITY_MARGIN = 5  # if top-2 scores are within this margin, treat as ambiguous


class ResolverError(Exception):
    """Base class for resolver failures."""


class NoMatchError(ResolverError):
    def __init__(self, query: str):
        super().__init__(f"No catalog entry matches '{query}'.")
        self.query = query


class AmbiguousMatchError(ResolverError):
    def __init__(self, query: str, candidates: list["ScoredEntry"]):
        names = ", ".join(f"{c.entry.id} ({c.score:.0f})" for c in candidates)
        super().__init__(f"'{query}' matches multiple projects: {names}. Please disambiguate.")
        self.query = query
        self.candidates = candidates


@dataclass
class CatalogEntry:
    id: str
    aliases: list[str]
    clouds: list[dict[str, Any]]
    repos: list[dict[str, Any]] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    runbooks_allowed: list[str] = field(default_factory=list)
    runbooks_forbidden: list[str] = field(default_factory=list)
    llm_egress_approved: bool = False
    source_path: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_path: str = "") -> "CatalogEntry":
        return cls(
            id=data["id"],
            aliases=data.get("aliases", [data["id"]]),
            clouds=data.get("clouds", []),
            repos=data.get("repos", []),
            domains=data.get("domains", []),
            runbooks_allowed=data.get("runbooks_allowed", []),
            runbooks_forbidden=data.get("runbooks_forbidden", []),
            llm_egress_approved=data.get("llm_egress_approved", False),
            source_path=source_path,
        )

    def is_runbook_allowed(self, runbook_name: str) -> bool:
        # Hardcoded, non-negotiable deny-list — never overridable by catalog data.
        hardcoded_forbidden = {"any_delete", "iam_modify"}
        if runbook_name in hardcoded_forbidden:
            return False
        if runbook_name in self.runbooks_forbidden:
            return False
        return runbook_name in self.runbooks_allowed


@dataclass
class ScoredEntry:
    entry: CatalogEntry
    score: float
    matched_alias: str


class Resolver:
    def __init__(self, catalog_dir: str = "catalog"):
        self.catalog_dir = catalog_dir
        self._entries: list[CatalogEntry] = []
        self.reload()

    def reload(self) -> None:
        self._entries = []
        for path in sorted(glob.glob(os.path.join(self.catalog_dir, "*.yaml"))):
            filename = os.path.basename(path)
            if filename in ("_schema.yaml",):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                continue
            self._entries.append(CatalogEntry.from_dict(data, source_path=path))

    @property
    def entries(self) -> list[CatalogEntry]:
        return list(self._entries)

    def resolve(self, query: str, threshold: int = DEFAULT_MATCH_THRESHOLD) -> CatalogEntry:
        """Resolve a free-text project name to exactly one catalog entry.

        Raises NoMatchError or AmbiguousMatchError instead of guessing.
        """
        query_norm = query.strip().lower()
        if not query_norm:
            raise NoMatchError(query)

        # 1. Exact match against id or any alias (case-insensitive).
        for entry in self._entries:
            candidates = [entry.id.lower()] + [a.lower() for a in entry.aliases]
            if query_norm in candidates:
                return entry

        # 2. Fuzzy match across all (entry, alias) pairs.
        alias_index: list[tuple[str, CatalogEntry]] = []
        for entry in self._entries:
            for alias in [entry.id] + entry.aliases:
                alias_index.append((alias, entry))

        if not alias_index:
            raise NoMatchError(query)

        scored = process.extract(
            query_norm,
            [alias for alias, _ in alias_index],
            scorer=fuzz.WRatio,
            limit=len(alias_index),
        )
        # scored: list of (alias, score, index)
        best_per_entry: dict[str, ScoredEntry] = {}
        for alias, score, idx in scored:
            entry = alias_index[idx][1]
            existing = best_per_entry.get(entry.id)
            if existing is None or score > existing.score:
                best_per_entry[entry.id] = ScoredEntry(entry=entry, score=score, matched_alias=alias)

        ranked = sorted(best_per_entry.values(), key=lambda s: s.score, reverse=True)
        ranked = [s for s in ranked if s.score >= threshold]

        if not ranked:
            raise NoMatchError(query)
        if len(ranked) == 1:
            return ranked[0].entry
        if ranked[0].score - ranked[1].score < AMBIGUITY_MARGIN:
            raise AmbiguousMatchError(query, ranked[:5])
        return ranked[0].entry

