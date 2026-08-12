from unittest.mock import MagicMock, patch

from scripts.catalog_drift import check_catalog_entry

GCP_ENTRY = {
    "id": "example-project",
    "clouds": [{
        "provider": "gcp",
        "project_id": "example-project-123456",
        "regions": ["asia-south1"],
        "services": [{"type": "cloud_run", "service": "example-project-api"}],
    }],
}

AWS_ENTRY = {
    "id": "example-project-aws",
    "clouds": [{
        "provider": "aws",
        "account_id": "123456789012",
        "regions": ["ap-south-1"],
        "services": [{"type": "ecs", "cluster": "example-cluster", "service": "example-project-api"}],
    }],
}


def test_check_gcp_entry_ok():
    with patch("scripts.catalog_drift.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        findings = check_catalog_entry(GCP_ENTRY)

    assert len(findings) == 1
    assert findings[0]["ok"] is True
    assert findings[0]["resource"] == "cloud_run:example-project-api"


def test_check_gcp_entry_drift():
    with patch("scripts.catalog_drift.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="NOT_FOUND: service does not exist")
        findings = check_catalog_entry(GCP_ENTRY)

    assert len(findings) == 1
    assert findings[0]["ok"] is False
    assert "NOT_FOUND" in findings[0]["detail"]


def test_check_aws_entry_ok():
    with patch("scripts.catalog_drift.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"serviceName": "example-project-api", "status": "ACTIVE"}]',
            stderr="",
        )
        findings = check_catalog_entry(AWS_ENTRY)

    assert len(findings) == 1
    assert findings[0]["ok"] is True
    assert findings[0]["resource"] == "ecs:example-cluster/example-project-api"


def test_check_aws_entry_drift_not_found():
    with patch("scripts.catalog_drift.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        findings = check_catalog_entry(AWS_ENTRY)

    assert len(findings) == 1
    assert findings[0]["ok"] is False
    assert "not found" in findings[0]["detail"].lower()


def test_check_catalog_entry_skips_unsupported_provider():
    entry = {"id": "x", "clouds": [{"provider": "azure", "regions": [], "services": []}]}
    assert check_catalog_entry(entry) == []
