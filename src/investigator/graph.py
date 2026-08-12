"""LangGraph investigator loop: read-only evidence gathering -> ranked hypotheses.

Uses a local Ollama model (e.g. llama3.1:8b or qwen2.5:7b) via langchain-ollama.
The investigator never calls write/mutating CLI commands.
"""

from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from src.audit import AuditLog
from src.investigator import tools

DEFAULT_MODEL = "llama3.1:8b"

HYPOTHESIS_PROMPT = """You are Raiden's investigator. You only read evidence; you never propose \
destructive or write actions directly to be run automatically.

Project: {project_id}
Services: {services}
Report: {report}

Evidence gathered:
{evidence}

Produce a ranked list of hypotheses for what went wrong. For each hypothesis include:
- statement
- supporting evidence
- disconfirming evidence (if any)
- confidence (low/medium/high)
"""


class InvestigatorState(TypedDict):
    report: str
    catalog_entry: dict
    evidence: list
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

    for repo in entry.get("repos", []):
        evidence.append(tools.gh_run_list(repo["url"].removeprefix("github.com/")))

    return {**state, "evidence": evidence}


def rank_hypotheses(state: InvestigatorState, model=DEFAULT_MODEL) -> InvestigatorState:
    llm = ChatOllama(model=model, temperature=0)
    entry = state["catalog_entry"]

    prompt = HYPOTHESIS_PROMPT.format(
        project_id=entry["id"],
        services=_describe_services(entry),
        report=state["report"],
        evidence=state["evidence"],
    )
    response = llm.invoke(prompt)
    return {**state, "hypotheses": response.content}


def build_graph():
    graph = StateGraph(InvestigatorState)
    graph.add_node("gather_evidence", gather_evidence)
    graph.add_node("rank_hypotheses", rank_hypotheses)
    graph.set_entry_point("gather_evidence")
    graph.add_edge("gather_evidence", "rank_hypotheses")
    graph.add_edge("rank_hypotheses", END)
    return graph.compile()


def investigate(report, catalog_entry, audit_log_path="audit/session.jsonl"):
    audit = AuditLog(audit_log_path)
    audit.record("investigation_started", report=report, project=catalog_entry["id"])

    app = build_graph()
    result = app.invoke({"report": report, "catalog_entry": catalog_entry})

    audit.record(
        "investigation_completed",
        project=catalog_entry["id"],
        hypotheses=result["hypotheses"],
    )
    return result["hypotheses"]
