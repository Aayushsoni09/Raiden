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
