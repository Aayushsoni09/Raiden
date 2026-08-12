"""LangGraph investigator loop: read-only evidence gathering -> ranked hypotheses.

Uses a local Ollama model (e.g. llama3.1:8b or qwen2.5:7b) via langchain-ollama.
The investigator never calls write/mutating CLI commands.
"""

import json
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from src.audit import AuditLog
from src.evidence import EvidenceStore
from src.investigator import tools

DEFAULT_MODEL = "llama3.1:8b"

HYPOTHESIS_PROMPT = """You are Raiden's investigator. You only read evidence; you never propose \
destructive or write actions directly to be run automatically.

Project: {project_id}
Services: {services}
Report: {report}

Health summary (computed directly from the evidence below — trust these
facts over your own reading of the raw command output):
{health_summary}

Raw evidence gathered:
{evidence}

Rules for ranking hypotheses:
- Only claim a service is unhealthy if the health summary or raw evidence
  shows an explicit error, a mismatch between running and desired task/
  instance counts, or a non-zero command exit code. Matching counts and a
  "steady state" / "Ready: True" condition mean the service is healthy —
  do not invent a failure hypothesis to explain a report if there is no
  such evidence.
- If nothing in the evidence indicates a problem, your top hypothesis
  must say so plainly (e.g. "service appears healthy; no error evidence
  found") with high confidence, rather than speculating about issues
  that aren't supported by the evidence.
- Every hypothesis needs supporting evidence quoted or closely
  paraphrased from the health summary or raw evidence above — not
  generic reasoning about what "might" be misconfigured.

Produce a ranked list of hypotheses for what went wrong (or a statement
that nothing is wrong). For each hypothesis include:
- statement
- supporting evidence
- disconfirming evidence (if any)
- confidence (low/medium/high)
"""


class InvestigatorState(TypedDict):
    report: str
    catalog_entry: dict
    evidence: list
    health_summary: list
    hypotheses: str


def _gather_gcp_evidence(cloud):
    project_id = cloud["project_id"]
    region = cloud["regions"][0]
    evidence = []
    for service_cfg in cloud.get("services", []):
        if service_cfg["type"] != "cloud_run":
            continue
        service = service_cfg["service"]
        evidence.append(tools.gcloud_run_describe(service, region, project_id))
        evidence.append(
            tools.gcloud_logging_read(
                project_id,
                f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service}" AND severity>=WARNING',
            )
        )
    return evidence


def _gather_aws_evidence(cloud):
    region = cloud["regions"][0]
    evidence = []
    for service_cfg in cloud.get("services", []):
        if service_cfg["type"] != "ecs":
            continue
        cluster = service_cfg["cluster"]
        service = service_cfg["service"]
        evidence.append(tools.aws_ecs_describe_service(cluster, service, region))
        evidence.append(tools.aws_ecs_list_tasks(cluster, service, region))
        evidence.append(tools.aws_logs_tail(f"/ecs/{service}", region))
    return evidence


_PROVIDER_GATHERERS = {
    "gcp": _gather_gcp_evidence,
    "aws": _gather_aws_evidence,
}


def _summarize_cloud_run_evidence(describe_result):
    summary = {"service": None, "healthy": None, "detail": None}
    if describe_result["returncode"] != 0:
        summary["healthy"] = False
        summary["detail"] = f"describe command failed: {describe_result['stderr'].strip()[:300]}"
        return summary
    try:
        data = json.loads(describe_result["stdout"])
    except (json.JSONDecodeError, KeyError):
        summary["detail"] = "describe output was not valid JSON; cannot assess health"
        return summary

    summary["service"] = data.get("metadata", {}).get("name")
    conditions = data.get("status", {}).get("conditions", [])
    ready = next((c for c in conditions if c.get("type") == "Ready"), None)
    if ready is None:
        summary["detail"] = "no 'Ready' condition found in service status"
        return summary
    summary["healthy"] = ready.get("status") == "True"
    summary["detail"] = ready.get("message") or f"Ready condition status: {ready.get('status')}"
    return summary


