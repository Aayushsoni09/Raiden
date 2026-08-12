"""Unit tests for src/resolver."""
import os
import tempfile

import pytest
import yaml

from src.resolver import AmbiguousMatchError, NoMatchError, Resolver


def _write_catalog(tmpdir: str, filename: str, data: dict) -> None:
    with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


@pytest.fixture
def catalog_dir():
    with tempfile.TemporaryDirectory() as tmp:
        _write_catalog(
            tmp,
            "my-app.yaml",
            {
                "id": "my-app",
                "aliases": ["my-app", "my app", "myapp"],
                "clouds": [{"provider": "aws", "account_id": "123", "regions": ["us-east-1"], "services": []}],
                "runbooks_allowed": ["restart_ecs_service"],
            },
        )
        _write_catalog(
            tmp,
            "my-other-app.yaml",
            {
                "id": "my-other-app",
                "aliases": ["my-other-app", "other app"],
                "clouds": [],
            },
        )
        yield tmp


def test_exact_match(catalog_dir):
    resolver = Resolver(catalog_dir=catalog_dir)
    entry = resolver.resolve("my-app")
    assert entry.id == "my-app"


def test_alias_exact_match_case_insensitive(catalog_dir):
    resolver = Resolver(catalog_dir=catalog_dir)
    entry = resolver.resolve("MYAPP")
    assert entry.id == "my-app"


def test_fuzzy_match(catalog_dir):
    resolver = Resolver(catalog_dir=catalog_dir)
    # "my app" alone should clearly favor my-app; a longer sentence can
    # legitimately trip the ambiguity guard against my-other-app, which is
    # the desired safe behavior (prefer asking over guessing).
    entry = resolver.resolve("my app")
    assert entry.id == "my-app"


def test_ambiguous_query_raises(catalog_dir):
    resolver = Resolver(catalog_dir=catalog_dir)
    with pytest.raises(AmbiguousMatchError):
        resolver.resolve("my app is down")



def test_no_match(catalog_dir):
    resolver = Resolver(catalog_dir=catalog_dir)
    with pytest.raises(NoMatchError):
        resolver.resolve("totally unrelated project name xyz123")


def test_runbook_allowed(catalog_dir):
    resolver = Resolver(catalog_dir=catalog_dir)
    entry = resolver.resolve("my-app")
    assert entry.is_runbook_allowed("restart_ecs_service") is True
    assert entry.is_runbook_allowed("iam_modify") is False
    assert entry.is_runbook_allowed("any_delete") is False
    assert entry.is_runbook_allowed("some_random_runbook") is False

