# GraphRAG Current Status — 2026-03-26

**Single source of truth for benchmark results. Other docs link here, don't duplicate.**

## 50q MuSiQue Results (Latest, 2026-03-26)

| Metric | Baseline | GraphRAG | Delta |
|--------|----------|----------|-------|
| LLM-judge | 20.0% (10/50) | 42.0% (21/50) | +22.0 pts (2.1x) |
| Model | gpt-5.4-mini | gpt-5.4-mini | — |
| Cost | $0.01 | $1.81 | — |

Result files:
- Baseline: `results/MuSiQue_gpt-5-4-mini_baseline_20260326T074316Z.json`
- GraphRAG: `results/MuSiQue_gpt-5-4-mini_consolidated_20260326T080737Z.json`

## Cross-Reference (50q)

| Category | Count | Detail |
|----------|-------|--------|
| Graph wins | 15 | Baseline fails, GraphRAG succeeds |
| Both pass | 6 | Both answer correctly |
| Regressions | 4 | Baseline passes, GraphRAG fails |
| Both fail | 25 | Neither answers correctly |

## Iteration Gains (retesting both-fail + regression subsets)

| Subset | Tested | Flipped to PASS |
|--------|--------|-----------------|
| 2-hop both-fail | 9 | 2 (645448, 95970) |
| 3-hop both-fail | 8 | 1 (136129) |
| 4-hop both-fail | 8 | 1 (94201) |
| Regressions | 4 | 2 fixed (511296, 127483) |
| **Total iteration gains** | **29** | **6** |

Projected with iteration: ~27/50 (54.0% LLM-judge)
Note: "Projected" means these questions passed on re-run but the full 50q hasn't been re-run with all fixes.

## What's Implemented

- Plan #14: Benchmark runner ✅
- Plan #15: Operator consolidation (28→10 tools, 31 methods) ✅
- Plan #16: HippoRAG build attributes (PPR=0.5, passage nodes, co-occurrence) ✅
- Plan #20: Tool linearization + planning tools + prompt v3.3 ✅
- Bug fixes: PPR damping, chunk linearization data-loss, per-chunk timeout, lazy imports

## What's Blocking

1. **llm_client missing 6 post-eval exports** — benchmark crashes on post-eval. Workaround: `--post-det-checks none --post-gate-policy none`
2. **Graph not rebuilt** — passage nodes, co-occurrence edges not in current graph (stalled at 45%)
3. **Answer extraction errors** — 21 both-fail questions where agent finds evidence but picks wrong fact

## Next Actions

1. Fix llm_client exports OR migrate DIGIMON to canonical import paths
2. Implement llm_client Plan #19 (agent planning/working memory with harness enforcement)
3. Run confirmatory 50q with all fixes
4. HotpotQA cross-benchmark validation
5. Graph rebuild when memory/API quota allows
