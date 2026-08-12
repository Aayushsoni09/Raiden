"""The investigator agent loop.

Built on LangGraph's prebuilt ReAct agent, backed by a local Ollama model
(free, offline — no API costs). The model only ever sees the read-only
tools in src/investigator/tools.py; it cannot mutate any cloud state.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from src.audit import AuditLogger
from src.resolver import CatalogEntry
from .tools import READ_ONLY_TOOLS

DEFAULT_MODEL = os.environ.get("RAIDEN_MODEL", "llama3.1")
DEFAULT_BASE_URL = os.environ.get("RAIDEN_OLLAMA_URL", "http://localhost:11434")
MAX_REPAIR_ROUNDS = 3

TOOLS_BY_NAME = {t.name: t for t in READ_ONLY_TOOLS}

# Smaller local models sometimes describe a tool call as text/JSON instead of
# actually invoking the function-calling API. This regex detects that pattern
# so we can execute the call for real and feed the result back, rather than
# accepting hallucinated "I would run X" text as evidence.
_PSEUDO_CALL_RE = re.compile(
    r'\{\s*"name"\s*:\s*"(?P<name>\w+)"\s*,\s*"parameters"\s*:\s*(?P<params>\{.*?\})\s*\}',
    re.DOTALL,
)

SYSTEM_PROMPT = """You are Raiden, a DevOps incident investigator.

Tools available: aws_cli, gcloud_cli, kubectl_cli, gh_cli (all read-only —
describe/list/get/logs only). You CANNOT and must NEVER attempt to mutate,
delete, or modify any resource; no tool here can do that.

Project context:
{catalog_context}

IMPORTANT: call tools using function calling, one at a time, to gather
real evidence (what changed recently, current service health, recent
errors in logs). Do NOT write out a plan or describe tool calls as text
or JSON in your reply — actually invoke the function calling API. Only
write prose once you are giving your final answer.

Once you have enough evidence (or a tool call fails/isn't available and
you've tried reasonable alternatives), give your final answer in exactly
this format and nothing else:

HYPOTHESES:
1. <hypothesis> | confidence: <low|medium|high> | evidence: <short summary>
2. ...

Rank most-likely first. Be concise. If you lack evidence for a clean
hypothesis, say so plainly instead of guessing.
"""


@dataclass
class Hypothesis:
    rank: int
    description: str
    confidence: str
    evidence: str


@dataclass
class InvestigationResult:
    raw_answer: str
    hypotheses: list[Hypothesis] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)


def _catalog_context(entry: CatalogEntry) -> str:
    lines = [f"id: {entry.id}"]
    for cloud in entry.clouds:
        lines.append(
            f"- provider={cloud.get('provider')} account={cloud.get('account_id')} "
            f"regions={cloud.get('regions')} services={cloud.get('services')}"
        )
    if entry.domains:
        lines.append(f"domains: {entry.domains}")
    return "\n".join(lines)


def _parse_hypotheses(text: str) -> list[Hypothesis]:
    hypotheses: list[Hypothesis] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("HYPOTHESES"):
            in_block = True
            continue
        if not in_block or not stripped:
            continue
        # Expected: "1. <desc> | confidence: <x> | evidence: <y>"
        try:
            _, rest = stripped.split(".", 1)
            parts = [p.strip() for p in rest.split("|")]
            desc = parts[0]
            confidence = next((p.split(":", 1)[1].strip() for p in parts if p.lower().startswith("confidence")), "unknown")
            evidence = next((p.split(":", 1)[1].strip() for p in parts if p.lower().startswith("evidence")), "")
            rank = len(hypotheses) + 1
            hypotheses.append(Hypothesis(rank=rank, description=desc, confidence=confidence, evidence=evidence))
        except (ValueError, IndexError):
            continue
    return hypotheses


def _extract_pseudo_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Find any {"name": "...", "parameters": {...}} blobs in free text that
    should have been real tool calls but weren't."""
    calls = []
    if not isinstance(text, str):
        return calls
    for m in _PSEUDO_CALL_RE.finditer(text):
        name = m.group("name")
        if name not in TOOLS_BY_NAME:
            continue
        try:
            params = json.loads(m.group("params"))
        except json.JSONDecodeError:
            continue
        calls.append((name, params))
    return calls


class Investigator:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        audit_logger: AuditLogger | None = None,
        temperature: float = 0.1,
    ):
        self.llm = ChatOllama(model=model, base_url=base_url, temperature=temperature)
        self.agent = create_react_agent(self.llm, READ_ONLY_TOOLS)
        self.audit = audit_logger or AuditLogger()

    def investigate(self, catalog_entry: CatalogEntry, problem_statement: str) -> InvestigationResult:
        self.audit.log(
            "investigate.start",
            project=catalog_entry.id,
            problem_statement=problem_statement,
        )

        system = SYSTEM_PROMPT.format(catalog_context=_catalog_context(catalog_entry))
        current_messages = [SystemMessage(content=system), HumanMessage(content=problem_statement)]

        out_messages: list = []
        final_answer = ""

        for attempt in range(MAX_REPAIR_ROUNDS + 1):
            result = self.agent.invoke({"messages": current_messages})
            out_messages = result["messages"]
            final_answer = out_messages[-1].content or ""

            pseudo_calls = _extract_pseudo_tool_calls(final_answer)
            if not pseudo_calls or attempt == MAX_REPAIR_ROUNDS:
                break

            # Repair: the model described tool calls as text instead of
            # invoking them for real. Execute them ourselves and feed the
            # real results back so the model can't hallucinate evidence.
            self.audit.log(
                "investigate.repair",
                project=catalog_entry.id,
                attempt=attempt,
                pseudo_calls=[{"name": n, "params": p} for n, p in pseudo_calls],
            )
            current_messages = list(out_messages)
            for name, params in pseudo_calls:
                tool_fn = TOOLS_BY_NAME[name]
                try:
                    output = tool_fn.invoke(params)
                except Exception as e:  # tool itself should already catch errors, but be defensive
                    output = f"ERROR: {e}"
                current_messages.append(
                    HumanMessage(
                        content=(
                            f"[System note: you described a call to {name} as text instead of "
                            f"invoking it. It has been executed for you with params {params}. "
                            f"Real result:]\n{output}"
                        )
                    )
                )
            current_messages.append(
                HumanMessage(
                    content=(
                        "Continue the investigation using the real tool result(s) above. "
                        "Use the function-calling API for any further tool calls — do not "
                        "describe them as text/JSON. When you have enough evidence, answer "
                        "in the HYPOTHESES format."
                    )
                )
            )

        for msg in out_messages:
            self.audit.log(
                "investigate.step",
                project=catalog_entry.id,
                role=msg.__class__.__name__,
                content=str(msg.content)[:4000],
                tool_calls=getattr(msg, "tool_calls", None),
            )

        hypotheses = _parse_hypotheses(final_answer)
        self.audit.log(
            "hypothesis",
            project=catalog_entry.id,
            hypotheses=[h.__dict__ for h in hypotheses],
        )

        return InvestigationResult(
            raw_answer=final_answer,
            hypotheses=hypotheses,
            transcript=[{"role": m.__class__.__name__, "content": m.content} for m in out_messages],
        )