def _summarize_ecs_evidence(describe_result):
    summary = {"service": None, "healthy": None, "detail": None}
    if describe_result["returncode"] != 0:
        summary["healthy"] = False
        summary["detail"] = f"describe-services command failed: {describe_result['stderr'].strip()[:300]}"
        return summary
    try:
        services = json.loads(describe_result["stdout"]).get("services", [])
    except (json.JSONDecodeError, KeyError):
        summary["detail"] = "describe-services output was not valid JSON; cannot assess health"
        return summary
    if not services:
        summary["healthy"] = False
        summary["detail"] = "no service found matching that name in this cluster"
        return summary

    svc = services[0]
    summary["service"] = svc.get("serviceName")
    running, desired = svc.get("runningCount"), svc.get("desiredCount")
    deployments = svc.get("deployments", [])
    rollout_states = [d.get("rolloutState") for d in deployments]
    counts_known = running is not None and desired is not None

    if any(state == "FAILED" for state in rollout_states):
        summary["healthy"] = False
    elif counts_known:
        summary["healthy"] = running == desired
    else:
        summary["healthy"] = None  # insufficient data to assess

    summary["detail"] = (
        f"runningCount={running} desiredCount={desired}, deployment rolloutStates={rollout_states}"
    )
    return summary


def summarize_evidence(entry, evidence):
    """Deterministically extract explicit health signals from the raw evidence,
    rather than relying on a small local model to parse nested JSON correctly.

    The index arithmetic below (+=2 for cloud_run, +=3 for ecs) must stay in
    lockstep with how many evidence entries _gather_gcp_evidence/
    _gather_aws_evidence append per service — if those change, update here too.
    """
    summaries = []
    idx = 0
    for cloud in entry.get("clouds", []):
        provider = cloud.get("provider")
        for service_cfg in cloud.get("services", []):
            if provider == "gcp" and service_cfg["type"] == "cloud_run":
                summaries.append({**_summarize_cloud_run_evidence(evidence[idx]), "provider": "gcp"})
                idx += 2
            elif provider == "aws" and service_cfg["type"] == "ecs":
                summaries.append({**_summarize_ecs_evidence(evidence[idx]), "provider": "aws"})
                idx += 3
    return summaries


def _describe_services(entry):
    parts = []
    for cloud in entry.get("clouds", []):
        for service_cfg in cloud.get("services", []):
            parts.append(f"{cloud['provider']}:{service_cfg['type']}:{service_cfg.get('service')}")
    return ", ".join(parts)


def gather_evidence(state: InvestigatorState) -> InvestigatorState:
    entry = state["catalog_entry"]
    evidence = []

    for cloud in entry.get("clouds", []):
        gatherer = _PROVIDER_GATHERERS.get(cloud.get("provider"))
        if gatherer is None:
            continue
        evidence.extend(gatherer(cloud))

    service_evidence_count = len(evidence)
    health_summary = summarize_evidence(entry, evidence[:service_evidence_count])

    for repo in entry.get("repos", []):
        evidence.append(tools.gh_run_list(repo["url"].removeprefix("github.com/")))

    return {**state, "evidence": evidence, "health_summary": health_summary}


def rank_hypotheses(state: InvestigatorState, model=DEFAULT_MODEL) -> InvestigatorState:
    llm = ChatOllama(model=model, temperature=0)
    entry = state["catalog_entry"]

    prompt = HYPOTHESIS_PROMPT.format(
        project_id=entry["id"],
        services=_describe_services(entry),
        report=state["report"],
        health_summary=json.dumps(state["health_summary"], indent=2),
        evidence=state["evidence"],
    )
    response = llm.invoke(prompt)
    return {**state, "hypotheses": response.content}


def build_graph(model=DEFAULT_MODEL):
    graph = StateGraph(InvestigatorState)
    graph.add_node("gather_evidence", gather_evidence)
    graph.add_node("rank_hypotheses", lambda state: rank_hypotheses(state, model=model))
    graph.set_entry_point("gather_evidence")
    graph.add_edge("gather_evidence", "rank_hypotheses")
    graph.add_edge("rank_hypotheses", END)
    return graph.compile()


def investigate(
    report,
    catalog_entry,
    audit_log_path="audit/session.jsonl",
    evidence_db_path="audit/evidence.sqlite3",
    model=DEFAULT_MODEL,
):
    audit = AuditLog(audit_log_path)
    store = EvidenceStore(evidence_db_path)
    investigation_id = store.start_investigation(catalog_entry["id"], report)
    audit.record("investigation_started", report=report, project=catalog_entry["id"])

    app = build_graph(model=model)
    result = app.invoke({"report": report, "catalog_entry": catalog_entry})

    store.record_evidence(investigation_id, result["evidence"])
    store.record_health_summary(investigation_id, result["health_summary"])
    store.finish_investigation(investigation_id, result["hypotheses"])

    audit.record(
        "investigation_completed",
        project=catalog_entry["id"],
        hypotheses=result["hypotheses"],
    )
    return result["hypotheses"]
