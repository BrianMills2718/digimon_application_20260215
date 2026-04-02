# CLAUDE.md — DIGIMON

## What This Is

DIGIMON is a **composable retrieval system** where agents build and query knowledge graphs using **28 typed operators** composed into retrieval DAGs at runtime. No fixed pipelines — the agent selects both **build strategy** (which graph attributes to construct) and **retrieval strategy** (which operators to compose) based on the task.

**Thesis**: An agent that adaptively selects retrieval strategies — including deciding when graph-based retrieval helps and when simpler methods (text search, VDB) suffice — should outperform any single fixed pipeline across all question types, not just multi-hop.

**Key design properties**:
- **Build is composable**: Graph attributes (entity types, edge descriptions, passage nodes, co-occurrence edges, synonym edges, etc.) are independently toggleable. A graph built with attributes {A, B, C, D} can be queried using any subset {A, D} at retrieval time. The agent can also determine the build strategy if no graph exists yet.
- **Retrieval is adaptive**: The agent chooses text search for simple factoid questions, VDB for semantic similarity, and graph traversal (PPR, multi-hop, subgraph extraction) only when the question structure demands it. Graph operators are available but not forced.
- **Graph isn't always better**: For many question types, text search or VDB outperforms graph traversal. The adaptive agent should recognize this and use simpler methods when they're sufficient, avoiding the cost and noise of graph operations on questions that don't need them.

## Commands

```bash
# Repo interface
make help                    # List supported targets
make status                  # git status --short --branch
make build                   # Build the configured graph artifact
make bench                   # Run the benchmark entrypoint
make build-status            # Show active graph-build progress

# Targeted benchmark/debug paths
python eval/prebuild_graph.py --help
python eval/run_agent_benchmark.py --help
python scripts/graph_build_status.py

# Plan workflow
python scripts/meta/create_plan.py --title "short title"
python scripts/meta/validate_plan.py --plan-file docs/plans/NN_name.md
python scripts/meta/complete_plan.py --plan N

# Coordination
python scripts/meta/check_coordination_claims.py --check --project Digimon_for_KG_application --json
python scripts/meta/worktree-coordination/create_worktree.py --help
```

## Principles

1. **Benchmark-first, general fixes only** — improve failure families, not one benchmark row.
2. **Composable build, adaptive retrieval** — graph enrichments are reusable layers and retrieval should only use graph structure when the question benefits from it.
3. **Observability before diagnosis** — inspect graph-build progress, benchmark artifacts, and trace data before guessing.
4. **Representation is product logic** — answer-critical facts must be retrievable as nodes, edges, attributes, or chunk evidence; do not hide them only in prose.
5. **DIGIMON is the retrieval/runtime lane, not the permanent semantic source of truth** — benchmark-lane local build logic is allowed when needed, but long-term ownership boundaries must stay explicit.

## Workflow

### Active execution lane
- Use `docs/plans/CLAUDE.md` as the current plan index.
- The active benchmark lane is Plans #17 and #21-#24, with Plan #22 as the current execution surface for canonicalization/projection hardening.
- Keep repo-local remediation or rollout work in its own numbered plan rather than folding it into benchmark plans.

### Benchmark iteration loop
- Freeze a bounded failing tranche before making representation or routing changes.
- Implement the smallest general fix that addresses the failure family.
- Rebuild on the smallest real slice first, then rerun the frozen tranche before broadening scope.
- Record the before/after artifact path in the active plan and append durable findings to `KNOWLEDGE.md`.

### Coordination and governance
- Work from claimed worktrees for implementation slices; do not edit the dirty canonical checkout for DIGIMON remediation.
- Keep `AGENTS.md` generated from this file and rerender it after governance-structure changes.
- If a shared or upstream migration question appears, record it in the active plan instead of silently redefining DIGIMON ownership.

## References

| Doc | Purpose |
|-----|---------|
| `docs/plans/CLAUDE.md` | Active plan index |
| `docs/plans/17_retest_thesis.md` | Thesis gate and benchmark decision frame |
| `docs/plans/22_benchmark_first_canonicalization_projection_hardening.md` | Current benchmark execution lane |
| `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md` | DIGIMON vs onto-canon6 boundary plan |
| `docs/plans/24_shared_run_progress_integration_for_graph_builds.md` | Shared graph-build observability contract |
| `docs/GRAPH_ATTRIBUTE_MODEL.md` | Long-term graph representation and projection model |
| `docs/ACTIVE_DOCS.md` | Current documentation authority map |
| `KNOWLEDGE.md` | Cross-agent runtime findings |

