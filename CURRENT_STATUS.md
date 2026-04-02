# GraphRAG Current Status — 2026-04-02

**Single source of truth for the latest benchmark comparison.**

Current implementation authority for the active frontier is in:

- `docs/plans/21_autonomous_failure_iteration_sprint.md`
- `docs/plans/22_benchmark_first_canonicalization_projection_hardening.md`
- `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md`

Use this file for the last result snapshot. Use the active plans for the
current failure family, next gate, and open uncertainties.

## 50q MuSiQue Results (2026-03-26, Plan #17 decision-grade run)

| Metric | Baseline | GraphRAG | Delta |
|--------|----------|----------|-------|
| LLM-judge | 20.0% (10/50) | 42.0% (21/50) | +22.0 pts (2.1x) |
| Model | gpt-5.4-mini | gpt-5.4-mini | — |
| Cost | $0.01 | $1.81 | — |

Result files:
- Baseline: `results/MuSiQue_gpt-5-4-mini_baseline_20260326T074316Z.json`
- GraphRAG: `results/MuSiQue_gpt-5-4-mini_consolidated_20260326T080737Z.json`

## 19q Diagnostic Results (2026-04-02, post-prompt-tuning)

| Metric | Pre-tuning | Post-tuning | Delta |
|--------|-----------|-------------|-------|
| LLM-judge | 26.3% (5/19) | 31.6% (6/19) | +5.3 pts |
| EM | 21.1% (4/19) | 26.3% (5/19) | +5.3 pts |
| Cost | $0.65 | $0.91 | — |

Result file: `results/MuSiQue_gpt-5-4-mini_consolidated_20260402T113854Z.json`

### What prompt tuning fixed
1. **Answer granularity matching** (+1 EM): "What year" → year only, not month+year (170823: "1986")
2. **Submit-immediately control flow** (+1 LLM_EM): Agent found answer but looped instead of submitting (511296: "Maria Shriver")
3. **Flexible atom resolution** (+1 LLM_EM): Agent found evidence with synonym phrasing but couldn't mark atom done (9285: "June" ≈ "mid-June")

### Remaining failure families (14 questions, 13 true failures + 1 LLM-judge pass)

| Family | Count | Description |
|--------|-------|-------------|
| QUERY_FORMULATION | 5 | Right tool, wrong query — answer in corpus but query didn't match |
| INTERMEDIATE_ENTITY_ERROR | 3 | Entity search returns wrong entity (e.g., Israel → "United States") |
| CONTROL_FLOW | 3 | Agent has evidence but can't complete atom lifecycle or submit |
| TOOL_SELECTION | 1 | Agent chose graph traversal when text search was needed |
| RETRIEVAL_RANKING | 1 | Right results but wrong item selected |
| ANSWER_SYNTHESIS | 1 | Evidence retrieved but wrong answer extracted |

### Key bottleneck: Retrieval stagnation

53-63% of questions hit the 4-turn stagnation limit well before the 20-call
tool budget. The agent makes similar searches that return the same results.
The bottleneck is **search quality**, not search quantity. This is a harness-level
issue, not a prompt issue.

### Stochasticity warning

Sentinel question 731956 passes ~50% of runs. Single-run single-question flips
are **stochastic noise**, not evidence of improvement. Promotion policy: ≥2 runs
showing same result, or ≥3 question improvement.

## Cross-Reference (50q, 2026-03-26)

| Category | Count | Detail |
|----------|-------|--------|
| Graph wins | 15 | Baseline fails, GraphRAG succeeds |
| Both pass | 6 | Both answer correctly |
| Regressions | 4 | Baseline passes, GraphRAG fails |
| Both fail | 25 | Neither answers correctly |

Projected with iteration: ~32/50 (64.0% LLM-judge). This projection is from
single-run reruns on subsets, not a full 50q confirmation.

## What's Implemented

- Plan #14: Benchmark runner ✅
- Plan #15: Operator consolidation (28→10 tools, 31 methods) ✅
- Plan #16: HippoRAG build attributes (PPR=0.5, passage nodes, co-occurrence) ✅
- Plan #17: Thesis test (42% LLM-judge on 50q, ANSWER_SYNTHESIS eliminated) ✅
- Plan #20: Tool linearization + planning tools + prompt v3.3 ✅
- Plan #25: Coordination prerequisite remediation ✅
- Prompt v3.4: Answer granularity, verification step, flexible relationships, short queries, search loops

## Active Work

- Plan #21: Failure iteration sprint (in progress, frozen tranche rerun pending)
- Plan #22: Canonicalization + projection hardening (in progress, Phase 2 rebuild in-flight)
- Plan #23: Semantic build boundary design (in progress, design phase)

## Next Actions

1. Make stagnation threshold configurable + test with higher limit
2. Close Plan #21 (frozen tranche rerun)
3. Assess Plan #22 projection results
4. Entity search quality improvements (top_k, fallback)
5. Full 50q confirmatory run with all improvements
