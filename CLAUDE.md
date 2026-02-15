# CLAUDE.md - DIGIMON Implementation Guide

## CURRENT STATE: Modular Operator Pipeline (2026-02-14)

Branch `modular-operator-pipeline` implements a typed, composable operator system.
Old Retriever/Query classes have been deleted. The operator pipeline is the canonical system.

### Operator Pipeline Status
```
Phase 1:  Type System        [DONE] SlotTypes, OperatorDescriptor, GraphCapabilities
Phase 2:  Operators (24)     [DONE] 7 entity + 4 relationship + 3 chunk + 3 subgraph + 2 community + 5 meta
Phase 3:  Registry           [DONE] OperatorRegistry with composition helpers
Phase 4:  Composition Engine [DONE] ChainValidator, PipelineExecutor, Adapters
Phase 5:  Method Plans (10)  [DONE] All 10 methods expressed as ExecutionPlans, all validate
Phase 6:  Graph Capabilities [DONE] BaseGraph.capabilities property
Phase 7:  QA Evaluation      [DONE] New pipeline 50% vs old 30% on HotPotQA (10 questions)
Phase 8:  Delete Old System  [DONE] Core/Retriever/ and Core/Query/ deleted, references cleaned up
Phase 9:  MCP Composition    [DONE] MCP tools, execute_method, auto_build for VDBs
Phase 10: Full Auto-Build    [DONE] build_sparse_matrices + build_communities tools; 10/10 methods pass with auto_build=True
Phase 11: Auto-Compose       [DONE] auto_compose MCP tool — LLM picks best method from 10 based on query + resources
```

### Key Architecture: Operator Pipeline

**Uniform operator signature** (all 24 operators):
```python
async def op(inputs: Dict[str, SlotValue], ctx: OperatorContext, params: Dict) -> Dict[str, SlotValue]
```

**Key files**:
- `Core/Schema/SlotTypes.py` — 7 SlotKinds + typed records (EntityRecord, RelationshipRecord, etc.)
- `Core/Schema/OperatorDescriptor.py` — Machine-readable operator metadata
- `Core/Operators/` — 24 operators in entity/, relationship/, chunk/, subgraph/, community/, meta/
- `Core/Operators/registry.py` — OperatorRegistry with composition helpers
- `Core/Composition/` — ChainValidator, PipelineExecutor, Adapters, auto_compose
- `Core/Methods/` — 10 method plans (basic_local, fastgraphrag, hipporag, tog, gr, dalk, kgp, med, etc.)
- `Core/AgentSchema/plan.py` — Extended with LoopConfig, ConditionalBranch

**Operator registry** (24 operators across 6 categories):
```
entity:       vdb, ppr, onehop, link, tfidf, agent, rel_node
relationship: onehop, vdb, score_agg, agent
chunk:        from_relation, occurrence, aggregator
subgraph:     khop_paths, steiner_tree, agent_path
community:    from_entity, from_level
meta:         extract_entities, reason_step, rerank, generate_answer, pcst_optimize
```

**Composition helpers**:
- `REGISTRY.get_compatible_successors("entity.ppr")` — 13 compatible operators
- `REGISTRY.find_chains_to_goal({QUERY_TEXT}, CHUNK_SET)` — 95 valid chains at depth 3
- `ChainValidator.validate(plan)` — validates all I/O connections in an ExecutionPlan

### MCP Agent Composition (2026-02-14)

**Status**: Complete. All 24 operators + 10 method pipelines accessible via MCP.

**Orchestration architecture** (see `docs/adr/001-agent-orchestration-architecture.md`):
Two non-exclusive modes — DIGIMON's internal brain (`agentic_model`) handles mid-pipeline
LLM calls and auto_compose; a capable client (Claude Code, Codex) can override and drive
directly via execute_method or individual operators. Both are always available.

**New components**:
- `Core/Provider/LLMClientAdapter.py` — wraps `llm_client.acall_llm` behind BaseLLM interface
- `Core/Composition/OperatorComposer.py` — method profiling, plan building, execution
- `Core/Composition/auto_compose.py` — LLM-driven method selection (CompositionDecision, select_method)
- `prompts/auto_compose.yaml` — Jinja2 template for method selection prompt
- `Option/Config2.py` — `agentic_model` field for separate LLM for meta operators