## Autonomous Execution Mandate

For active DIGIMON implementation and benchmark iterations, the default is
**continuous autonomous execution**:

- Do not pause after a partial slice just to ask what to do next.
- Do not stop because a run is incomplete, ambiguous, or only partially
  improved. That is diagnostic signal, not a stopping condition.
- If uncertainty remains, log it in the active plan or `KNOWLEDGE.md` and keep
  moving with the best bounded next step in the current phase sequence.
- Treat benchmark failures as routing, representation, tool-contract, or
  answer-synthesis diagnostics. Investigate, classify, fix, re-run.
- Continue through the planned phase sequence until one of these happens:
  1. the current milestone's acceptance criteria are met,
  2. a real external blocker appears (missing dependency, unavailable service,
     corrupted artifact, exhausted budget guardrail),
  3. three materially different attempts fail without new information, which
     triggers a documented strategy change instead of another blind retry.
- "Needs more iteration" is not a stopping condition by itself. The agent must
  record the current failure family, choose the next systemic fix, and continue.
- Every overnight-style run must leave an artifact trail: updated plan status,
  runtime findings in `KNOWLEDGE.md`, and a verified commit for each completed
  implementation slice. Never leave meaningful progress only in chat.

**THIS IS NOT OPTIONAL.** The agent MUST run continuously through the planned
phase sequence. Do not stop to ask "what next?" — the phase sequence below is
the answer. Do not stop because a benchmark run is "only" partially improved —
that is signal, not a stopping condition. Do not stop because it's been a long
time — context compaction handles that. The ONLY reasons to stop are the three
listed above. If you are unsure, write the uncertainty to KNOWLEDGE.md and
keep going.

For the current thesis work, this means the agent should keep running the
failure-driven loop overnight: implement the next control-layer fix, verify on a
small slice, run the targeted MuSiQue batch, diagnose the remaining misses, and
immediately start the next systemic repair until the active plan is exhausted or
an explicit escalation criterion is hit.

### Overnight Phase Sequence (2026-04-02 → 2026-04-03)

Execute these phases in order. Each phase has explicit acceptance criteria.
Do not skip phases. Commit after each verified phase.

| Phase | Task | Acceptance Criteria | Est. Time |
|-------|------|-------------------|-----------|
| 0 | Doc/plan hygiene + commit uncommitted work | CURRENT_STATUS.md updated, Codex changes committed, Plan #17 has completion findings | 1h |
| 1 | Stagnation threshold configurable + diversification | `make bench-musique STAG_TURNS=6` works; stagnation rate drops vs baseline | 2h |
| 2 | Close Plan #21 or document handoff | Frozen tranche rerun completed; plan status updated | 2h |
| 3 | Check Plan #22 projection results | Post-projection benchmark compared with pre-projection baseline; findings recorded | 1h |
| 4 | Entity search quality: top_k increase + fallback | entity_search default top_k=10; sentinel passes; bench-musique tested | 2h |
| 5 | Full 50q decision-grade MuSiQue run | 50q benchmark completed; results in CURRENT_STATUS.md; comparison with 42% baseline | 3h |
| 6 | Update all docs with overnight findings | CURRENT_STATUS.md, KNOWLEDGE.md, ROADMAP.md all current; all plans have correct status | 1h |

**Budget guardrail**: Total overnight LLM spend ≤ $15. Check with `make cost DAYS=1` after each benchmark run. If approaching $12, skip Phase 5 (50q) and proceed to Phase 6.

**Stochasticity policy**: Any benchmark improvement claim requires ≥2 runs showing the same result, OR the improvement is ≥3 questions (outside stochastic noise). Single-run single-question flips are noted as "stochastic" not "fixed."

## Generalization Mandate

DIGIMON fixes must be **general improvements to representation, retrieval,
tool contracts, or control flow**, not patches that only teach the system a
single benchmark answer path.

- Do not hardcode a specific question, answer, entity pair, or dataset row.
- Do not add special-case logic for one failure ID or one named entity unless
  the rule is framed at the level of a general failure family.
- Every repair must be expressible as one of:
  - better graph/entity canonicalization,
  - better passage/edge representation,
  - better retrieval query construction,
  - better tool linearization or contracts,
  - better atom lifecycle / answer gating,
  - or better generic ranking/disambiguation.
- Before landing a fix, state the failure family it addresses and why it should
  improve more than the currently failing question.
- If a candidate fix would only make one benchmark case pass without improving
  the underlying retrieval system, reject it and keep investigating.

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

