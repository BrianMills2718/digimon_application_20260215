# Investigation: Full Dependency Chain of Planned Work

**Date**: 2026-02-16
**Question**: What is the complete dependency chain of everything we need to implement across DIGIMON and onto-canon? What's essential vs overengineering?

---

## Atoms

| ID | Question | Deps | Status |
|----|----------|------|--------|
| A1 | What does ADR-002 propose and what are its internal dependencies? | — | Answered |
| A2 | What does ADR-003 propose and what are its internal dependencies? | — | Answered |
| A3 | What does UNIFIED_PLAN list as pending? | — | Answered |
| A4 | Where exactly are prompts hardcoded in the extraction pipeline? | — | Answered |
| A5 | What mutation methods exist/are missing in storage? | — | Answered |
| A6 | What onto-canon code is reusable without SQLite? | — | Answered |
| A7 | What does LLMClientAdapter support? | — | Answered |
| A8 | What benchmark infra exists vs what's needed? | — | Answered |
| A9 | What is the actual dependency graph? | A1-A8 | Answered |
| A10 | What's overengineering vs essential? | A9 | Answered |

---

## Assumptions Register

| # | Assumption | Confidence | How to verify | Status |
|---|-----------|------------|---------------|--------|
| 1 | `match_entities_to_concepts()` works without SQLite | High | Read code — confirmed pure LLM call, takes dicts | **Verified** |
| 2 | `belief_ops.py` is pure math, no DB | High | Read code — confirmed only imports `math` | **Verified** |
| 3 | HippoRAG corpus needs conversion to DIGIMON JSONL | High | Compared formats — JSON array vs JSONL, different field names | **Verified** |
| 4 | Prompts-as-data requires changing GraphPrompt.py callers | High | Traced 7 LLM call sites through ERGraph, RKGraph, DelimiterExtraction, BaseGraph | **Verified** |
| 5 | Existing operators work unmodified with reified graphs | Medium | ADR-002 claims topology-agnostic; NOT empirically verified | Unverified |
| 6 | Entity canonicalization improves benchmark EM scores | Medium | Logical (dedup helps multi-hop), but no empirical test yet | Unverified |
| 7 | networkx-query library exists and is usable | Low | Not checked | Unverified |

---

## A1: ADR-002 Internal Dependencies

**Source**: `docs/adr/002-universal-graph-schema-and-extraction.md`

6 proposed items with this dependency chain:

```
Nothing ──→ Prompts as data ──→ Ontology modes ──→ Schema validation
                            └──→ Reified graph type
Nothing ──→ Entity canonicalization ──→ Q-code resolution
```

**Evidence for prompts-as-data scope** (A4 results):
- 7 hardcoded prompts in `Core/Prompt/GraphPrompt.py` (lines 1-411)
- 7 LLM call sites across 4 files:
  1. `ERGraph.py:70` — NER via `GraphPrompt.NER`
  2. `ERGraph.py:115` — OpenIE via `GraphPrompt.OPENIE_POST_NET`
  3. `ERGraph.py:175` — Auto-generate ontology
  4. `DelimiterExtraction.py:72` — Main extraction via `ENTITY_EXTRACTION` or `ENTITY_EXTRACTION_KEYWORD`
  5. `DelimiterExtraction.py:85` — Gleaning continue via `ENTITY_CONTINUE_EXTRACTION`
  6. `DelimiterExtraction.py:89` — Gleaning check via `ENTITY_IF_LOOP_EXTRACTION`
  7. `BaseGraph.py:310` — Summary merging via `SUMMARIZE_ENTITY_DESCRIPTIONS`
- **Custom ontology already loaded at runtime** (`Config2.py:106-120` → `graph_config.loaded_custom_ontology`)
- **No `ontology_mode` or `post_build` config fields exist** in `Config2.py` or `GraphConfig.py`

---

## A2: ADR-003 Internal Dependencies

**Source**: `docs/adr/003-graph-tool-suites.md`

```
Nothing ──→ Basic mutation tools (expose upsert, add delete) ──→ Graph versioning
Nothing ──→ Graph statistics tool
Nothing ──→ Lightweight belief state on edges ──→ Deep epistemic round-trip
Nothing ──→ Cypher-like pattern matching
```