**MCP tools (43 total)**:
- 5 graph build (er, rk, tree, tree_balanced, passage) + 1 corpus (prepare)
- 7 entity (vdb_build, vdb_search, onehop, ppr, agent, link, tfidf)
- 5 relationship (onehop, score_agg, agent, vdb_build, vdb_search)
- 4 chunk (from_relationships, occurrence, get_text, aggregator)
- 2 graph analysis (analyze, visualize) + 3 subgraph (khop_paths, steiner_tree, agent_path)
- 3 community (build_communities, detect_from_entities, get_layer)
- 3 meta (extract_entities, generate_answer, pcst_optimize)
- 1 prerequisite build (build_sparse_matrices)
- 2 config (get_config, set_agentic_model)
- 2 operator discovery (list_operators, get_compatible_successors)
- 4 method-level (list_methods, list_graph_types, execute_method, auto_compose)
- 1 context (list_available_resources)

**Three execution modes** (increasing control):
1. Individual operator tools — client composes the pipeline using `list_operators` + `get_compatible_successors`
2. `execute_method("basic_local", query, dataset, auto_build=True)` — client picks from 10 methods
3. `auto_compose(query, dataset, auto_build=True)` — full auto, DIGIMON picks the method

**Auto-build** (`auto_build=True` on execute_method):
- Automatically builds all missing prerequisites: entity VDB, relationship VDB,
  sparse matrices, and community structure
- Community building calls LLM (most expensive auto-build step)
- Default: `False` (existing behavior unchanged)
- All 10 methods work with `auto_build=True` given a built graph

**Multi-model config**:
```yaml
agentic_model: "gemini/gemini-2.0-flash"  # for meta operators (default)
```
Graph building uses `llm` (cheap/fast), meta operators use `agentic_model` (capable).
Use `get_config` to inspect, `set_agentic_model` to override at runtime.

### Previous Work: MCP Integration

MCP server, client manager, context store, and tool migration complete (checkpoints 1.1-2.3).
Operator pipeline phases 1-10 complete. All 10 retrieval methods fully operational via MCP.

---

## Quick Reference

### Test Datasets
- `Data/Social_Discourse_Test`: Best for testing (10 actors, 20 posts, rich network)
- `Data/Synthetic_Test`: Good for VDB testing
- `Data/MySampleTexts`: Historical documents

### Current Environment
- Model: o4-mini (OpenAI)
- Embeddings: text-embedding-3-small
- Vector DB: FAISS
- Working directory: /home/brian/digimon_cc
- Python: 3.10+ with conda environment 'digimon'

### Method Plans (10 methods as ExecutionPlans)
```
basic_local:   entity.vdb → relationship.onehop → chunk.occurrence → generate_answer
basic_global:  community.from_level → generate_answer
lightrag:      relationship.vdb → entity.rel_node → chunk.from_relation → generate_answer
fastgraphrag:  entity.vdb → entity.ppr → relationship.score_agg → chunk.aggregator
hipporag:      extract_entities → entity.link → entity.ppr → chunk.aggregator
tog:           extract_entities → entity.link → Loop(relationship.agent → entity.agent) → chunk.from_relation → generate_answer
gr:            entity.vdb + relationship.vdb → meta.pcst_optimize → chunk.from_relation → generate_answer
dalk:          extract_entities → entity.link → subgraph.khop_paths → subgraph.agent_path → chunk.from_relation → generate_answer
kgp:           entity.tfidf → Loop(entity.onehop → reason_step → entity.tfidf) → chunk.occurrence → generate_answer
med:           entity.vdb → subgraph.khop_paths → subgraph.steiner_tree → relationship.onehop → chunk.from_relation → generate_answer
```

### Known Limitations
- Entity.PPR: The operator implementation uses direct graph PPR (not the old EntityRetriever path)
- Entity.Link needs an entity VDB built first (graceful degradation without one)
- Community operators require `build_communities` to be run first (or `auto_build=True`)
- SteinerTree extracts connected component before running (NetworkX 3.3 workaround)

### Graph Building Pipeline Fix (2026-02-14)

**Status**: Fixed and verified. ERGraph now produces 640 nodes, 578 edges on HotPotQA (was 0/0).

