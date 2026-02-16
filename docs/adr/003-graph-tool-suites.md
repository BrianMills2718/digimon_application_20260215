# ADR-003: Three Graph Tool Suites — Creation, Retrieval, Mutation

**Status**: Proposed
**Date**: 2026-02-16
**Context**: DIGIMON has 53 MCP tools and 27 operators covering graph creation and read-only retrieval. Graph mutation (update, delete, belief revision) is absent. Onto-canon has working belief revision but operates on SQLite, not NetworkX. This ADR defines the complete tool architecture across three suites.

---

## Problem

1. **No graph mutation**. All 27 operators are read-only. The storage layer has `upsert_node`/`upsert_edge` (used during build) but no `delete_node`, `delete_edge`, or selective update. Once a graph is built, the only mutation is `clear()` (wipe everything).

2. **No structured query language**. All retrieval is operator-based (PPR, VDB search, k-hop). There is no way to express ad-hoc graph patterns like "find all PERSON nodes connected to ORGANIZATION nodes via EMPLOYED_BY edges." Operators compose well but can't express arbitrary pattern matching.

3. **No belief revision on graphs**. Onto-canon has `canon_update_belief`, `canon_find_tensions`, `canon_resolve_tension` operating on SQLite beliefs. These don't apply to DIGIMON's NetworkX graphs. An edge added during extraction can't be weakened, retracted, or superseded without rebuilding.

4. **Creation tools lack post-build enrichment**. Graph building goes straight from LLM extraction to persistence. No entity canonicalization, no Q-code resolution, no schema validation (see ADR-002).

---

## Decision

Organize all graph tools into three suites. Each suite has clear boundaries for what EXISTS today vs what is PROPOSED.

### Suite 1: Creation (Graph Building)

Tools that construct graphs from source documents.

#### EXISTS Today (7 MCP tools)

| Tool | What it does |
|------|-------------|
| `corpus_prepare` | Convert files (.txt, .md, .json, .csv, .pdf) to DIGIMON corpus format |
| `graph_build_er` | Build entity-relationship graph (TKG) |
| `graph_build_rk` | Build rich keyword graph (RKG) |
| `graph_build_tree` | Build hierarchical chunk tree |
| `graph_build_tree_balanced` | Build balanced chunk tree |
| `graph_build_passage` | Build passage-level graph |
| `entity_vdb_build` | Build vector database index from graph entities |

Supporting infrastructure:
- `LLMClientAdapter` wraps `llm_client.acall_llm` with fallback chain (Fix 3, implemented)
- Checkpointing: partial graph persisted after each batch (Fix 1, implemented)
- `ERGraph._build_graph` processes chunks in batches of 50 via `asyncio.gather`

#### PROPOSED (from ADR-002)

| Enhancement | Description | Depends on |
|-------------|-------------|------------|
| **Prompts as data** | Move extraction prompts from `GraphPrompt.py` to YAML/Jinja2 templates. Graph type config selects template. | Nothing |
| **Ontology modes** | `open`/`closed`/`mixed` entity and relation type constraints in extraction prompts | Prompts as data |
| **Entity canonicalization** | Post-build LLM fuzzy dedup. Reuse `onto-canon/concept_dedup.py` logic on NetworkX graph directly. | Nothing |
| **Q-code resolution** | Post-build Wikidata entity disambiguation via `onto-canon/wikidata_entity_search.py` | Entity canonicalization |
| **Schema validation** | Post-build rejection/flagging of out-of-schema types (closed/mixed mode) | Ontology modes |
| **Reified graph type** | New extraction template + JSON parser for event-as-node diamond pattern (n-ary relationships) | Prompts as data |

---

### Suite 2: Retrieval (Graph Querying)

Tools that read graphs to answer questions. All read-only.

#### EXISTS Today (27 operators + 10 methods + 4 cross-modal + composition tools)

**27 Operators** (uniform signature: `async op(inputs, ctx, params) -> outputs`):

| Category | Operators | What they do |
|----------|-----------|-------------|
| **Entity** (7) | `vdb_search`, `ppr`, `onehop`, `link`, `tfidf`, `agent`, `rel_node` | Find relevant entities via vector search, PageRank, traversal, linking, TF-IDF, LLM reasoning |
| **Relationship** (4) | `onehop`, `vdb_search`, `score_aggregator`, `agent` | Find and score relationships between entities |
| **Chunk** (4) | `from_relationships`, `occurrence`, `aggregator`, `text_search` | Retrieve source text chunks via graph edges, co-occurrence, aggregation |
| **Subgraph** (3) | `khop_paths`, `steiner_tree`, `agent_path` | Extract subgraphs: k-hop neighborhoods, Steiner trees, LLM-guided paths |
| **Community** (2) | `from_entities`, `from_level` | Community detection from entity sets or hierarchy levels |
| **Meta** (7) | `extract_entities`, `reason_step`, `rerank`, `generate_answer`, `pcst_optimize`, `decompose_question`, `synthesize_answers` | Query preprocessing, reasoning, reranking, answer generation, AoT decomposition |

