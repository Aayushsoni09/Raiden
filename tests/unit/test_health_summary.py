import json

from src.investigator.graph import _summarize_ecs_evidence, summarize_evidence

CATALOG_ENTRY_ECS = {
    "clouds": [{
        "provider": "aws",
        "regions": ["ap-south-1"],
        "services": [{"type": "ecs", "cluster": "c", "service": "s"}],
    }]
}


def _ecs_describe(stdout_obj, returncode=0):
    return {"cmd": "aws ecs describe-services ...", "returncode": returncode, "stdout": json.dumps(stdout_obj), "stderr": ""}


def test_failed_rollout_with_missing_counts_is_unhealthy_not_none_eq_none():
    # Regression: running/desired both absent (None) must not be treated as
    # "counts match" via Python's None == None being True.
    result = _summarize_ecs_evidence(
        _ecs_describe({"services": [{"serviceName": "s", "deployments": [{"rolloutState": "FAILED"}]}]})
    )
    assert result["healthy"] is False


def test_missing_counts_and_no_failed_deploy_is_unknown():
    result = _summarize_ecs_evidence(
        _ecs_describe({"services": [{"serviceName": "s", "deployments": [{"rolloutState": "IN_PROGRESS"}]}]})
    )
    assert result["healthy"] is None


def test_matching_counts_with_completed_rollout_is_healthy():
    result = _summarize_ecs_evidence(
        _ecs_describe({
            "services": [{
                "serviceName": "s", "runningCount": 1, "desiredCount": 1,
                "deployments": [{"rolloutState": "COMPLETED"}],
            }]
        })
    )
    assert result["healthy"] is True


def test_summarize_evidence_matches_gather_evidence_indexing():
    # aws ecs gathers 3 evidence entries per service (describe, list-tasks, logs)
    evidence = [
        _ecs_describe({"services": [{"serviceName": "s", "runningCount": 1, "desiredCount": 1, "deployments": [{"rolloutState": "COMPLETED"}]}]}),
        {"cmd": "list-tasks", "returncode": 0, "stdout": "{}", "stderr": ""},
        {"cmd": "logs tail", "returncode": 0, "stdout": "", "stderr": ""},
    ]
    summaries = summarize_evidence(CATALOG_ENTRY_ECS, evidence)
    assert len(summaries) == 1
    assert summaries[0]["healthy"] is True