**Evidence for storage gaps** (A5 results):
- `NetworkXStorage` has `upsert_node`, `upsert_edge`, `clear()`, `persist()`
- **No `delete_node`, `delete_edge`, `remove_node`, `remove_edge` methods**
- These are 1-liners wrapping `nx.Graph.remove_node()` / `nx.Graph.remove_edge()`
- VDB invalidation on delete is a real concern — VDB indices reference node names

---

## A3: UNIFIED_PLAN Pending Items

**Source**: `project-meta/vision/UNIFIED_PLAN.md`

Three independent tracks:

| Track | Next Item | Status | Depends On |
|-------|-----------|--------|------------|
| A (Epistemic) | M5 validation/hardening | Implementation done, integration validation pending | M1 (done), M6 (done) |
| B (Cross-modal) | M13/7 (cross-modal pipeline) + #9 (convergence spike) | 50% done (4 MCP tools exist) | M12 (done) |
| C (Theory) | #6 (analytic tier system) → #11 (six-level theory) | Stub created | Nothing |

Also pending:
- M2 (Corpus Bridge) — no dependencies, not started
- M4 (Claim Adapter) — depends on M1 (done)
- #14 (Semantic SUMO Validation) — depends on M1 (done)
- M16 (WhyGame Adapter) — **already done** (noted in onto-canon CLAUDE.md)

---

## A6: Onto-Canon Reusable Code

| Asset | Standalone? | Evidence |
|-------|-------------|----------|
| `match_entities_to_concepts()` in `concept_dedup.py:145-233` | **YES** — takes plain dicts, calls `llm_client.call_llm_structured()`, returns `ConceptMatch` objects | No DB imports in function body |
| `belief_ops.py` (all functions) | **YES** — pure math | Only imports `math` |
| `match_concepts.yaml` prompt | **YES** — YAML file | Standalone template |
| `import_digimon_graph()` | **NO** — writes to SQLite | `cursor` parameter required |
| `export_to_digimon_graph()` | **NO** — reads from SQLite | `db_path` parameter required |
| `verify_round_trip()` | **YES** — pure dict comparison | No DB calls |

**Known prompt quality issue**: `match_concepts.yaml` "too aggressive — merges related-but-distinct concepts" (onto-canon CLAUDE.md). May need iteration for DIGIMON entity names.

---

## A7: LLMClientAdapter State

**Source**: `Core/Provider/LLMClientAdapter.py`

- `fallback_models` parameter: **implemented** (line 54, forwarded at lines 79, 117)
- `num_retries` parameter: **implemented** (line 55, forwarded at lines 80, 118)
- `format="json"` support: **implemented** (line 120-121, sends `response_format`)
- Streaming: **not implemented** (raises `NotImplementedError` at lines 111, 150)
- Structured output: **not implemented** — `acompletion_text` returns `str`, not validated Pydantic models. For entity canonicalization post-build, would need `call_llm_structured` from `llm_client` directly (not through adapter).

**Implication**: Post-build entity canonicalization should call `llm_client.call_llm_structured()` directly, not go through `LLMClientAdapter`. The adapter is for operator compatibility (`BaseLLM.aask()` interface).

---

## A8: Benchmark Infrastructure

**Conversion needed**: HippoRAG format → DIGIMON format.

| HippoRAG Field | DIGIMON Field | Transform |
|----------------|---------------|-----------|
| Corpus: `[{"idx", "title", "text"}]` (JSON array) | `{"title", "context", "doc_id"}` (JSONL) | Rename `text`→`context`, `idx`→`doc_id`, array→lines |
| Questions: `[{"_id", "question", "answer", "type"}]` (JSON array) | `{"id", "question", "answer"}` (JSONL) | Rename `_id`→`id`, array→lines |

**No converter exists**. Need ~30 lines in `eval/data_prep.py`.

**corpus_format_parsers.py** (`Core/AgentTools/corpus_format_parsers.py`) auto-detects `text` field, so `corpus_prepare` MCP tool *could* handle the corpus file — but the question file still needs custom conversion.

---

## A9: Full Dependency Graph

### Contraction

After analyzing all atoms, here's the **actual** dependency graph across all work items, distinguishing what blocks what:

