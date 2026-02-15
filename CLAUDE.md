# CLAUDE.md - DIGIMON Implementation Guide

## CURRENT STATE: Modular Operator Pipeline (2026-02-15)

Branch `modular-operator-pipeline` implements a typed, composable operator system.
Old Retriever/Query classes have been deleted. The operator pipeline is the canonical system.

### Operator Pipeline Status
```
Phase 1:  Type System        [DONE] SlotTypes, OperatorDescriptor, GraphCapabilities
Phase 2:  Operators (26)     [DONE] 7 entity + 4 relationship + 3 chunk + 3 subgraph + 2 community + 7 meta
Phase 3:  Registry           [DONE] OperatorRegistry with composition helpers
Phase 4:  Composition Engine [DONE] ChainValidator, PipelineExecutor, Adapters
Phase 5:  Method Plans (10)  [DONE] All 10 methods expressed as ExecutionPlans, all validate
Phase 6:  Graph Capabilities [DONE] BaseGraph.capabilities property
Phase 7:  QA Evaluation      [DONE] New pipeline 50% vs old 30% on HotPotQA (10 questions)
Phase 8:  Delete Old System  [DONE] Core/Retriever/ and Core/Query/ deleted, references cleaned up
Phase 9:  MCP Composition    [DONE] MCP tools, execute_method, auto_build for VDBs
Phase 10: Full Auto-Build    [DONE] build_sparse_matrices + build_communities tools; 10/10 methods pass with auto_build=True
Phase 11: Auto-Compose       [DONE] auto_compose MCP tool — LLM picks best method from 10 based on query + resources
Phase 12: Config + Operators [DONE] get_config, set_agentic_model, list_operators, get_compatible_successors; operator-centric MCP framing
Phase 13: Output Schemas     [DONE] Returns: section added to all MCP tool docstrings
Phase 14: Eval Harness       [DONE] eval/ directory — BenchmarkRunner, EM/F1 scoring, CLI entry point
Phase 15: AoT Operators      [DONE] meta.decompose_question + meta.synthesize_answers — AoT-style reasoning
Phase 16: Recursive Trace    [DESIGN] docs/RECURSIVE_REASONING_TRACE.md — reasoning trace as ER graph, recursive DIGIMON-on-DIGIMON
Phase 17: Cross-Modal MCP   [DONE] 4 tools: convert_modality, validate_conversion, select_analysis_mode, list_modality_conversions
```

### Key Architecture: Operator Pipeline

**Uniform operator signature** (all 26 operators):
```python
async def op(inputs: Dict[str, SlotValue], ctx: OperatorContext, params: Dict) -> Dict[str, SlotValue]
```

**Key files**:
- `Core/Schema/SlotTypes.py` — 7 SlotKinds + typed records (EntityRecord, RelationshipRecord, etc.)
- `Core/Schema/OperatorDescriptor.py` — Machine-readable operator metadata
- `Core/Operators/` — 26 operators in entity/, relationship/, chunk/, subgraph/, community/, meta/
- `Core/Operators/registry.py` — OperatorRegistry with composition helpers
- `Core/Composition/` — ChainValidator, PipelineExecutor, Adapters, auto_compose
- `Core/Methods/` — 10 reference pipelines as ExecutionPlan factories (convenience shortcuts, not the core abstraction)
- `Core/AgentSchema/plan.py` — Extended with LoopConfig, ConditionalBranch

**Operator registry** (26 operators across 6 categories):
```
entity:       vdb, ppr, onehop, link, tfidf, agent, rel_node
relationship: onehop, vdb, score_agg, agent
chunk:        from_relation, occurrence, aggregator
subgraph:     khop_paths, steiner_tree, agent_path
community:    from_entity, from_level
meta:         extract_entities, reason_step, rerank, generate_answer, pcst_optimize, decompose_question, synthesize_answers
```

**Composition helpers**:
- `REGISTRY.get_compatible_successors("entity.ppr")` — 13 compatible operators
- `REGISTRY.find_chains_to_goal({QUERY_TEXT}, CHUNK_SET)` — 95 valid chains at depth 3
- `ChainValidator.validate(plan)` — validates all I/O connections in an ExecutionPlan

