"""Dry-run the investigator graph against an AWS/ECS catalog entry, with
mocked CLI calls and mocked LLM. No real aws/gh/Ollama required.
"""

import json
from unittest.mock import MagicMock, patch

import yaml

from src.investigator.graph import investigate

CATALOG_ENTRY = yaml.safe_load(
    """
id: example-project-aws
aliases: [example-project-aws]
clouds:
  - provider: aws
    account_id: "123456789012"
    regions: [ap-south-1]
    services:
      - { type: ecs, cluster: example-cluster, service: example-project-api }
repos:
  - { url: github.com/your-org/example-project-api, deploy: github-actions }
runbooks_allowed: [restart_ecs_service]
runbooks_forbidden: [any_delete, iam_modify]
llm_egress_approved: false
"""
)

FAKE_DESCRIBE_SERVICES = {
    "cmd": "aws ecs describe-services ...",
    "returncode": 0,
    "stdout": json.dumps({"services": [{"deployments": [{"rolloutState": "FAILED"}], "events": [
        {"message": "service example-project-api was unable to place a task because no container instance met all of its requirements"}
    ]}]}),
    "stderr": "",
}

FAKE_LIST_TASKS = {
    "cmd": "aws ecs list-tasks ...",
    "returncode": 0,
    "stdout": json.dumps({"taskArns": []}),
    "stderr": "",
}

FAKE_LOGS_TAIL = {
    "cmd": "aws logs tail ...",
    "returncode": 0,
    "stdout": "ResourceInitializationError: unable to pull secrets or registry auth: execution resource retrieval failed",
    "stderr": "",
}

FAKE_GH_RUNS = {
    "cmd": "gh run list ...",
    "returncode": 0,
    "stdout": json.dumps([{"status": "completed", "conclusion": "success"}]),
    "stderr": "",
}


def test_investigate_dry_run_aws(tmp_path):
    audit_path = tmp_path / "audit.jsonl"

    with patch("src.investigator.tools._run") as mock_run, patch(
        "src.investigator.graph.ChatOllama"
    ) as mock_chat:
        mock_run.side_effect = [
            FAKE_DESCRIBE_SERVICES, FAKE_LIST_TASKS, FAKE_LOGS_TAIL, FAKE_GH_RUNS,
        ]

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(
            content=(
                "1. ECS task failed to start — unable to retrieve execution "
                "role secrets/registry auth. Confidence: high."
            )
        )
        mock_chat.return_value = mock_llm_instance

        hypotheses = investigate(
            report="the api service is down",
            catalog_entry=CATALOG_ENTRY,
            audit_log_path=audit_path,
        )

    assert "execution role" in hypotheses.lower() or "secrets" in hypotheses.lower()
    assert mock_run.call_count == 4
    mock_chat.assert_called_once()

    audit_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in audit_lines]
    assert events[0]["type"] == "investigation_started"
    assert events[-1]["type"] == "investigation_completed"
