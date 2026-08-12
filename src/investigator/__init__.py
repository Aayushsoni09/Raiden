"""src/investigator — the read-only agent loop.

Wraps aws/gcloud/kubectl/gh CLIs as read-only tools, calls a local LLM
(via Ollama) through LangGraph to reason over the evidence, and produces
ranked hypotheses. This process never holds write credentials in the
LLM's tool set — see src/executor for anything that mutates state.
"""
from .agent import Investigator, Hypothesis
from .tools import READ_ONLY_TOOLS, ToolExecutionError

__all__ = ["Investigator", "Hypothesis", "READ_ONLY_TOOLS", "ToolExecutionError"]

