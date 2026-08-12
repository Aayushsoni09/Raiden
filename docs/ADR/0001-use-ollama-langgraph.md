# ADR-0001: Use local Ollama + LangGraph instead of Claude Code

## Status
Accepted

## Context
The original design (see README history) assumed a persistent Claude Code
session as the agent runtime. This is a paid, proprietary tool tied to an
Anthropic subscription/API. This project is a no-budget POC, so an
open-source, free-to-run alternative is required for the core agent loop.

## Decision
Use **Ollama** as the local LLM runtime (runs open models like Llama 3.1
or Qwen2.5 entirely offline, no API key, no per-token cost) combined with
**LangGraph** (open-source, Apache-2.0/MIT licensed agent orchestration
built on LangChain) to implement the investigator's ReAct-style tool-calling
loop.

Alternatives considered:
- **Open Interpreter** — open-source, executes commands via an LLM, but is
  designed for general-purpose local code execution rather than a strict
  read-only/write-separated tool set. Would need significant stripping down
  to match the safety model.
- **OpenHands (formerly OpenDevin)** — open-source autonomous agent, but
  oriented around software engineering tasks (editing repos, running
  sandboxed dev environments) rather than cloud CLI investigation; heavier
  than needed for this POC.
- **Custom loop with raw function-calling** — viable, but LangGraph already
  provides a maintained, tested `create_react_agent` primitive, saving
  reimplementation of the reasoning loop.

LangGraph + Ollama was chosen because it keeps the read-only tool
boundary explicit (tools are plain Python callables we control) while
avoiding any subscription cost.

## Consequences
- No API costs; fully offline capable once the model is pulled.
- Model quality is bounded by what runs locally (7B–8B class models by
  default); investigation depth may be lower than a frontier hosted model.
  `RAIDEN_MODEL` env var allows swapping to a larger local model if
  hardware allows.
- If a hosted model is later desired for higher quality, it must be gated
  behind `llm_egress_approved` per catalog entry (see THREAT_MODEL.md) —
  not done by default.