```
TIER 0: NO DEPENDENCIES (can start immediately, in parallel)
═══════════════════════════════════════════════════════════

[A] HippoRAG converter          ~30 lines in eval/data_prep.py
    → enables fair benchmark

[B] Entity canonicalization      ~150 lines: extract match_entities_to_concepts
    post-build step              + belief_ops.py + new post_build hook in BaseGraph
    → immediate graph quality improvement

[C] Basic mutation MCP tools     ~80 lines: add delete_node/delete_edge to
                                 NetworkXStorage + 5 thin MCP wrappers
    → enables graph maintenance

[D] Graph statistics MCP tool    ~50 lines: wrap nx analytics
    → enables observability


TIER 1: DEPENDS ON TIER 0
═══════════════════════════

[E] Fair HippoRAG benchmark     Depends on: [A] converter + graph build (~6K docs)
    run on standard corpus       + run_benchmark or run_agent_benchmark on 1000 questions
    → establishes comparable SOTA number

[F] Prompts as data             ~200 lines: YAML templates + loader function in
                                GraphPrompt.py + changes to 7 call sites
    Depends on: nothing (but [B] entity canonicalization is higher priority)
    → unblocks ontology modes and reified graphs

[G] Lightweight belief state    ~150 lines: add status/probability edge attrs
    on NetworkX edges            during build + weaken/retract MCP tools
    Depends on: [C] basic mutation tools (needs delete for retraction)
    + extract belief_ops.py math
    → enables edge-level quality tracking

[H] Graph versioning            ~150 lines: snapshot/diff/restore
    Depends on: [C] mutation tools (no point versioning without mutation)
    → enables safe experimentation


TIER 2: DEPENDS ON TIER 1
═════════════════════════

[I] Ontology modes              ~100 lines: add ontology_mode to Config2.py
    (open/closed/mixed)          + Jinja2 conditionals in extraction templates
    Depends on: [F] prompts as data
    → enables constrained extraction

[J] Reified graph type          ~300 lines: new extraction template (JSON parser)
    (n-ary via diamond pattern)  + diamond-pattern builder in __graph__()
    Depends on: [F] prompts as data
    → enables event-centric reasoning

[K] Schema validation           ~80 lines: post-build type checker
    post-build step              Depends on: [I] ontology modes (needs type lists)
    → enforces closed/mixed constraints


TIER 3: DEPENDS ON TIER 2
═════════════════════════

[L] Q-code resolution           Depends on: [B] entity canonicalization
    post-build step              + onto-canon's wikidata_entity_search.py
    → Wikidata entity disambiguation

[M] Deep epistemic round-trip   Depends on: [G] lightweight belief state
    (DIGIMON ↔ onto-canon)       + fix round-trip data loss in digimon_adapter.py
    → full epistemic analysis

[N] Cypher-like pattern          ~300 lines: parser + NetworkX query compiler
    matching                     Depends on: nothing strictly, but more useful after
                                 [I] ontology modes (type-filtered queries)
    → ad-hoc graph pattern queries


UNIFIED_PLAN ITEMS (parallel tracks, mostly independent):
═══════════════════════════════════════════════════════════

[UP-1] M5 validation/hardening   → onto-canon epistemic workflow testing
[UP-2] M13/7 cross-modal pipeline → CrossModalBridge (480 lines in DIGIMON)
[UP-3] #9 convergence spike      → overlaps with [M] round-trip optimization
[UP-4] #6 analytic tier system    → theory-selector (separate project)
[UP-5] M2 corpus bridge           → twitter/onto-canon → DIGIMON corpus converter
```

### Visual Dependency DAG

```
[A] Converter ──→ [E] Fair Benchmark

[B] Entity Canon ──→ [L] Q-codes

[C] Mutation Tools ──→ [G] Belief State ──→ [M] Deep Epistemic
                   └──→ [H] Versioning

[D] Graph Stats

[F] Prompts as Data ──→ [I] Ontology Modes ──→ [K] Schema Validation
                    └──→ [J] Reified Graph

                         [N] Cypher (independent)
```

---

## A10: What's Essential vs Overengineering

### ESSENTIAL (solves a real problem we have today)

| Item | Why Essential | Evidence |
|------|-------------|----------|
| **[A] HippoRAG converter** | Can't run fair benchmark without it. Current HotpotQA_200 result (61.5% EM) isn't comparable to SOTA. | `Data/hipporag_benchmark/` exists but in wrong format. |
| **[B] Entity canonicalization** | Direct benchmark quality improvement. "United States" / "US" / "the US" are separate nodes. HotpotQA_200 graph has 17,118 nodes — many are duplicates. | `clean_str()` only does lowercase + strip punctuation (`Core/Graph/BaseGraph.py`). `match_entities_to_concepts()` in onto-canon does LLM fuzzy matching — verified standalone. |
| **[E] Fair benchmark** | Without this, we can't claim any SOTA number. The entire benchmarking exercise is blocked. | Previous benchmark used 200 questions from 1,800 chunks — not the standard 1,000 questions from pooled ~10K corpus. |
| **[F] Prompts as data** | Brian's design principle ("Prompts as Data — All LLM prompts stored as YAML/Jinja2 templates"). 7 hardcoded Python f-strings in `GraphPrompt.py`. Every prompt change requires editing Python. | `GraphPrompt.py` is 411 lines of hardcoded strings. `CLAUDE.md` global instructions explicitly require this pattern. |

