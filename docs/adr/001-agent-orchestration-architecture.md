# ADR-001: Agent Orchestration Architecture

**Status**: Accepted
**Date**: 2026-02-15
**Context**: Phases 1-11 of the operator pipeline

## Decision

DIGIMON requires a **capable LLM** (Claude, Codex, or equivalent) for all agentic reasoning — both for orchestration (choosing how to build graphs, selecting retrieval methods, composing chains) and for mid-pipeline steps (entity extraction, iterative reasoning, answer generation). The default `agentic_model` must be a strong model, not gpt-4o-mini.

The system supports two orchestration modes that are **not mutually exclusive**:

1. **DIGIMON-internal brain** — A capable `agentic_model` handles orchestration and mid-pipeline reasoning. The client just sends a query and gets an answer.

2. **Client-as-brain** — When the client is itself a capable agent (Claude Code, Codex CLI), it can bypass DIGIMON's orchestration and drive directly — choosing graph types, picking retrieval methods, composing operator chains. Mid-pipeline LLM calls still use the internal `agentic_model`.

Which mode to use is **the client's choice**, and should be **configurable at runtime via MCP**.

## Context

### The two kinds of LLM work inside DIGIMON

**Orchestration** (can be done by client OR internal brain):
- Choosing which graph type to build (ER, RK, tree, passage)
- Selecting a retrieval method from the 10 named methods
- Composing custom operator chains
- Deciding what prerequisites to build

**Mid-pipeline agentic steps** (must be internal — client can't intervene):
- `meta.extract_entities` — LLM extracts entity mentions from a query
- `meta.reason_step` — LLM reasons about graph neighborhoods (tog, kgp loops)
- `meta.generate_answer` — LLM synthesizes a final answer from retrieved context
- `subgraph.agent_path` — LLM ranks candidate paths by relevance

The client can own orchestration but **cannot** own mid-pipeline steps — those happen inside PipelineExecutor without round-tripping. So DIGIMON always needs a capable internal model.

### Three MCP client modes

| Mode | Tool | Orchestration by | Mid-pipeline by |
|------|------|-----------------|-----------------|
| Full auto | `auto_compose(query, dataset)` | Internal brain | Internal brain |
| Named method | `execute_method(method, query, dataset)` | Client | Internal brain |
| Raw operators | Individual tools | Client | Internal brain |

### Why the internal brain must be capable

Mid-pipeline steps are retrieval-critical. A weak model doing entity extraction or iterative reasoning degrades the entire pipeline. tog's multi-hop exploration, hipporag's entity linking, kgp's neighborhood reasoning — all require strong LLM reasoning. gpt-4o-mini is not sufficient as a default.

### When a smart client should drive

A capable client (Claude Code, Codex) has advantages for orchestration:
- Full user-goal context — knows what the query is really asking
- Cross-system awareness — can coordinate DIGIMON with other tools
- Conversation history — can learn from previous retrieval failures

But DIGIMON's internal brain has advantages too:
- Deep knowledge of the operator catalog and method tradeoffs
- Can be a specialized model fine-tuned or prompted for retrieval decisions
- Simpler for the client — one tool call instead of multi-step reasoning

The right answer is: **let the client choose**. Expose the configuration through MCP so the client can delegate or override as it sees fit.

## Design

### Model roles

| Config field | Controls | Default |
|-------------|----------|---------|
| `llm.model` | Graph construction (entity/relationship extraction), community reports | `openai/gpt-4o-mini` (bulk extraction, cost-sensitive) |
| `agentic_model` | All agentic reasoning: auto_compose, meta operators, loop bodies | A capable model (Claude Sonnet, Codex, etc.) |

### MCP configuration exposure

The client must be able to:
1. **Inspect** active model configuration (`get_config` tool)
2. **Override** the agentic model at runtime (`set_agentic_model` tool)
3. **See** which model controls what (documented in MCP server instructions)

This lets a Claude Code client say: "use Codex for internal reasoning" (cheaper) or "use Sonnet" (higher quality) — without editing files on disk.

### Recommended usage patterns

**Capable client (Claude Code, Codex CLI)**:
- Use Mode 2 (`list_methods` + `execute_method`) for orchestration — client picks the method with full goal context
- Or use `auto_compose` when the client doesn't have strong opinions about retrieval strategy
- Optionally call `set_agentic_model` at session start to control cost/quality

**Simple client (script, webhook, automation)**:
- Use `auto_compose(query, dataset, auto_build=True)` — one call, full auto
- Internal brain handles everything

**Cost-sensitive setup**:
- `agentic_model`: cheaper-but-capable model (Codex) for internal reasoning
- Client: expensive model (Claude Code) for high-level orchestration
- `llm.model`: gpt-4o-mini for bulk graph extraction (cost-sensitive, high volume)

## Current State (2026-02-15)

- `agentic_model` is **commented out** in Config2.yaml — everything falls back to gpt-4o-mini
- No MCP tools for config inspection or runtime override
- Client is blind to what model handles agentic steps

## Action Items

1. Uncomment `agentic_model` in Config2.yaml with a capable default
2. Add `get_config` MCP tool
3. Add `set_agentic_model` MCP tool
4. Update MCP server instructions to document model roles and configuration