**10 Reference Methods** (pre-composed operator chains):

| Method | Pipeline |
|--------|----------|
| `basic_local` | extract_entities → entity.onehop → rel.onehop → chunk.from_rel → generate_answer |
| `basic_global` | extract_entities → community.from_level → chunk.aggregator → generate_answer |
| `ppr_based` | extract_entities → entity.ppr → rel.onehop → chunk.from_rel → generate_answer |
| `vdb_only` | extract_entities → entity.vdb → chunk.from_rel → generate_answer |
| `steiner_optimized` | extract_entities → entity.vdb → subgraph.steiner → chunk.from_rel → generate_answer |
| `comprehensive` | extract_entities → entity.vdb+ppr → rel.score_agg → subgraph.steiner → chunk.aggregator → generate_answer |
| `entity_focused` | extract_entities → entity.vdb → entity.ppr → rel.onehop → chunk.occurrence → generate_answer |
| `hipporag_style` | extract_entities → entity.link → entity.ppr → rel.onehop → chunk.occurrence → generate_answer |
| `lightrag_style` | extract_entities → entity.vdb → rel.vdb → chunk.from_rel → generate_answer |
| `aot_reasoning` | decompose_question → [per-sub-question: entity.vdb → rel.onehop → chunk.from_rel → generate_answer] → synthesize_answers |

**4 Cross-Modal Tools**:

| Tool | What it does |
|------|-------------|
| `convert_modality` | Convert data between graph, table, and vector representations |
| `validate_conversion` | Measure round-trip preservation quality |
| `select_analysis_mode` | LLM recommends best modality for a research question |
| `list_modality_conversions` | Discover all 15 conversion paths |

**Composition & Discovery Tools**:

| Tool | What it does |
|------|-------------|
| `list_operators` | Full operator catalog with I/O types |
| `get_compatible_successors` | Given an operator, list valid next operators |
| `execute_method` | Run a named reference method end-to-end |
| `auto_compose` | LLM picks best method based on query characteristics |
| `list_methods` | List all 10 reference methods with profiles |
| `get_config` / `set_agentic_model` | Runtime configuration |
| `list_available_resources` | What graphs and VDBs exist on disk |

#### PROPOSED

| Enhancement | Description | Complexity |
|-------------|-------------|------------|
| **Cypher-like pattern matching** | Express ad-hoc graph patterns: `MATCH (p:Person)-[:EMPLOYED_BY]->(o:Org) RETURN p, o`. Compiles to NetworkX traversal under the hood. Not full Neo4j Cypher — a subset covering node type filters, edge type filters, variable-length paths, and property constraints. | Medium — needs parser + NetworkX query compiler. Consider using `networkx-query` or writing a minimal pattern matcher. |
| **SPARQL endpoint** | RDF export + SPARQL query. | Low priority — Cypher-like covers most needs. Defer unless academic publication requires it. |
| **Graph statistics tool** | Node/edge counts, degree distribution, connected components, diameter, density — basic NetworkX analytics exposed as MCP tool. Currently requires raw Python. | Low — mostly wrapping `nx.degree_histogram()`, `nx.number_connected_components()`, etc. |

---

### Suite 3: Analysis & Mutation (Graph Maintenance)

Tools that modify existing graphs: add/update/delete nodes and edges, revise beliefs, maintain quality.

#### EXISTS Today

**In DIGIMON storage layer (not exposed as MCP tools):**

| Method | Location | What it does |
|--------|----------|-------------|
| `upsert_node(id, data)` | `NetworkXStorage` | Add or update a node |
| `upsert_edge(src, tgt, data)` | `NetworkXStorage` | Add or update an edge |
| `_merge_nodes_then_upsert()` | `BaseGraph` | Merge multiple observations of same entity |
| `_merge_edges_then_upsert()` | `BaseGraph` | Merge multiple observations of same edge |
| `augment_graph_by_similarity_search()` | `BaseGraph` | Add similarity edges from VDB |
| `cluster_data_to_subgraphs()` | `BaseGraph` | Write community assignments to nodes |
| `clear()` | `NetworkXStorage` | Wipe entire graph |
| `persist()` | `NetworkXStorage` | Write graph to GraphML file |

**In onto-canon (operates on SQLite beliefs, not NetworkX):**