### HIGH VALUE BUT NOT BLOCKING

| Item | Why High Value | Why Not Blocking |
|------|---------------|-----------------|
| **[C] Mutation tools** | Can't fix extraction errors without rebuilding. | Current workflow is rebuild-from-scratch, which works. |
| **[D] Graph statistics** | Would help diagnose graph quality issues. | Can do `nx.info()` manually in Python. |
| **[G] Lightweight belief state** | Enables edge quality tracking. | Not needed for benchmark. |
| **[I] Ontology modes** | Enables constrained extraction for domain-specific graphs. | Open mode (current) works for HotpotQA. |

### LIKELY OVERENGINEERING (defer until proven needed)

| Item | Why Suspect | When It Becomes Needed |
|------|------------|----------------------|
| **[H] Graph versioning** | Classic YAGNI. Nobody has asked for snapshot/diff/restore. The current workflow is: build graph → query graph → done. | When mutation tools are used in production and someone needs to undo a bad edit. |
| **[J] Reified graph type** | Adds significant extraction complexity (new parser, diamond-pattern builder). No benchmark tests n-ary relationships. 2WikiMultiHopQA questions are binary property chains. | When building graphs from narrative text with complex events (intelligence analysis, not QA benchmarks). |
| **[K] Schema validation** | Only useful in closed/mixed mode, which itself isn't needed for current benchmarks. SUMO/PropBank may replace hand-curated type lists entirely. | When using domain-specific ontologies for controlled extraction. |
| **[L] Q-code resolution** | Wikidata linking is expensive and adds latency. HotpotQA entities don't need disambiguation — they're already named entities from Wikipedia. | When building cross-investigation graphs where "CIA" in doc 1 must link to "CIA" in doc 500. |
| **[M] Deep epistemic round-trip** | The round-trip is lossy (`DIGIMON_ATTRIBUTE_MAPPING.md` documents data loss: keywords, clusters, multi-source_ids). Fixing this is significant work for a use case (periodic deep epistemic analysis) that hasn't been demonstrated yet. | When actually using onto-canon's belief revision on DIGIMON graphs in a real workflow. |

### RECLASSIFIED: Not overengineering, but has a dependency chain

| Item | Status | Dependency |
|------|--------|-----------|
| **[N] Cypher queries** | Was "overengineering." Now: **high value but blocked by relation canonicalization**. Cypher's value scales directly with ontology constraint — with messy extracted edge labels, pattern matching fails on label mismatch. With canonicalized PropBank senses, `MATCH (f)-[:direct-01]->(p)` works reliably. Use [GrandCypher](https://github.com/aplbrain/grand-cypher) on NetworkX (proven by txtai). | Depends on: relation canonicalization (PropBank mapping) |
| **Relation canonicalization** | New item. Map extracted relation names → PropBank senses post-build. Configurable aggressiveness. Reuse onto-canon's AMR pipeline. | Depends on: nothing (onto-canon AMR infrastructure exists) |

### Two orthogonal configuration dimensions (new insight)

Ontology mode (extraction constraint) and canonicalization aggressiveness (post-extraction merge) are **independent**:

```
Extraction constraint:         open → mixed → closed       (prompt-level)
Canonicalization aggressiveness: none → conservative → aggressive  (post-build)
```

Canonicalization applies to three targets independently:
- **Entities** → merge "CIA" / "Central Intelligence Agency" / "the Agency" (via `match_entities_to_concepts`)
- **Relations** → merge "funded" / "bankrolled" / "gave money to" → `fund-01` (via PropBank)
- **Entity types** → merge "spy agency" / "intelligence org" → `GovernmentOrganization` (via SUMO)

SUMO/PropBank/FrameNet may make hand-curated ontology lists unnecessary — they ARE the principled minimal vocabulary. The aggressiveness setting controls how forcefully you map into them.

---

## Recommended Implementation Order

