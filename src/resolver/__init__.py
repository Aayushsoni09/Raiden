"""src/resolver — maps a spoken/typed project name to a catalog entry.

No LLM involved. Exact match first, then fuzzy match against aliases.
If the match is ambiguous, callers must ask the user to disambiguate
rather than guessing.
"""
from .resolver import CatalogEntry, Resolver, ResolverError, AmbiguousMatchError, NoMatchError

__all__ = [
    "CatalogEntry",
    "Resolver",
    "ResolverError",
    "AmbiguousMatchError",
    "NoMatchError",
]