| Tool | What it does |
|------|-------------|
| `canon_update_belief` | Bayesian logit-space belief update with likelihood ratios |
| `canon_find_tensions` | Detect contradictory beliefs (opposing predicates, conflicting values) |
| `canon_resolve_tension` | Resolve contradiction: QUALIFY, WEAKEN, RETRACT, or SUPERSEDE |
| `canon_merge_concepts` | Merge duplicate concepts (redirect FKs + delete) |
| `canon_prune_orphans` | Find/remove concepts with zero non-system beliefs |
| `canon_import_digimon_graph` | Import DIGIMON graph dict → onto-canon concepts+beliefs |
| `canon_export_digimon_graph` | Export onto-canon beliefs → DIGIMON graph dict |
| `canon_run_governance` | Discover, validate, promote predicates to ontology |

**In `graph_analyze` operator (read-only analysis, exposed as MCP):**

| Tool | What it does |
|------|-------------|
| `graph_analyze` | Centrality, community stats, path analysis on existing graph |
| `graph_visualize` | Generate graph visualization |

#### DOES NOT EXIST (gaps)

| Gap | Impact |
|-----|--------|
| **No `delete_node` / `delete_edge`** | Can't remove incorrect extractions without rebuilding |
| **No selective update MCP tool** | `upsert_node`/`upsert_edge` exist in storage but aren't exposed as tools |
| **No belief revision on NetworkX** | Onto-canon's epistemic engine operates on SQLite; no equivalent for NetworkX graphs |
| **No edge retraction/weakening** | An incorrect extraction stays in the graph forever |
| **No provenance-aware deletion** | Can't say "remove all edges from chunk X" (e.g., if source was retracted) |
| **No graph diff / versioning** | Can't compare graph states before/after mutation |
| **No undo / rollback** | Mutations are permanent; no transaction log |

#### PROPOSED

**Tier 1: Basic Mutation Tools** (expose existing storage methods as MCP tools)

| Tool | Description | Implementation |
|------|-------------|----------------|
| `graph_upsert_node` | Add or update a node with attributes | Thin wrapper around `NetworkXStorage.upsert_node` + `persist` |
| `graph_upsert_edge` | Add or update an edge with attributes | Thin wrapper around `NetworkXStorage.upsert_edge` + `persist` |
| `graph_delete_node` | Remove a node and all its edges | Add `delete_node` to `NetworkXStorage` using `nx.Graph.remove_node`, expose as tool |
| `graph_delete_edge` | Remove a specific edge | Add `delete_edge` to `NetworkXStorage` using `nx.Graph.remove_edge`, expose as tool |
| `graph_delete_by_source` | Remove all nodes/edges from a specific source chunk | Filter by `source_id` attribute, bulk delete |

**Tier 2: Belief Revision on NetworkX**

Two architectural options:

**Option A: Round-trip through onto-canon** (reuse existing epistemic engine)
```
DIGIMON graph → canon_import_digimon_graph → [belief operations in SQLite] → canon_export_digimon_graph → DIGIMON graph
```
- Pro: Reuses all existing onto-canon tools (update_belief, find_tensions, resolve_tension, merge_concepts)
- Con: Lossy round-trip (see `DIGIMON_ATTRIBUTE_MAPPING.md` — keywords, clusters, multi-source_ids lost)
- Con: Performance cost of serialization + SQLite I/O + deserialization
- Best for: Periodic deep analysis, not real-time graph maintenance

**Option B: Lightweight edge-level epistemic state on NetworkX** (new)
```python
# Add epistemic attributes to edges during build or post-build
edge_data = {
    "relation_name": "employed_by",
    "weight": 0.85,
    "status": "active",         # active | weakened | retracted
    "probability": 0.85,        # [0.005, 0.995]
    "source_ids": ["chunk_42"],
    "extraction_count": 3,      # how many chunks produced this edge
}
```
- New MCP tools: `graph_weaken_edge`, `graph_retract_edge`, `graph_find_tensions`
- Reuse `belief_ops.py` math (logit updates, status transitions) but apply to NetworkX edge attributes
- Pro: Fast, no serialization overhead, graph stays in memory
- Con: Simpler model than onto-canon (no meta-beliefs, no supersession chains, no provenance DAG)
- Best for: Real-time graph maintenance during or after retrieval

**Recommendation**: Both. Option A for deep epistemic analysis (periodic). Option B for lightweight graph hygiene (continuous). They serve different use cases.

**Tier 3: Graph Versioning**

| Tool | Description |
|------|-------------|
| `graph_snapshot` | Save named snapshot (copy GraphML file with timestamp) |
| `graph_diff` | Compare two snapshots: added/removed/modified nodes and edges |
| `graph_restore` | Restore graph from a named snapshot |