Based on the dependency analysis and essential vs overengineering classification:

### Phase 1: Benchmark-Critical Path

```
[A] HippoRAG converter → [E] Fair benchmark (build graph + run 1000 questions)
     └── in parallel:
[B] Entity canonicalization post-build step
```

**Rationale**: [A]+[E] gives us a comparable SOTA number. [B] may improve that number significantly (dedup helps multi-hop).

**Uncertainty**: Will entity canonicalization actually improve EM/F1? We believe it will because multi-hop questions require traversing from "United States" to facts about "US", but this is **unverified** (Assumption #6). Run benchmark once without canonicalization, once with, to measure.

### Phase 2: Technical Debt (Prompts as Data)

```
[F] Prompts as data (externalize 7 hardcoded prompts to YAML)
```

**Rationale**: Brian's design principle requires this. Every future prompt change is harder without it. But it doesn't change benchmark numbers, so it's not Phase 1.

### Phase 3: Graph Maintenance (if needed)

```
[C] Mutation tools → [G] Lightweight belief state
[D] Graph statistics
```

**Rationale**: Only implement if we find ourselves rebuilding graphs repeatedly to fix extraction errors. Currently the rebuild-from-checkpoint workflow is adequate.

### Phase 4: Advanced Features (defer)

```
[I] Ontology modes
[J] Reified graphs
[H] Versioning
[K]-[N] Everything else
```

**Rationale**: These serve future use cases (domain-specific extraction, event analysis, epistemic reasoning) that don't apply to the current benchmark goal.

---

## Open Questions

1. **Will entity canonicalization hurt precision?** Over-merging distinct entities (the known prompt quality issue) could *decrease* EM if "Bob Smith the politician" gets merged with "Bob Smith the scientist." Need to test on real data. **Mitigation**: Make merge aggressiveness configurable. `auto_merge_threshold` already exists as a parameter in `match_entities_to_concepts()` (concept_dedup.py:150). The prompt rules (lines 14-33 in `match_concepts.yaml`) should also be templatized with a `merge_aggressiveness` Jinja variable: `conservative` (only exact abbreviation/case matches, current "when in doubt, return null"), `moderate` (loosen place qualifiers + title variants), `aggressive` (merge on semantic similarity). This is consistent with prompts-as-data — the prompt is already YAML/Jinja, just needs one more variable.

2. **2WikiMultiHopQA vs HotPotQA?** **Decision: 2WikiMultiHopQA first.** Smallest corpus (6,119 paragraphs), fastest graph build, and multi-hop QA is what KG-RAG is supposed to excel at. HotPotQA second (9,811 paragraphs, most-reported).

3. **corpus_prepare auto-detection**: Can `corpus_format_parsers.py` handle HippoRAG corpus JSON directly? It auto-detects `text` field — might work for corpus. But question file still needs custom conversion regardless.

4. **Graph build cost for 10K paragraphs**: HotpotQA_200 (1,800 chunks) cost ~$X for graph build. HotpotQA full (9,811 paragraphs → ~10K chunks) will cost ~5x more. With fallback chain, Gemini rate limits may force fallback to DeepSeek/OpenAI, changing extraction quality.

5. **Canonicalization timing: post-build.** During-build is quadratic: each of ~360 batches checks new entities against a growing graph (batch 1: 50 vs 0, batch 360: 50 vs 17K). Total LLM token cost grows as O(chunks × cumulative_entities). Post-build is linear: collect all N nodes once, batch into groups of ~100, make ~N/100 LLM calls. For 17K nodes = ~170 calls, done once, O(N). Post-build also gives better dedup decisions because the LLM sees the full entity population.

---

## Synthesis

**The shortest path to a publishable result is**:

1. Write HippoRAG converter (~30 lines)
2. Build graph from HotpotQA corpus (~10K paragraphs)
3. Run 1,000-question benchmark
4. Compare to StepChain 66.7% EM / HippoRAG2 baseline

**Entity canonicalization is the highest-value enhancement** but should be measured as a delta, not assumed to help. Run benchmark without it first, then with it, report the difference.

**Everything in ADR-003 Suite 3 (mutation) and most of ADR-002 (ontology modes, reification, schema validation) is premature** for the benchmark goal. These serve the broader epistemic engine vision but don't help answer "can DIGIMON beat StepChain on HotPotQA?"

**Prompts-as-data is technical debt** that should be paid after the benchmark, not before. It's a design principle issue, not a capability issue.
