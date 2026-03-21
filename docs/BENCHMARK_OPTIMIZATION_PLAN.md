# Benchmark Optimization Plan: MuSiQue + HotpotQA 1000q

## Goal

Build all capabilities that improve benchmark scores BEFORE running the definitive 1000q evaluation. Run once, crush it.

## Context

- **Current best**: 52% EM / 80% LLM_EM on 50q MuSiQue (o4-mini, unenriched graph)
- **SOTA**: 53.6% top-20 accuracy (Youtu-GraphRAG, ICLR 2026, DeepSeek-V3)
- **Our LLM_EM is directly comparable** to their top-20 accuracy (both are LLM-judge answer accuracy)
- **Judge audit**: NOT lenient — 12/14 upgrades are legitimate formatting differences, p<0.001 vs SOTA
- **MuSiQue graph**: 82,526 nodes, 820,215 edges (enriched with co-occurrence + centrality)

## Model Strategy

- **Testing/iteration**: `deepseek/deepseek-chat` ($0.14/M input) — cheapest model with tool calling
- **Final 1000q run**: `gpt-4o` — comparable tier to DeepSeek-V3 used by Youtu
- **Judge**: `deepseek-chat` (matches Youtu's DeepSeek-V3 family)
- **Graph building**: `gemini/gemini-2.5-flash` (unchanged, $0.15/M)

## Build Sequence

### Phase 1: Validate Enrichment (1 hour)
**Status**: PENDING

Re-run MuSiQue 50q on the enriched graph (820K edges vs 127K) with deepseek-chat.
Establishes whether co-occurrence edges + centrality improve retrieval.

```bash
cd ~/projects/Digimon_for_KG_application
python eval/run_agent_benchmark.py \
  --dataset MuSiQue --num 50 \
  --model deepseek/deepseek-chat \
  --backend direct --mode fixed
```

**Success**: EM improves over unenriched baseline (52% EM). If not, investigate why.

### Phase 2: Add Reject Mode (2 hours)
**Status**: PENDING

Prompt change to `agent_benchmark_adaptive.yaml` and `agent_benchmark.yaml`:
- Add instruction: "If retrieved context is insufficient to answer confidently, respond with INSUFFICIENT_CONTEXT"
- Update `submit_answer` to accept this as a valid response
- Score rejected answers: correct rejection = 1.0 if gold answer is unanswerable, 0.0 otherwise
- Report both Open mode (must answer) and Reject mode (can abstain) scores

Youtu evaluates in both modes. This gives direct comparability.

### Phase 3: Prompts as Data (1 day)
**Status**: PENDING

Move extraction prompts from `Core/Prompt/GraphPrompt.py` to Jinja2/YAML templates in `prompts/extraction/`.
Load via `llm_client.render_prompt()`. No behavior change — pure externalization.

**Files to create**:
- `prompts/extraction/tkg_extraction.yaml` — TKG delimiter-based extraction
- `prompts/extraction/gleaning.yaml` — shared gleaning template
- `prompts/graph_types/tkg.yaml` — graph type config

**Files to modify**:
- `Core/Prompt/GraphPrompt.py` — become a loader, not a container
- `Core/Graph/ERGraph.py` — load prompts from templates

This unblocks schema-constrained extraction (Phase 4).

### Phase 4: Schema-Constrained/Schema-Guided Extraction (1-2 days)
**Status**: PENDING

Wire `open`, `schema_guided`, and `schema_constrained` modes into the extraction pipeline.

**Design**: ADR-002 (`docs/adr/002-universal-graph-schema-and-extraction.md`)
**Existing code**: `~/projects/Digimons/src/core/extraction_schemas.py` + `schema_manager.py`

**Config addition** to project config:
```yaml
graph:
  schema_mode: "schema_guided"  # "open" | "schema_guided" | "schema_constrained"
  ontology:
    entity_types:
      - person: "A human individual"
      - organization: "A company, government, or group"
      - location: "A geographic place"
      - event: "A specific occurrence"
    relation_types:
      - employed_by: "Person works for organization"
      - located_in: "Entity is in a location"
      - founded_by: "Person/org founded another org"
```

**Prompt template** (Jinja2 conditionals):
```
{% if schema_mode == "schema_constrained" %}
ONLY extract entities matching these types: {{ entity_types }}
{% elif schema_mode == "schema_guided" %}
Prefer these types: {{ entity_types }}
Mark genuinely new types with [NEW] prefix.
{% endif %}
```

**Decisions needed**:
- Which entity/relation types for MuSiQue? (multi-hop QA about Wikipedia articles — mostly person, org, location, event, work_of_art)
- Use `schema_guided` (safer) or `schema_constrained` (more constrained)?
- Port schema classes from Digimons or rewrite simpler versions?

### Phase 5: Build Communities on MuSiQue (2 hours)
**Status**: PENDING

Run community detection on enriched graph. Add community-first retrieval strategy to adaptive prompt.

```bash
# Via MCP or direct Python
build_communities(dataset_name="MuSiQue", algorithm="leiden", resolution=1.0)
```

Update `agent_benchmark_adaptive.yaml` with community-aware strategy:
- For broad/comparison questions: start with community summaries, filter down
- For specific entity questions: use current VDB→onehop→chunk flow

### Phase 6: Synonym Edge Enrichment (1 hour)
**Status**: PENDING

Run `augment_synonym_edges` on MuSiQue graph. This uses entity VDB embeddings to find near-duplicate entities and adds explicit edges between them (e.g., "CIA" ↔ "Central Intelligence Agency").

Already implemented — just needs to be executed on the MuSiQue graph.

### Phase 7: Rebuild MuSiQue Graph (6 hours, ~$30)
**Status**: PENDING — only if schema-constrained extraction is ready

Rebuild the MuSiQue graph from scratch with:
- Schema-guided/schema-constrained mode (Phase 4)
- All enrichments applied post-build: co-occurrence + centrality + synonym edges + communities

Compare node/edge counts and entity type distribution against the open-mode graph.

**Decision point**: If schema-constrained extraction isn't ready or doesn't look promising on a small test, skip the rebuild and use the current enriched graph. The enrichments (Phase 5-6) can be applied to the existing graph without rebuilding.

### Phase 8: Tune Agent Prompt (2 hours)
**Status**: PENDING

Iterate the adaptive prompt on 50q with all capabilities available:
- Reject mode active
- Community-first strategy for appropriate questions
- Synonym edges available for traversal
- Schema-constrained graph (if rebuilt)

Run 2-3 iterations with deepseek-chat, analyze failures, adjust.

### Phase 9: Final 1000q Runs (cost: ~$30-50 total)
**Status**: PENDING — do NOT start until all above phases complete

```bash
# MuSiQue 1000q with gpt-4o
python eval/run_agent_benchmark.py \
  --dataset MuSiQue --num 1000 \
  --model gpt-4o \
  --backend direct --mode adaptive

# HotpotQA 1000q with gpt-4o
python eval/run_agent_benchmark.py \
  --dataset HotpotQA --num 1000 \
  --model gpt-4o \
  --backend direct --mode adaptive
```

Report: EM, F1, LLM_EM (Open mode), LLM_EM (Reject mode), cost, tokens, tools/question.

## What We're NOT Doing (Deferred)

- **Entity canonicalization** — risk of over-merging on benchmark. Synonym edges provide traversal shortcuts without merge risk. Revisit if failure analysis shows entity confusion.
- **Relation canonicalization** (PropBank/FrameNet) — valuable for downstream query but not for EM scoring
- **Reified graph type** (n-ary relationships) — intelligence analysis use case, not QA benchmarks
- **Structured output tool shim** for flash-lite — filed as `PROJECTS_DEFERRED/llm_client_structured_output_tool_shim.md`

## Metrics to Report (matching Youtu-GraphRAG Table 1)

| Metric | Our name | Notes |
|--------|----------|-------|
| Top-20 Accuracy (Open) | LLM_EM | LLM judge, must answer |
| Top-20 Accuracy (Reject) | LLM_EM_reject | LLM judge, can abstain |
| EM | EM | Exact match |
| F1 | F1 | Token-level F1 |
| Token cost | cost | Per-query average |
| Tools/query | tools_per_q | Agent tool calls per question |

## Date

2026-02-18