Agents compose operators via MCP tools. The full MCP server exposes ~67 individual tools, but **benchmarks use the consolidated tool surface** (Plan #15).

**Tool result linearization**: All consolidated tool results must be linearized into compact natural language summaries before entering agent context. Raw JSON wastes context and confuses the LLM. The linearization happens in `tool_consolidation.py` — each tool has a `_linearize()` function that converts structured output to a 2-5 line summary. Full data is written to `results/.last_tool_result.json` for inspection if needed.

**Planning tools**: `semantic_plan` (typed decomposition) and `todo_write` (progress tracking) are available alongside consolidated tools. The agent should plan before retrieving. Plan progress is tracked and can be injected into context.

### Consolidated Benchmark Surface (default, DIGIMON_CONSOLIDATED_TOOLS=1)

10 tools covering the most-used operators via `method` argument (7 specialized operators like entity.agent, meta.rerank are not exposed — available via legacy surface with `DIGIMON_CONSOLIDATED_TOOLS=0`):
```
entity_search(method=semantic|string|tfidf)         — find entities by query
entity_traverse(method=onehop|ppr|neighborhood|link) — explore graph from known entities
entity_info(method=profile|resolve)                  — entity details or name resolution
relationship_search(method=graph|semantic|score)      — find relationships
chunk_retrieve(method=text|semantic|relationships|cooccurrence|by_ids|by_entities) — text evidence
subgraph_extract(method=khop|steiner|pcst)           — extract subgraph structure
community_search(method=from_entities|from_level)    — community retrieval
reason(method=answer|decompose|synthesize|extract)   — LLM reasoning
submit_answer                                         — submit final answer
resources                                             — list available graphs/VDBs
```

Plus `bridge_disambiguate` for entity resolution ambiguity.

Implementation: `Core/MCP/tool_consolidation.py` dispatches to existing operator implementations. Set `DIGIMON_CONSOLIDATED_TOOLS=0` for legacy individual tools.

**Typical agent flow** (consolidated):
```
resources → entity_search(semantic) → entity_traverse(ppr) →
relationship_search(graph) → chunk_retrieve(cooccurrence) → reason(answer) → submit_answer
```

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
- **NEVER truncate evidence text in tool results.** Chunk text, entity descriptions, relationship descriptions must be shown in full to the agent. Truncation hides answers and causes false "extraction failures." The linearization layer summarizes metadata (IDs, scores, counts) but NEVER truncates the actual evidence. This rule exists because we found truncation at 150 chars was silently hiding answers across multiple benchmark runs. If compact output is needed, keep an explicit path to the best available full evidence.
- Do not set explicit max output tokens on DIGIMON LLM calls by default, especially for structured extraction or eval paths. Any exception needs code-local justification.
- Treat single-pass wins as insufficient evidence when stochasticity is possible. Promote an extraction change only after it improves the frozen case set without regressing protected sentinels.

## Graph Building

**Graph types**: ER (general-purpose), RK (keyword-enriched), Tree/Tree-Balanced (hierarchical), Passage (document-centric).

**Cross-project import bridge**: `scripts/import_onto_canon_jsonl.py` imports
onto-canon6 `entities.jsonl` / `relationships.jsonl` exports into DIGIMON's
native GraphML artifact layout. Current policy is to merge duplicate entity
names and skip relationships with a missing endpoint because the persisted
graph is binary-edge-only.

**Lane 2 consumer boundary**: DIGIMON is the first chosen downstream consumer
for onto-canon6's post-cutover program. The currently supported workflow is the
thin v1 seam: from the `onto-canon6` repo root, export via the installed
`onto-canon6` console script; from the DIGIMON repo root, import via
`scripts/import_onto_canon_jsonl.py`. This proves governed graph
materialization into DIGIMON, but it does not yet promote onto-canon6-backed
semantic build outputs onto DIGIMON's default benchmark lane.

**Cross-project integration**: `scripts/import_onto_canon_jsonl.py` imports onto-canon6 entity/relationship exports into DIGIMON's GraphML format. See CLAUDE.md Vision section for the full pipeline (research_v3 → onto-canon → DIGIMON → grounded-research).

**Representation policy**:
- Choose node vs edge vs attribute vs chunk-only evidence by operator utility and benchmark reasoning role, not by topic.
- Do not materialize every detailed phrase as a node. Only materialize what must be directly operable for retrieval/composition.
- Do not rely on buried description text as the only representation for answer-critical facts when the retrieval plan needs direct addressing.

**Representation diagnosis loop**:
1. Define the answer-critical datum.
2. Locate where it exists now: node, edge, attribute, chunk evidence, buried description text, or nowhere.
3. Define the minimal representation that would make the datum retrievable and composable.
4. Check operator reachability from the question to that representation.
5. Identify the first loss point: extraction, indexing, tool contract, routing, or answer synthesis.
6. Group by reasoning-role failure family, not topic.
7. Set stage-specific acceptance criteria for the suspected loss point.
8. Prove the fix on the smallest real benchmark slice before scaling.

**Resilience**:
- **Checkpointing**: ERGraph persists after each batch of 50 chunks. Interrupted builds resume automatically.
- **Fallback chain**: `llm.fallback_models` in Config2.yaml. Primary model fails → next model.
- **Per-chunk isolation**: Individual chunk failures are logged and skipped.

**Extraction levels**: KG (names+relations), TKG (+ types, descriptions), RKG (+ keywords).

**Graph attributes are composable layers, not monolithic builds.** A graph built with attributes {A, B, C, D} must be usable with any subset at retrieval time. Enrichments (passage nodes, co-occurrence edges, synonym edges, centrality) are post-build scripts that add layers without rebuilding. The base graph (entities + relationships from extraction) is built once; layers are added/removed independently via `make add-passages`, `make enrich`, etc.

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

**Latest results**: See `CURRENT_STATUS.md` for the single source of truth on benchmark numbers.

**50q MuSiQue (2026-03-26)**: Baseline 20.0% → GraphRAG 42.0% LLM-judge (2.1x, 15 graph wins). Plans #14-#16 complete, Plan #17 active. **Note (2026-04-02)**: Plan #17 found results are stochastic (sentinel question 731956 has ~50% pass rate). Prompt tuning alone eliminated the ANSWER_SYNTHESIS failure family. Retrieval stagnation (4-turn limit) is the remaining bottleneck, not graph architecture.

**Routing model**: `openrouter/openai/gpt-5.4-mini` (400K context, strong tool calling, $1.69/M blended). Replaces gemini-2.5-flash as the recommended benchmark agent model.

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

## Literature Review (2026-03-23)

Full review: `~/projects/investigations/digimon/2026-03-23-graphrag-sota-review.md`

**Key findings**:
- Graphs unambiguously help for multi-hop QA (vanilla RAG 27% → SOTA 58% EM)
- DIGIMON is missing: passage-level nodes (HippoRAG v2), PPR tuning (damping=0.5), IDF scoring, question decomposition in pipeline
- Question decomposition is the single biggest lever (+15 EM in StepChain ablation)
- Co-occurrence edges may suffice — EcphoryRAG gets 72.2% EM without relationship extraction
- No system in literature does per-question composable operator routing — DIGIMON's thesis is novel and untested

**Competitive scoreboard** (SOTA on multi-hop QA):
| System | Avg EM | Architecture |
|--------|--------|-------------|
| StepChain | 57.7 | On-the-fly graph + BFS + decomposition (GPT-4o) |
| HopRAG | 53.8 | Passage graph + logical edges |
| EcphoryRAG | 47.4 | Entity-only + associative search (Phi-4) |
| HippoRAG 2 | 39.0* | Phrase+passage bipartite + PPR |

**Active strategic plan**: Plans #14-#18 (ROADMAP.md). Fix tool surface → add SOTA build attributes → re-test thesis.

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

## Vision

**DIGIMON is the retrieval engine for a causal-epistemic reasoning system.** The benchmarks aren't the product — they prove the engine works.

**The pipeline** (not all components built yet):
```
Sources (web, docs, OSINT) → research_v3 (ingestion + search)
    → onto-canon (entity canonicalization + ontology)
    → DIGIMON (graph construction + adaptive retrieval)
    → grounded-research (adjudication + claim evaluation)
```

**What DIGIMON uniquely provides**: Composable operator routing. No other system lets the agent select retrieval strategies per question from a typed operator catalog AND determine the graph build strategy. The 28 operators exist because real investigative questions need different retrieval shapes — entity co-occurrence, multi-hop traversal, community detection, subgraph extraction, or just text search when the graph adds no value.

**Scaling path**:
1. Prove graph value on multi-hop QA benchmarks (current — Plan #17)
2. Test on real OSINT queries from research_v3
3. Wire as research_v3's retrieval backend
4. Feed onto-canon's canonicalized entities into graph builds

**What DIGIMON is NOT**: Not a general-purpose RAG framework. Not a graph database. Not trying to beat SOTA benchmarks as an end goal. The contribution is the composable operator model and the evidence that adaptive routing outperforms fixed pipelines across question types.
