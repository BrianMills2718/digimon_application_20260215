# ADR-014: Consolidated Tool Surface for Benchmark Agents

**Status**: Accepted
**Date**: 2026-03-23

## Context

DIGIMON exposes 28 typed operators via ~67 individual MCP tools. Usage audit on benchmark runs showed agents overwhelmingly used only 2 tools (chunk_text_search, entity_vdb_search) and never touched graph-specific operators like PPR, decomposition, or subgraph extraction. The tool surface was drowning the routing agent.

Plan #15 consolidated the individual tools into 10 method-dispatched tools (e.g., `entity_search(method="semantic"|"string"|"tfidf")`). This reduced cognitive load and changed agent behavior dramatically — agents began using graph operators.

## Decision

1. **10 consolidated tools** are the default benchmark surface (`DIGIMON_CONSOLIDATED_TOOLS=1`).
2. **7 specialized operators are intentionally excluded** from the consolidated surface:
   - `entity.agent` — LLM-scored entity candidates (ToG pipeline)
   - `entity.rel_node` — extract entity endpoints from relationships
   - `relationship.agent` — LLM-guided relation selection (ToG pipeline)
   - `subgraph.agent_path` — LLM-filter paths (ToG pipeline)
   - `chunk.aggregator` — PPR score propagation to chunks (HippoRAG path)
   - `meta.reason_step` — iterative query refinement
   - `meta.rerank` — LLM re-scoring

   These are excluded because: (a) ToG pipeline operators are a separate paradigm not yet benchmarked, (b) chunk.aggregator and meta.rerank are refinement operators that add complexity without clear value until the base pipeline is proven.
3. **Legacy surface available** via `DIGIMON_CONSOLIDATED_TOOLS=0` for backward compatibility and access to excluded operators.
4. **`bridge_disambiguate`** is the only non-consolidated control tool retained (useful for entity resolution ambiguity). `semantic_plan` and `todo_write` were removed to avoid contradicting the `reason(method="decompose")` workflow.

## Consequences

**Easier**: Agent uses graph operators. Behavioral evidence: relationship_search, entity_traverse, entity_info used consistently. Pre-rebuild 19q comparison: 52.6% vs 21.1% LLM-judge over baseline.

**Harder**: 7 operators are inaccessible in consolidated mode. If chunk.aggregator or meta.rerank prove valuable, they need to be added to the consolidated surface. Any new operator added to Core/Operators/ needs a decision about whether it gets a consolidated method or stays legacy-only.

**Open question**: Should excluded operators be individually addable via config, or should they be grouped into a "power user" tier?