### MCP Agent Composition (2026-02-15)

**Status**: Complete. All 26 operators accessible individually via MCP. Agents compose
arbitrary retrieval DAGs by calling operators sequentially, using `list_operators` +
`get_compatible_successors` for discovery. 10 reference pipelines also available as
shortcuts via `execute_method`.

**Orchestration architecture** (see `docs/adr/001-agent-orchestration-architecture.md`):
Two non-exclusive modes — DIGIMON's internal brain (`agentic_model`) handles mid-pipeline
LLM calls and auto_compose; a capable client (Claude Code, Codex) can override and drive
directly via individual operators or execute_method. Both are always available.

**New components**:
- `Core/Provider/LLMClientAdapter.py` — wraps `llm_client.acall_llm` behind BaseLLM interface
- `Core/Composition/OperatorComposer.py` — method profiling, plan building, execution
- `Core/Composition/auto_compose.py` — LLM-driven method selection (CompositionDecision, select_method)
- `prompts/auto_compose.yaml` — Jinja2 template for method selection prompt
- `Option/Config2.py` — `agentic_model` field for separate LLM for meta operators
- `Core/AgentTools/corpus_format_parsers.py` — multi-format file parsers for corpus_prepare

**MCP tools (49 total)**:
- 5 graph build (er, rk, tree, tree_balanced, passage) + 1 corpus (prepare)
- 7 entity (vdb_build, vdb_search, onehop, ppr, agent, link, tfidf)
- 5 relationship (onehop, score_agg, agent, vdb_build, vdb_search)
- 4 chunk (from_relationships, occurrence, get_text, aggregator)
- 2 graph analysis (analyze, visualize) + 3 subgraph (khop_paths, steiner_tree, agent_path)
- 3 community (build_communities, detect_from_entities, get_layer)
- 5 meta (extract_entities, generate_answer, pcst_optimize, decompose_question, synthesize_answers)
- 1 prerequisite build (build_sparse_matrices)
- 2 config (get_config, set_agentic_model)
- 2 operator discovery (list_operators, get_compatible_successors)
- 4 method-level (list_methods, list_graph_types, execute_method, auto_compose)
- 1 context (list_available_resources)
- 4 cross-modal (convert_modality, validate_conversion, select_analysis_mode, list_modality_conversions)

**Three execution modes** (increasing autonomy):
1. **Operator composition** (primary) — client composes arbitrary retrieval DAGs by calling operators directly. Use `list_operators` + `get_compatible_successors` for discovery, `ChainValidator` to verify. Tested via `test_custom_chain.py`.
2. **Reference pipelines** — `execute_method("basic_local", query, dataset, auto_build=True)` runs one of 10 pre-composed pipelines. Convenience shortcuts for known-good patterns.
3. **Full auto** — `auto_compose(query, dataset, auto_build=True)` — LLM picks a reference pipeline based on query characteristics and available resources.

**Auto-corpus** (`input_directory` on graph_build_* tools):
- All 5 graph_build tools accept `input_directory` parameter
- If no Corpus.json exists, auto-calls `corpus_prepare` before building
- `corpus_prepare` supports .txt, .md, .json, .jsonl, .csv, .pdf
- For structured formats (JSON, CSV), auto-detects text/title fields
- One-call workflow: `graph_build_er(dataset_name="my_kg", input_directory="/path/to/data/")`

**Auto-build** (`auto_build=True` on execute_method):
- Automatically builds all missing prerequisites: entity VDB, relationship VDB,
  sparse matrices, and community structure
- Community building calls LLM (most expensive auto-build step)
- Default: `False` (existing behavior unchanged)
- All reference pipelines work with `auto_build=True` given a built graph

**Two-level agent architecture**:

There are two agents in DIGIMON — the **outer agent** (orchestrator) and the **inner agent** (`agentic_model`):
- **Outer agent** (Claude Code, Codex): Composes operators, decides strategy, drives Mode 1.
- **Inner agent** (`agentic_model`): Handles mid-pipeline LLM calls inside operators like `entity.agent`, `relationship.agent`, `subgraph.agent_path`, and iterative loops in tog/kgp.

