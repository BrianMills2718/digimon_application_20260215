# CLAUDE.md — DIGIMON

## What This Is

DIGIMON is a knowledge-graph-based retrieval system with **28 typed, composable operators** that agents compose into retrieval DAGs at runtime. The agent decides what operators to call based on the question and intermediate results. There are no fixed pipelines.

**Thesis**: Adaptive operator-routing over graph retrieval — selecting retrieval strategies per question rather than forcing one fixed pipeline.

## Core Architecture

**Uniform operator signature** (all 28 operators):
```python
async def op(inputs: Dict[str, SlotValue], ctx: OperatorContext, params: Dict) -> Dict[str, SlotValue]
```

**Operator registry** (28 operators across 6 categories):
```
entity:       vdb, ppr, onehop, link, tfidf, agent, rel_node
relationship: onehop, vdb, score_agg, agent
chunk:        from_relation, occurrence, aggregator, text_search, vdb
subgraph:     khop_paths, steiner_tree, agent_path
community:    from_entity, from_level
meta:         extract_entities, reason_step, rerank, generate_answer, pcst_optimize, decompose_question, synthesize_answers
```

**Composition helpers**:
- `REGISTRY.get_compatible_successors("entity.ppr")` — find operators whose inputs match this operator's outputs
- `REGISTRY.find_chains_to_goal({QUERY_TEXT}, CHUNK_SET)` — valid chains at depth N
- `ChainValidator.validate(plan)` — validates all I/O connections in an ExecutionPlan
- `PipelineExecutor` — runs validated plans through operators

**Key files**:
- `Core/Schema/SlotTypes.py` — 7 SlotKinds + typed records (EntityRecord, RelationshipRecord, etc.)
- `Core/Schema/OperatorDescriptor.py` — Machine-readable operator metadata
- `Core/Operators/` — 28 operators in entity/, relationship/, chunk/, subgraph/, community/, meta/
- `Core/Operators/registry.py` — OperatorRegistry with composition helpers
- `Core/Composition/` — ChainValidator, PipelineExecutor, Adapters
- `Core/AgentSchema/plan.py` — ExecutionPlan, LoopConfig, ConditionalBranch

## MCP Interface

Agents compose operators via MCP tools. `list_operators` + `get_compatible_successors` for discovery. Each operator is an individual MCP tool.

**Typical agent flow**:
```
corpus_prepare → graph_build_er → entity_vdb_build →
entity_vdb_search → relationship_onehop → chunk_occurrence → meta_generate_answer
```

The agent decides the chain at runtime. A comparison question might skip multi-hop traversal; a 4-hop question might iterate deeper.

**MCP tools (50+ total)**:
- 5 graph build (er, rk, tree, tree_balanced, passage) + 1 corpus (prepare)
- 7 entity (vdb_build, vdb_search, onehop, ppr, agent, link, tfidf)
- 5 relationship (onehop, score_agg, agent, vdb_build, vdb_search)
- 7 chunk (from_relationships, occurrence, get_text, aggregator, text_search, vdb_build, vdb_search)
- 2 graph analysis (analyze, visualize) + 3 graph enrichment (augment_chunk_cooccurrence, augment_centrality, augment_synonym_edges) + 3 subgraph (khop_paths, steiner_tree, agent_path)
- 3 community (build_communities, detect_from_entities, get_layer)
- 5 meta (extract_entities, generate_answer, pcst_optimize, decompose_question, synthesize_answers)
- 1 prerequisite build (build_sparse_matrices)
- 2 config (get_config, set_agentic_model)
- 2 operator discovery (list_operators, get_compatible_successors)
- 1 graph types (list_graph_types)
- 1 context (list_available_resources)
- 4 cross-modal (convert_modality, validate_conversion, select_analysis_mode, list_modality_conversions)
- 4 benchmark (semantic_plan, todo_write, bridge_disambiguate, submit_answer)

**Common output-to-input mappings** (for agents composing chains):
- `entity_vdb_search` → `similar_entities[].entity_name` → feed as `seed_entity_ids` to `entity_ppr`
- `entity_ppr` → `ranked_entities: [[id, score], ...]` → `{id: score}` dict for `relationship_score_aggregator(entity_scores=...)`
- `relationship_onehop` → relationship objects → `source_node_id->target_node_id` strings for `chunk_from_relationships(target_relationships=...)`
- `meta_extract_entities` → `entities[].entity_name` → feed as `source_entities` to `entity_link`
- chunk tools → `text_content` fields → feed as `context_chunks: list[str]` to `meta_generate_answer`

**AoT-style composition** (decompose/synthesize operators):
```
meta_decompose_question("Who founded the company that employed Jane Doe?")
→ ["Who is Jane Doe?", "Which company employed her?", "Who founded that company?"]
→ For each sub-question: entity_vdb_search → relationship_onehop → chunk_occurrence → meta_generate_answer
→ meta_synthesize_answers(original_question, sub_answers)
```

## Two-Model Design

- **`llm.model`** (gemini-2.5-flash, cheap) — graph building via `LLMClientAdapter`
- **`agentic_model`** (configurable) — mid-pipeline reasoning in operators like `entity.agent`, `meta.generate_answer`

Both route through `llm_client.acall_llm` — smart retry, fallback chains, cost tracking. API keys auto-loaded from `~/.secrets/api_keys.env`. Use `get_config` to inspect, `set_agentic_model` to override at runtime.

## Extraction Iteration Policy

