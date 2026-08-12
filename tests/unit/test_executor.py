from pathlib import Path

import pytest

from src.executor.executor import RunbookExecutor, RunbookNotAllowedError

RUNBOOKS_DIR = Path(__file__).parent.parent.parent / "runbooks"

CATALOG_ENTRY = {
    "id": "example-project",
    "runbooks_allowed": ["restart_cloud_run"],
    "runbooks_forbidden": ["any_delete", "iam_modify"],
}


def make_executor(tmp_path):
    return RunbookExecutor(
        runbooks_dir=RUNBOOKS_DIR, audit_log_path=tmp_path / "audit.jsonl"
    )


def test_propose_allowed_runbook(tmp_path):
    executor = make_executor(tmp_path)
    command, requires_confirmation = executor.propose(
        "restart_cloud_run",
        {"service": "example-project-api", "region": "asia-south1", "project_id": "example-project-123456"},
        CATALOG_ENTRY,
    )
    assert command == [
        "gcloud", "run", "services", "update", "example-project-api",
        "--region=asia-south1", "--project=example-project-123456", "--no-traffic",
    ]
    assert requires_confirmation is True


def test_propose_rejects_forbidden_runbook(tmp_path):
    executor = make_executor(tmp_path)
    with pytest.raises(RunbookNotAllowedError):
        executor.propose("iam_modify", {}, CATALOG_ENTRY)


def test_propose_rejects_not_allowlisted_runbook(tmp_path):
    executor = make_executor(tmp_path)
    entry = {**CATALOG_ENTRY, "runbooks_allowed": []}
    with pytest.raises(RunbookNotAllowedError):
        executor.propose("restart_cloud_run", {"service": "x", "region": "y", "project_id": "z"}, entry)


def test_execute_requires_confirmation(tmp_path):
    executor = make_executor(tmp_path)
    with pytest.raises(PermissionError):
        executor.execute(["echo", "hi"], confirmed=False)


def test_propose_allowed_ecs_runbook(tmp_path):
    executor = make_executor(tmp_path)
    entry = {
        "id": "example-project-aws",
        "runbooks_allowed": ["restart_ecs_service"],
        "runbooks_forbidden": ["any_delete", "iam_modify"],
    }
    command, requires_confirmation = executor.propose(
        "restart_ecs_service",
        {"cluster": "example-cluster", "service": "example-project-api", "region": "ap-south-1"},
        entry,
    )
    assert command == [
        "aws", "ecs", "update-service",
        "--cluster", "example-cluster",
        "--service", "example-project-api",
        "--force-new-deployment",
        "--region", "ap-south-1",
    ]
    assert requires_confirmation is True