**Root causes fixed**:
1. **LiteLLMProvider JSON mode**: `format="json"` now sets `response_format: {"type": "json_object"}` so GPT-4o-mini returns clean JSON
2. **JSON parsing**: `prase_json_from_response` rewritten with 3 strategies (fence stripping, stack-based matching, regex fallback)
3. **Corpus loading**: ChunkFactory now reads both `"content"` and `"context"` keys from corpus JSONL
4. **Ontology generation**: Now opt-in via `auto_generate_ontology: bool = False` in GraphConfig
5. **Encoder/tokenizer mismatch**: ERGraph wraps embedding models with TokenizerWrapper when they lack `.decode()`

**Architecture: Three attribute levels**:

| Attribute | KG (two-step) | TKG (delimiter) | RKG (delimiter+kw) |
|-----------|:---:|:---:|:---:|
| Entity Name | Y | Y | Y |
| Entity Type | | Y | Y |
| Entity Description | | Y | Y |
| Relation Name | Y | Y | Y |
| Relation Keywords | | | Y |
| Relation Description | | Y | Y |
| Edge Weight | Y | Y | Y |

- `extract_two_step=False` (default): ENTITY_EXTRACTION delimiter-based extraction (TKG-level) — extracts entity types, descriptions, relation descriptions
- `extract_two_step=True`: NER + OpenIE JSON-based extraction (KG-level) — names and relations only, no descriptions
- `extract_two_step=False` + `enable_edge_keywords=True`: RKG-level with keywords

**Shared code**: `DelimiterExtractionMixin` (Core/Graph/DelimiterExtraction.py) used by both ERGraph and RKGraph.

**Test results**:
- `test_hotpotqa.py`: 8/9 PASS (640 nodes, 578 edges)
- `test_operators.py`: 11/11 PASS (no regressions)
- `test_llm_operators.py`: 4/4 PASS (no regressions)
- TKG extraction verified: 55 nodes, 52 edges from 5 chunks

---

## Architecture Overview

### Operator Pipeline (canonical system):
- **Type System**: `Core/Schema/SlotTypes.py`, `OperatorDescriptor.py`, `GraphCapabilities.py`
- **24 Operators**: `Core/Operators/{entity,relationship,chunk,subgraph,community,meta}/`
- **Registry**: `Core/Operators/registry.py` — OperatorRegistry with composition helpers
- **Composition**: `Core/Composition/` — ChainValidator, PipelineExecutor, Adapters, OperatorComposer
- **Method Plans**: `Core/Methods/` — 10 method plans as ExecutionPlan factories
- **Plan Extensions**: `Core/AgentSchema/plan.py` — LoopConfig, ConditionalBranch

### Key Components:
- **Orchestrator**: `Core/AgentOrchestrator/orchestrator.py`
- **Tool Registry**: `Core/AgentTools/tool_registry.py`
- **GraphRAGContext**: `Core/AgentSchema/context.py`
- **Graph Classes**: ERGraph, RKGraph, TreeGraph, PassageGraph (unchanged)
- **Storage**: NetworkXStorage, TreeGraphStorage (unchanged)
- **VDB**: FaissIndex (unchanged)
- **GraphRAG**: `Core/GraphRAG.py` — uses `_OperatorPipelineQuerier` for query()

---

## Next Steps

### Phase 11: Auto-Compose (DONE)
LLM-driven method selection via `auto_compose` MCP tool. An LLM picks from the 10 named methods
based on query characteristics and available resources, then executes the selected pipeline.
- `Core/Composition/auto_compose.py` — `select_method()` renders prompt, calls `acall_llm_structured`, returns `CompositionDecision`
- `prompts/auto_compose.yaml` — Jinja2 template with method profiles, resources, and selection rules
- Uses `llm_client.render_prompt()` + `llm_client.acall_llm_structured()` with Pydantic extraction
- Falls back to `basic_local` on any LLM failure (invalid method name, extraction error, etc.)
- `list_available_resources` enhanced with community + sparse matrix availability
- **Design decision**: Pick from 10 tested methods, not compose raw chains (2054 valid chains at depth 4 is too many for LLM evaluation)

### Phase 12: Multi-Dataset Composition
`OperatorContext` is monolithic — all operators share one graph, one VDB set. This blocks:
- Cross-dataset queries (e.g., "compare entities in dataset A vs dataset B")
- Graph merging / federation
- **What's needed**: Either per-step context overrides in `ExecutionPlan`, or a multi-context executor that can bind different graphs to different steps

### Phase 13: QA Benchmarking
Tune retrieval parameters, benchmark operator chains (not just the 10 named methods) on HotPotQA and other datasets. Use `test_custom_chain.py` pattern to test novel chains against ground truth.