This enables safe experimentation: snapshot before mutation, diff to verify, restore if wrong.

---

## Integration Architecture

### How the Three Suites Connect

```
                    ┌─────────────────────────────────────┐
                    │         Agent Brain (Client)         │
                    │   Claude Code / Codex / OpenClaw     │
                    └──────────┬──────────┬──────────┬─────┘
                               │          │          │
                    ┌──────────▼──┐ ┌─────▼─────┐ ┌─▼──────────┐
                    │  Suite 1:   │ │  Suite 2:  │ │  Suite 3:   │
                    │  Creation   │ │  Retrieval │ │  Mutation   │
                    ├─────────────┤ ├────────────┤ ├─────────────┤
                    │corpus_prepare│ │27 operators│ │upsert/delete│
                    │graph_build_* │ │10 methods  │ │belief ops   │
                    │entity_vdb_*  │ │cross-modal │ │governance   │
                    │[post-build]  │ │[cypher]    │ │[versioning] │
                    └──────┬──────┘ └─────┬──────┘ └──────┬──────┘
                           │              │               │
                    ┌──────▼──────────────▼───────────────▼──────┐
                    │              NetworkX Graph                 │
                    │         (GraphML persistence)              │
                    └──────────────────┬─────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │   Onto-Canon    │
                              │   (SQLite DB)   │
                              │                 │
                              │ Deep epistemic  │
                              │ analysis when   │
                              │ needed          │
                              └─────────────────┘
```

### DIGIMON ↔ Onto-Canon Boundary

| Concern | Lives in DIGIMON | Lives in Onto-Canon |
|---------|-----------------|-------------------|
| Graph storage | NetworkX + GraphML | SQLite (concepts, beliefs) |
| Entity dedup (lightweight) | `clean_str()` during build | — |
| Entity dedup (deep) | Post-build step calling onto-canon logic | `concept_dedup.py` (LLM fuzzy) |
| Belief state (lightweight) | Edge attributes: status, probability | — |
| Belief state (deep) | — | Full epistemic engine: logit math, tensions, resolution, meta-beliefs |
| Provenance | `source_id` attribute on nodes/edges | `evidence` table + `evidence_concepts` + `artifact_lineage` |
| Ontology constraints | Prompt-level (open/closed/mixed) | `predicate_proposals` + governance pipeline |
| Q-codes | Post-build enrichment attribute | Wikidata entity search + disambiguation |

---

## Implementation Order

1. **Basic mutation tools** — Expose `upsert_node`/`upsert_edge` as MCP tools. Add `delete_node`/`delete_edge` to `NetworkXStorage`. ~100 lines.

2. **Graph statistics tool** — Wrap `nx.info()`, degree distribution, component analysis as MCP tool. ~50 lines.

3. **Lightweight belief state** — Add `status`/`probability` attributes to edges during build. Expose `graph_weaken_edge`/`graph_retract_edge` MCP tools using `belief_ops.py` math. ~200 lines.

4. **Post-build entity canonicalization** — The ADR-002 step 3. Most immediate quality improvement.

5. **Graph versioning** — Snapshot/diff/restore. ~150 lines.

6. **Cypher-like pattern matching** — Evaluate `networkx-query` library or write minimal pattern compiler. ~300 lines.

7. **Deep epistemic round-trip** — Optimize `canon_import_digimon_graph`/`canon_export_digimon_graph` to reduce round-trip data loss.

---

## Consequences

**Positive:**
- Complete lifecycle: build → query → maintain → revise
- Mutation tools enable iterative graph refinement without full rebuild
- Lightweight belief state enables real-time quality tracking
- Versioning enables safe experimentation
- Cypher-like queries enable ad-hoc pattern matching beyond fixed operators

**Negative:**
- Two belief systems (NetworkX edge attributes vs onto-canon SQLite) creates consistency risk
- Mutation tools without versioning are dangerous (no undo)
- Cypher compiler adds parsing complexity

**Risks:**
- Lightweight belief state on NetworkX may diverge from onto-canon's epistemic model over time
- Delete operations on graphs may invalidate VDB indices (need rebuild trigger)
- Pattern matching performance on large graphs (>50K nodes) may be slow without indexing

---

## References

- ADR-001: Agent Orchestration Architecture (orchestration modes)
- ADR-002: Universal Graph Schema and Configurable Extraction (creation enhancements)
- `onto-canon/docs/core/UNIVERSAL_KG_VISION.md` (superset attribute schema)
- `onto-canon/docs/core/DIGIMON_ATTRIBUTE_MAPPING.md` (round-trip mapping)
- `project-meta/vision/UNIFIED_PLAN.md` (155 FRs, prioritized work items)
