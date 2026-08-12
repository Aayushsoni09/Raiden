"""Unit tests for src/executor (runbook loading + safety guards, no real subprocess calls)."""
import os
import tempfile

import pytest
import yaml

from src.executor import RunbookNotAllowedError, RunbookRunner, RunbookValidationError
from src.resolver import CatalogEntry


def _write_runbook(tmpdir: str, filename: str, data: dict) -> None:
    with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


@pytest.fixture
def runbooks_dir():
    with tempfile.TemporaryDirectory() as tmp:
        _write_runbook(
            tmp,
            "noop.yaml",
            {
                "name": "noop",
                "description": "test runbook",
                "params": {"type": "object", "required": ["msg"], "properties": {"msg": {"type": "string"}}},
                "command": ["echo", "{msg}"],
                "confirm_message": "Echo {msg}?",
            },
        )
        yield tmp


@pytest.fixture
def entry():
    return CatalogEntry(id="proj", aliases=["proj"], clouds=[], runbooks_allowed=["noop"])


def test_run_requires_approval(runbooks_dir, entry, tmp_path):
    runner = RunbookRunner(runbooks_dir=runbooks_dir, audit_logger=_fake_audit(tmp_path))
    with pytest.raises(Exception):
        runner.run("noop", {"msg": "hi"}, entry, confirm=lambda msg: False)


def test_run_executes_on_approval(runbooks_dir, entry, tmp_path):
    runner = RunbookRunner(runbooks_dir=runbooks_dir, audit_logger=_fake_audit(tmp_path))
    output = runner.run("noop", {"msg": "hi"}, entry, confirm=lambda msg: True)
    assert output == "hi"


def test_runbook_not_allowed(runbooks_dir, tmp_path):
    runner = RunbookRunner(runbooks_dir=runbooks_dir, audit_logger=_fake_audit(tmp_path))
    entry_no_perm = CatalogEntry(id="proj", aliases=["proj"], clouds=[], runbooks_allowed=[])
    with pytest.raises(RunbookNotAllowedError):
        runner.run("noop", {"msg": "hi"}, entry_no_perm, confirm=lambda msg: True)


def test_invalid_params_rejected(runbooks_dir, entry, tmp_path):
    runner = RunbookRunner(runbooks_dir=runbooks_dir, audit_logger=_fake_audit(tmp_path))
    with pytest.raises(RunbookValidationError):
        runner.run("noop", {}, entry, confirm=lambda msg: True)


def test_hardcoded_forbidden_names_rejected(runbooks_dir, tmp_path):
    _write_runbook(
        runbooks_dir,
        "iam_modify.yaml",
        {"name": "iam_modify", "params": {"type": "object", "properties": {}}, "command": ["echo", "no"]},
    )
    runner = RunbookRunner(runbooks_dir=runbooks_dir, audit_logger=_fake_audit(tmp_path))
    entry_all = CatalogEntry(id="proj", aliases=["proj"], clouds=[], runbooks_allowed=["iam_modify"])
    with pytest.raises(RunbookNotAllowedError):
        runner.run("iam_modify", {}, entry_all, confirm=lambda msg: True)


def test_terraform_apply_rejected_at_load(tmp_path):
    from src.executor.executor import RunbookDefinition

    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text(
        yaml.safe_dump({"name": "bad", "params": {"type": "object", "properties": {}}, "command": ["terraform", "apply"]})
    )
    with pytest.raises(RunbookValidationError):
        RunbookDefinition.from_file(str(bad_path))


def _fake_audit(tmp_path):
    from src.audit import AuditLogger

    return AuditLogger(audit_dir=str(tmp_path / "audit"))