In Mode 1, the outer agent can subsume the inner agent's role — instead of calling `subgraph.agent_path` (which uses `agentic_model` internally to filter paths), the outer agent can call `subgraph.khop_paths`, read the paths itself, and decide which to keep.

In Mode 2/3, the inner agent does all the reasoning within the pipeline. This is where `agentic_model` matters most.

**Multi-model config**:
```yaml
agentic_model: "anthropic/claude-sonnet-4-5-20250929"  # query-time reasoning, via litellm API
```
Valid values: any litellm model string. This is a regular API call (NOT an agent SDK), despite the field name.
Common choices: `"anthropic/claude-sonnet-4-5-20250929"`, `"gemini/gemini-2.5-flash"`, `"openai/o4-mini"`.
Agent SDK models (`codex`, `claude-code`) work but cause recursive subprocess issues when DIGIMON runs as an MCP server under that same agent.

**Model tradeoffs** (for mid-pipeline reasoning):
- `anthropic/claude-sonnet-4-5-20250929` — default. High-quality reasoning via direct API.
- `gemini/gemini-2.5-flash` — $0.30/M. Good balance of quality and cost.
- `openai/o4-mini` — Strong reasoning with chain-of-thought.

Graph building uses `llm.model` (`gemini/gemini-2.5-flash`, cheap/fast). API keys auto-loaded by llm_client from `~/.secrets/api_keys.env`. Use `get_config` to inspect, `set_agentic_model` to override at runtime.

### Previous Work: MCP Integration

MCP server, client manager, context store, and tool migration complete (checkpoints 1.1-2.3).
Operator pipeline phases 1-12 complete. All 24 operators and 10 reference pipelines operational via MCP.

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

### Reference Pipelines (10 pre-composed operator chains)

These are convenience shortcuts — common operator compositions packaged as named pipelines.
The real power is composing operators freely (Mode 1). These exist for benchmarking and
as starting points. See `test_custom_chain.py` for arbitrary composition.

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

### Mode 1 via MCP: Agent-Driven Composition

**Status**: Works. Agent calls individual operator tools, parses JSON output, constructs
inputs for the next tool. Standard MCP pattern — agent is the composition layer.

**Output schemas**: All MCP tool docstrings now include `Returns:` sections documenting
output JSON structure. Agents can plan operator chains by reading docstrings alone.

**Common output-to-input mappings** (for agents composing chains):
- `entity_vdb_search` → outputs `similar_entities[].entity_name` → feed as `seed_entity_ids` to `entity_ppr`
- `entity_ppr` → outputs `ranked_entities: [[id, score], ...]` → construct `{id: score}` dict for `relationship_score_aggregator(entity_scores=...)`
- `relationship_onehop` → outputs relationship objects → extract `source_node_id->target_node_id` as strings for `chunk_from_relationships(target_relationships=...)`
- `meta_extract_entities` → outputs `entities[].entity_name` → feed as `source_entities` to `entity_link`
- chunk tools → outputs `text_content` fields → feed as `context_chunks: list[str]` to `meta_generate_answer`

