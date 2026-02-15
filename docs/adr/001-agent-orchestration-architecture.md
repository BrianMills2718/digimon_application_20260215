# ADR-001: Agent Orchestration Architecture

**Status**: Accepted
**Date**: 2026-02-15
**Context**: Phases 1-11 of the operator pipeline

## Decision

DIGIMON supports **two orchestration modes** that are **not mutually exclusive**:

1. **DIGIMON-internal brain** — An `agentic_model` (configurable in Config2.yaml) handles mid-pipeline LLM calls and auto_compose method selection. This model should be capable (Claude, GPT-4o, Codex) because it makes retrieval-critical decisions.

2. **Client-as-brain** — A capable external agent (Claude Code, Codex CLI) calls DIGIMON's tools directly, choosing graph types, retrieval methods, and operator chains. The client bypasses auto_compose and drives via `execute_method` or individual operator tools.

The client can **delegate** orchestration to DIGIMON's internal brain (auto_compose) or **override** it (execute_method, individual operators). Both paths are always available.

## Context

The operator pipeline exposes 39 MCP tools across three client modes:

| Mode | Tool | Who decides |
|------|------|-------------|
| Full auto | `auto_compose(query, dataset)` | DIGIMON's internal brain |
| Named method | `execute_method(method, query, dataset)` | Client picks method |
| Raw operators | Individual tools (entity_vdb_search, etc.) | Client composes chain |

### Tension

The calling client (Claude Code / Codex CLI) is often a powerful LLM agent with full user-goal context. Having `auto_compose` make a **separate internal LLM call** to pick a retrieval method seems redundant when the client could just read `list_methods()` and pick.

But mid-pipeline agentic steps (meta.extract_entities, meta.reason_step, subgraph.agent_path, tog's iterative loop) **cannot** round-trip to the client. These happen inside PipelineExecutor and need an internal LLM.

### Arguments for DIGIMON-internal brain

- Knows the operator catalog, graph topology tradeoffs, and retrieval nuances intimately
- Mid-pipeline LLM calls (tog, hipporag, kgp) cannot be delegated to the client
- Auto_compose is a single tool call vs. the client needing two (list_methods + execute_method)
- Useful for simple/non-LLM clients (scripts, webhooks, cron jobs)

### Arguments for client-as-brain

- Has the user's full goal context — knows what the query is really asking
- Can make cross-system decisions (e.g., "query DIGIMON then feed results to investigative_wiki")
- Already a capable model — redundant to call a second LLM for method selection
- Can inspect `list_methods()` profiles and reason about method fit with full conversation context

## Design

### Configuration

```yaml
# Config2.yaml
llm:
  model: "openai/gpt-4o-mini"     # Default for graph building (extraction)
  api_key: "..."

# Separate model for agentic reasoning (mid-pipeline LLM + auto_compose).
# Should be capable. Falls back to llm.model if unset.
agentic_model: "anthropic/claude-sonnet-4-5-20250929"
```

`agentic_model` controls:
- `auto_compose` method selection
- All meta operators (extract_entities, reason_step, rerank, generate_answer)
- Loop-based reasoning in tog, kgp
- Any future agentic operators

`llm.model` controls:
- Graph construction (entity/relationship extraction during build)
- Community report generation

### Recommended usage patterns

**Capable client (Claude Code, Codex CLI)**:
- Use Mode 2 (`execute_method`) or Mode 3 (individual operators)
- Client reads `list_methods()`, reasons about method fit, picks the method
- Client can also use `auto_compose` when it doesn't want to think about method selection

**Simple client (script, webhook, automation)**:
- Use `auto_compose(query, dataset, auto_build=True)` — one call, full auto
- DIGIMON's internal brain handles everything

**Cost-sensitive setup**:
- Set `agentic_model` to a cheaper-but-capable model (e.g., Codex, gpt-4o-mini)
- Use expensive client (Claude Code) only for high-level orchestration
- DIGIMON handles internal reasoning cheaply

## Current State (2026-02-15)

### Defaults
- `llm.model`: `openai/gpt-4o-mini` — used for graph building (entity/relationship extraction)
- `agentic_model`: **commented out** (`None`) — all agentic/mid-pipeline LLM calls fall back to gpt-4o-mini
- This means tog's iterative reasoning, hipporag's entity extraction, auto_compose method selection, and answer generation all use gpt-4o-mini

### Configuration
- `Config2.yaml` is the only config file, edited on disk before server start
- `agentic_model` field exists in `Config2.py` (line 53) but is commented out in the YAML
- No runtime configuration — model choices are baked in at server startup

### MCP exposure
- **Not exposed.** The client cannot inspect or change model configuration through MCP tools.
- The client has no way to know what model is handling agentic steps
- The client cannot say "use Sonnet for reasoning" without editing Config2.yaml on disk

## Action Items

1. **Uncomment `agentic_model`** in Config2.yaml with a capable default
2. **Add `get_config` MCP tool** — client can inspect active models, working_dir, etc.
3. **Add `set_agentic_model` MCP tool** — client can override the agentic model at runtime (e.g., Claude Code says "use codex for internal reasoning, use sonnet for answer generation")
4. **Document in MCP server instructions** which model controls what

## Consequences

- `auto_compose` stays as a tool — useful for simple clients and as a fallback
- The MCP server instructions document all three modes so the client can choose
- Future raw chain composition (using `find_chains_to_goal()`) follows the same pattern: the client or the internal brain can drive it
- Runtime model configuration means the client can tune cost/quality tradeoffs per session
