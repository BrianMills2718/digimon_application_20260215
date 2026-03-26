# ADR-014: Consolidated Tool Surface for Benchmark Agents

**Status**: Accepted
**Date**: 2026-03-23

## Context

DIGIMON exposes 28 typed operators via ~67 individual MCP tools. Usage audit on benchmark runs showed agents overwhelmingly used only 2 tools (chunk_text_search, entity_vdb_search) and never touched graph-specific operators like PPR, decomposition, or subgraph extraction. The tool surface was drowning the routing agent.

Plan #15 consolidated the individual tools into 10 method-dispatched tools (e.g., `entity_search(method="semantic"|"string"|"tfidf")`). This reduced cognitive load and changed agent behavior dramatically — agents began using graph operators.

## Decision

1. **10 consolidated tools** are the default benchmark surface (`DIGIMON_CONSOLIDATED_TOOLS=1`).
2. **4 operators were restored** as methods on existing tools (commit 1bf7f83):
   - `entity_search(method="agent")` → `entity.agent`
   - `relationship_search(method="agent")` → `relationship.agent`
   - `subgraph_extract(method="agent")` → `subgraph.agent_path`
   - `chunk_retrieve(method="ppr_weighted")` → `chunk.aggregator`

   **3 operators still excluded** (no MCP wrapper implementations):
   - `entity.rel_node` — extract entity endpoints from relationships
   - `meta.reason_step` — iterative query refinement
   - `meta.rerank` — LLM re-scoring
3. **Legacy surface available** via `DIGIMON_CONSOLIDATED_TOOLS=0` for backward compatibility and access to excluded operators.
4. **`semantic_plan`**, **`todo_write`**, and **`bridge_disambiguate`** are available alongside consolidated tools. `semantic_plan` provides typed decomposition with dependencies; `todo_write` provides persistent progress tracking. Both were briefly removed (prompt v2.0) then restored (Plan #20) after diagnosis showed the agent needed working memory to prevent premature submission.

## Consequences

**Easier**: Agent uses graph operators. Behavioral evidence: relationship_search, entity_traverse, entity_info used consistently. Pre-rebuild 19q comparison: 52.6% vs 21.1% LLM-judge over baseline.

**Harder**: 3 operators are inaccessible in consolidated mode (no MCP wrappers). If chunk.aggregator or meta.rerank prove valuable, they need to be added to the consolidated surface. Any new operator added to Core/Operators/ needs a decision about whether it gets a consolidated method or stays legacy-only.

**Open question**: Should excluded operators be individually addable via config, or should they be grouped into a "power user" tier?