**AoT-style composition** (using new decompose/synthesize operators):
```
meta_decompose_question("Who founded the company that employed Jane Doe?")
→ ["Who is Jane Doe?", "Which company employed her?", "Who founded that company?"]
→ For each sub-question: entity_vdb_search → relationship_onehop → chunk_occurrence → meta_generate_answer
→ meta_synthesize_answers(original_question, sub_answers)
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
- **26 Operators**: `Core/Operators/{entity,relationship,chunk,subgraph,community,meta}/`
- **Registry**: `Core/Operators/registry.py` — OperatorRegistry with composition helpers
- **Composition**: `Core/Composition/` — ChainValidator, PipelineExecutor, Adapters, OperatorComposer
- **Reference Pipelines**: `Core/Methods/` — 10 pre-composed operator chains as ExecutionPlan factories
- **Plan Extensions**: `Core/AgentSchema/plan.py` — LoopConfig, ConditionalBranch
- **Eval Harness**: `eval/` — BenchmarkRunner, EM/F1 scoring, CLI entry point
- **Prompt Templates**: `prompts/` — auto_compose.yaml, decompose_question.yaml, synthesize_answers.yaml, select_analysis_mode.yaml
- **Cross-Modal**: `Core/AgentTools/cross_modal_tools.py` — 15 conversion paths, embedding providers, round-trip validation

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

### Eval Harness (DONE)

**Two benchmark modes:**

1. **Agent benchmark** (`eval/run_agent_benchmark.py`) — Codex agent freely composes operators via MCP
   - Uses `acall_llm("codex", ..., mcp_servers=...)` from llm_client (Codex SDK, not subprocess)
   - **Only loads `digimon-kgrag` MCP server** (not all 17 global servers) via `mcp_servers` kwarg
   - Agent discovers and calls digimon-kgrag MCP tools autonomously
   - Structured `McpToolCallItem` extraction from `Turn.items` (exact tool tracking)
   - Real token counts and cost from SDK `Usage` object
   - CLI: `python eval/run_agent_benchmark.py --dataset HotpotQAsmallest --n 10`
   - Options: `--model codex` `--effort high` `--timeout 120`
   - Output: `results/{dataset}_agent_benchmark.json` + `.log`

2. **Fixed pipeline benchmark** (`eval/run_benchmark.py`) — runs named methods via OperatorComposer
   - Calls Python directly (no MCP overhead) for batch runs
   - `CountingLLMWrapper` tracks LLM calls and tokens per question
   - CLI: `python eval/run_benchmark.py --dataset HotpotQAsmallest --methods basic_local --n 10`
   - Output: `results/{dataset}_benchmark.json`

**Shared infrastructure:**
- `eval/benchmark.py` — EM/F1 scoring, BenchmarkRunner, QuestionResult/MethodResult dataclasses
- `eval/data_prep.py` — Dataset loading from Question.json (JSONL)
- `eval/_llm_counter.py` — CountingLLMWrapper for fixed pipeline token tracking
- `eval/_chunk_lookup.py` — ChunkLookup adapter for OperatorContext

**Existing baselines** (from `test_qa_evaluation_pipeline.py`):
- basic_local pipeline: 50% accuracy on HotPotQAsmallest (10 questions, 2-5s/question)
- Uses LLM judge for flexible answer matching (handles verbose answers)

### Phase 17: Cross-Modal MCP Tools (DONE)

**Key files**:
- `Core/AgentTools/cross_modal_tools.py` — Conversion logic, embedding providers, validation
- `prompts/select_analysis_mode.yaml` — Jinja2 prompt for modality recommendation

**4 MCP tools**: convert_modality, validate_conversion, select_analysis_mode, list_modality_conversions

**15 conversion paths** across 6 format pairs (graph/table/vector):
- graph→table: nodes, edges, adjacency
- table→graph: entity_rel, adjacency, auto (heuristic)
- graph→vector: node_embed (via embedding model), features (static stats)
- table→vector: stats (descriptive), row_embed (via embedding model)
- vector→graph: similarity (cosine threshold), clustering (KMeans/DBSCAN)
- vector→table: direct, pca, similarity matrix

**3 embedding providers**: `local` (sentence-transformers, default), `digimon` (configured model), `hash` (testing)

**Round-trip validation**: `validate_conversion(format_sequence="graph,table,graph")` measures entity/edge preservation.

**E2E tests**: `test_cross_modal.py` — 75 tests on real Fictional_Test ERGraph (104 nodes, 84 edges). No mocks.

### Phase 16: Recursive Reasoning Trace (DESIGN)
See `docs/RECURSIVE_REASONING_TRACE.md`. Reasoning traces stored as DIGIMON-compatible ER
graphs, enabling recursive meta-analysis. Priority order:
1. **Run baselines** — benchmark all 10 methods on HotPotQA (50+ questions) to establish EM/F1 baselines
2. **Add MuSiQue + 2Wiki** — download, convert to DIGIMON corpus format, add to data_prep.py
3. **Trace writer + trace-to-graph converter** — instrument operator calls, produce ER graphs
4. **Recursive application** — apply DIGIMON operators to trace graphs

See `docs/IDEAS.md` for future enhancement ideas and dead code inventory.
