"""Dry-run the full investigator graph with mocked CLI calls and mocked LLM.

No real gcloud/gh/Ollama required. Verifies gather_evidence -> rank_hypotheses
-> audit logging wiring end-to-end.
"""

import json
from unittest.mock import MagicMock, patch

import yaml

from src.evidence import EvidenceStore
from src.investigator.graph import investigate

CATALOG_ENTRY = yaml.safe_load(
    """
id: example-project
aliases: [example-project]
clouds:
  - provider: gcp
    project_id: example-project-123456
    regions: [asia-south1]
    services:
      - { type: cloud_run, service: example-project-api }
repos:
  - { url: github.com/your-org/example-project-api, deploy: github-actions }
runbooks_allowed: [restart_cloud_run]
runbooks_forbidden: [any_delete, iam_modify]
llm_egress_approved: false
"""
)

FAKE_DESCRIBE = {
    "cmd": "gcloud run services describe ...",
    "returncode": 0,
    "stdout": json.dumps({"status": {"conditions": [{"type": "Ready", "status": "False"}]}}),
    "stderr": "",
}

FAKE_LOGS = {
    "cmd": "gcloud logging read ...",
    "returncode": 0,
    "stdout": json.dumps([{"severity": "ERROR", "textPayload": "permission denied on secret X"}]),
    "stderr": "",
}

FAKE_GH_RUNS = {
    "cmd": "gh run list ...",
    "returncode": 0,
    "stdout": json.dumps([{"status": "completed", "conclusion": "success"}]),
    "stderr": "",
}


def test_investigate_dry_run(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    evidence_db_path = tmp_path / "evidence.sqlite3"

    with patch("src.investigator.tools._run") as mock_run, patch(
        "src.investigator.graph.ChatOllama"
    ) as mock_chat:
        mock_run.side_effect = [FAKE_DESCRIBE, FAKE_LOGS, FAKE_GH_RUNS]

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(
            content=(
                "1. Cloud Run revision failed readiness — permission denied on "
                "Secret Manager access. Confidence: high."
            )
        )
        mock_chat.return_value = mock_llm_instance

        hypotheses = investigate(
            report="the api service is down",
            catalog_entry=CATALOG_ENTRY,
            audit_log_path=audit_path,
            evidence_db_path=evidence_db_path,
        )

    assert "permission denied" in hypotheses.lower()
    assert mock_run.call_count == 3
    mock_chat.assert_called_once()

    audit_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in audit_lines]
    assert events[0]["type"] == "investigation_started"
    assert events[-1]["type"] == "investigation_completed"
    assert "permission denied" in events[-1]["hypotheses"].lower()

    store = EvidenceStore(evidence_db_path)
    saved = store.get_investigation(1)
    assert saved["project"] == "example-project"
    assert "permission denied" in saved["hypotheses"].lower()
