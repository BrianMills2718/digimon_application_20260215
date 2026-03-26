# GraphRAG Current Status — 2026-03-26

## 50q MuSiQue Results (Best)

| Metric | Baseline | GraphRAG | Delta |
|--------|----------|----------|-------|
| LLM-judge | 20.0% (10/50) | 42.0% (21/50) | +22.0 pts |
| With iteration gains | — | ~54.0% (27/50) projected | +34.0 pts |

## Iteration Results

| Category | Count | Detail |
|----------|-------|--------|
| Graph wins | 15 | Baseline fails, GraphRAG succeeds |
| Both pass | 6 | Both answer correctly |
| Regressions | 4 (2 fixed) | 2 still regressing |
| Both fail | 25 (4 flipped) | 21 remaining |

## What Worked

1. **Operator consolidation** (28→10 tools) — agent uses graph operators instead of just text search
2. **Tool result linearization** — NL summaries instead of raw JSON, 50% context savings
3. **Planning tools** (semantic_plan + todo_write) — agent plans before retrieving
4. **Prompt v3.3** — planning-first flow, retry strategies, indirect references, date ranges
5. **PPR damping 0.5** — HippoRAG-aligned (was 0.15, a critical bug)
6. **Chunk linearization data-loss fix** — chunk_retrieve(by_ids) was silently returning empty

## What's Blocking Further Progress

1. **Answer extraction errors** — agent finds right evidence, picks wrong fact (21 failures)
   - Fix: llm_client Plan #19 (harness-level plan enforcement) + stronger model
2. **2 remaining regressions** — baseline gets right, GraphRAG gets wrong
   - Fix: investigate why graph noise hurts these specific questions
3. **Graph not rebuilt** — stalled at 45% due to OOM/timeouts
   - Fix: smaller graph or more RAM; per-chunk timeout now implemented

## Next Steps (for next agent)

1. **Implement llm_client Plan #19** (agent planning/working memory) — file-based plan state + auto-injected context + submit enforcement
2. **Fix llm_client exports** — restore triage_items, build_gate_signals, etc. (or fix DIGIMON to use canonical paths)
3. **Run confirmatory 50q** — full run with all fixes to get definitive number
4. **Scale to 100q** — larger sample for statistical confidence
5. **Diagnose remaining 21 both-fail** — are they extraction misses or model capability?

## Key Files

- `NEXT_STEPS.md` — execution plan
- `notebooks/plan17_thesis_retest.ipynb` — planning notebook
- `eval/fixtures/musique_*` — question ID sets for iteration
- `scripts/diagnose_question.py` — per-question trace analysis
- `Core/MCP/tool_consolidation.py` — consolidated tools with linearization
- `prompts/agent_benchmark_consolidated.yaml` — prompt v3.3
