from pathlib import Path

import pytest

from src.resolver.resolver import (
    AmbiguousProjectError,
    ProjectNotFoundError,
    resolve_project,
)

CATALOG_DIR = Path(__file__).parent.parent.parent / "catalog"


def test_resolve_exact_alias():
    entry = resolve_project("example-project", CATALOG_DIR)
    assert entry["id"] == "example-project"


def test_resolve_fuzzy_alias():
    entry = resolve_project("exampleproj", CATALOG_DIR)
    assert entry["id"] == "example-project"


def test_resolve_not_found():
    with pytest.raises(ProjectNotFoundError):
        resolve_project("totally-unknown-service-xyz", CATALOG_DIR)


def test_resolve_not_found_on_single_shared_word():
    # Regression: WRatio alone scores "totally unknown gibberish project
    # name" at 85+ against both example-project* aliases because they share
    # the single word "project" — the raised threshold must reject this.
    with pytest.raises(ProjectNotFoundError):
        resolve_project("totally unknown gibberish project name", CATALOG_DIR)


def test_resolve_prefers_more_specific_superset_alias():
    # Regression: "example project" is a literal prefix of "example project
    # aws", so a query naming the AWS project used to tie both entries.
    entry = resolve_project("example project aws is down", CATALOG_DIR)
    assert entry["id"] == "example-project-aws"


def test_resolve_generic_phrase_matches_shorter_alias_unambiguously():
    entry = resolve_project("example project is down", CATALOG_DIR)
    assert entry["id"] == "example-project"