- Decision-grade extraction prompt/schema/build iteration is pinned to `gemini/gemini-2.5-flash`.
- Do not switch production extraction lanes while judging extraction-quality improvements. Stronger models or SDK agents may be used only as diagnostic tools to classify failures or generate hypotheses.
- Group frozen extraction cases by failure family. Change prompts, schemas, or validators to fix a failure family, not a single benchmark question.
- Do not add entity-string-specific keep/drop lists or other case-shaped extraction rules. Fix the category boundary that explains the miss.
- If a failure family is too narrow to prove generalization, broaden the frozen case set with another real-corpus target before promoting a fix.
- Do not truncate answer-relevant tool results or evidence surfaces. If compact output is needed, keep an explicit path to the best available full evidence.
- Do not set explicit max output tokens on DIGIMON LLM calls by default, especially for structured extraction or eval paths. Any exception needs code-local justification.
- Treat single-pass wins as insufficient evidence when stochasticity is possible. Promote an extraction change only after it improves the frozen case set without regressing protected sentinels.

## Graph Building

**Graph types**: ER (general-purpose), RK (keyword-enriched), Tree/Tree-Balanced (hierarchical), Passage (document-centric).

**Representation policy**:
- Choose node vs edge vs attribute vs chunk-only evidence by operator utility and benchmark reasoning role, not by topic.
- Do not materialize every detailed phrase as a node. Only materialize what must be directly operable for retrieval/composition.
- Do not rely on buried description text as the only representation for answer-critical facts when the retrieval plan needs direct addressing.

**Resilience**:
- **Checkpointing**: ERGraph persists after each batch of 50 chunks. Interrupted builds resume automatically.
- **Fallback chain**: `llm.fallback_models` in Config2.yaml. Primary model fails → next model.
- **Per-chunk isolation**: Individual chunk failures are logged and skipped.

**Extraction levels**: KG (names+relations), TKG (+ types, descriptions), RKG (+ keywords).

**Post-build enrichment** (no LLM cost):
- Chunk co-occurrence edges (`augment_chunk_cooccurrence`)
- PageRank centrality (`augment_centrality`)
- Synonym edges (`augment_synonym_edges`)

**Config overrides**: All 5 `graph_build_*` tools accept `config_overrides: dict` for per-build tuning.

See `docs/adr/013-answer-critical-fact-representation.md`.

## Eval

**Agent benchmark** (`eval/run_agent_benchmark.py`) — the agent freely composes operators.
- Backends: Codex SDK, Claude Agent SDK, MCP agent loop, Direct Python tools (`--backend direct`)
- Modes: `baseline` (no graph), `fixed_graph` (deterministic graph chain), `hybrid` (adaptive)
- Legacy aliases: `fixed`, `adaptive`, and `aot` currently map to `hybrid`
- `BENCHMARK_MODE=1` hides build/config/discovery tools — agent uses retrieval operators only
- CLI: `python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --model gemini/gemini-3-flash --backend direct`

**Scoring**: `eval/benchmark.py` — EM, F1, LLM-as-judge.

**Best results** (50q subsets — not directly comparable to 1000q SOTA):
- HotpotQA: 68.0% EM, 90.0% LLM_EM, 82.5% F1 (deepseek-chat, $0.30)
- MuSiQue: 52.0% EM, 80.0% LLM_EM, 67.7% F1 (o4-mini, $3.41)

**Latest controlled comparison** (MuSiQue 50q balanced dev sample, March 18, 2026):
- Baseline: 34.0% EM, 60.0% LLM_EM
- Fixed Graph: 32.0% EM, 54.0% LLM_EM
- Hybrid: 32.0% EM, 44.0% LLM_EM

This is development evidence only, but it does not currently support the adaptive-routing thesis.

**Test datasets**: `Data/Social_Discourse_Test` (best for dev), `Data/Synthetic_Test`, `Data/MySampleTexts`.

## Environment

- Conda env: `digimon`
- Python 3.10+
- Embeddings: text-embedding-3-small via FAISS
- Graph storage: NetworkX + GraphML

## Known Limitations

- Entity.PPR uses direct graph PPR (not the old EntityRetriever path)
- Entity.Link needs an entity VDB built first (graceful degradation without one)
- Community operators require `build_communities` to be run first
- SteinerTree extracts connected component before running (NetworkX 3.3 workaround)

## Observability

- All LLM/embedding calls logged to `~/projects/data/llm_observability.db` with `trace_id` correlation
- `PipelineExecutor` propagates `trace_id` from `OperatorContext` to adapters
- Query costs: `python -m llm_client cost --project Digimon_for_KG_application`

## Future Work

### Schema Guidance

ADR-002 defines schema-aware extraction as an implemented slice with three canonical modes:
- **Open**: No schema constraints are enforced in prompts.
- **Schema-Guided**: Declared schema is preferred; novel types may appear.
- **Schema-Constrained**: Prompt stays within declared type lists when provided.

The canonical vocabulary is:
- `open`
- `schema_guided`
- `schema_constrained`

See `docs/adr/002-universal-graph-schema-and-extraction.md`.

### Recursive Reasoning Trace (DESIGN)

See `docs/RECURSIVE_REASONING_TRACE.md`. Reasoning traces stored as DIGIMON-compatible ER graphs.

### Cross-Modal Analysis

4 MCP tools, 15 conversion paths across graph/table/vector. See `Core/AgentTools/cross_modal_tools.py`.
