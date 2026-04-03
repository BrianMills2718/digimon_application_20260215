# GraphRAG Current Status — 2026-04-03

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

## 19q Diagnostic Results (2026-04-03, post-submit-gate-removal)

| Metric | Pre-fix baseline | Best run | Avg (2 runs) | Delta |
|--------|-----------------|----------|--------------|-------|
| LLM-judge | 31.6% (6/19) | 57.9% (11/19) | ~55% | +21–26 pts |
| missing_required_submit | 13/19 | 1/19 | ~1/19 | -12 |
| Cost per run | $0.91 | ~$0.35 | ~$0.35 | — |

Result files:
- Pre-fix: `results/MuSiQue_gpt-5-4-mini_consolidated_20260402T113854Z.json`
- Best: `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T003635Z.json` (11/19 = 57.9%)
- Verification: `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T010250Z.json` (10/19 = 52.6%)

### What submit gate removal fixed (+21pp improvement)

The primary fix was removing three blocking validators in `digimon_mcp_stdio_server.py`
and `Core/MCP/tool_consolidation.py`:

1. **Atom-completion gate** (biggest impact): Blocked submit_answer when any todo atom was
   pending. Agents were calling submit_answer as their final tool call and getting rejected.
   After rejection they ended the conversation with empty predictions. 10-13/19 questions
   affected. Root cause of `missing_required_submit` failures.

2. **Refusal-style check** (`_ANSWER_REFUSAL_RE`): Blocked answers containing "cannot",
   "unknown", etc. Blocked 199513 (Nazareth) 7 times — agent had correct answer in todo_write
   but hedged in the reasoning text. Removed because LLM-judge evaluates answer quality;
   string matching is too blunt.

3. **Negation prefix checks**: Blocked answers starting with "not" or "no". Over-aggressive,
   removed together with refusal check.

All three were in `digimon_mcp_stdio_server.py` submit_answer (lines ~8633–8662). The only
remaining check: empty-answer rejection.

### Prompt changes (earlier, +5pp)
1. **Answer granularity matching**: "What year" → year only, not month+year
2. **Submit-immediately control flow**: "after 4+ failed atom attempts, submit your best guess"
3. **Flexible atom resolution**: Accept synonym phrasing when marking atoms done

### Stably passing (≥2 runs): 8 questions

13548, 766973, 655505, 619265, 849312, 511296, 731956, 170823

### Stochastic (pass sometimes): 4–5 questions

| ID | Pass rate | Notes |
|----|-----------|-------|
| 9285 | ~50% | "June" vs "March" — query path variation |
| 511454 | ~50% | "918" vs "1870" — retrieval stochasticity |
| 305282 | ~50% | "Dec 14, 1814" vs wrong — path variation |
| 94201 | ~50% | "Mississippi River delta" vs "Minneapolis" (intermediate entity) |
| 152562 | ~50% | Passes in some runs |

### Consistently failing: 6 questions

| ID | Gold | Typical pred | Root cause |
|----|------|-------------|-----------|
| 199513 | Nazareth | "" or "Nauvoo, IL" | IEE — confuses Joseph of Nazareth with Joseph Smith |
| 136129 | 1952 | "Saint Peter" | IEE — stops at intermediate entity |
| 820301 | 22 | "1" | IEE — wrong answer, retrieval finds wrong chain |
| 354635 | Time Warner Cable | "Adelphia" or "Comcast" | Close IEE — finds neighbor not target |
| 71753 | 1930 | "1961" or "1921" | Wrong year — poor entity disambiguation |
| 754156 | Laos | "expelled by the Portuguese" | Wrong type — text phrase not entity name |

### Remaining failure families

| Family | Count | Description |
|--------|-------|-------------|
| INTERMEDIATE_ENTITY_ERROR (IEE) | 4 | Agent stops at wrong hop or confuses similar entities |
| ANSWER_TYPE_MISMATCH | 1 | Retrieves relationship description, not entity name |
| YEAR_DISAMBIGUATION | 1 | Finds plausible but wrong year in related entity |

### Note: todo_write validator still active

`_validate_manual_todo_completion` in `digimon_mcp_stdio_server.py` (line 2005) still blocks
agents from marking atoms done if proposed value doesn't match cached evidence. This may
contribute to CONTROL_FLOW failures and some stochastic misses but was NOT removed in this
session — it requires careful evaluation to avoid regression on correct evidence-gating.

### Stochasticity policy

Single-run single-question flips are noise. Promotion policy: ≥2 runs same result, or
≥3 question net improvement. The +21pp improvement shown above is stable (2 runs, net +5q).

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
- Plan #21: Failure iteration sprint ✅ (closed — see plan for findings)
- Plan #22: Control flow hardening ✅ (submit gate + refusal checks removed, +21pp on 19q)
- Plan #25: Coordination prerequisite remediation ✅
- Prompt v3.4: Answer granularity, verification step, flexible relationships, short queries, search loops
- STAG_TURNS=6 default (configurable via Makefile, proven better than 4)
- entity_search top_k=10 default

## Active Work

- Plan #22: Canonicalization + projection hardening (Phase 2 rebuild documented; control flow hardening complete)
- Plan #23: Semantic build boundary design (in progress, design phase)

## Next Actions

1. **Full 50q confirmatory run** — 19q went from 42% → 55% after gate removal; need 50q to confirm real gain (budget: needs ~$1.50 per run)
2. **IEE family fix** — 4/6 consistently-failing questions are IEE; entity disambiguation improvement would have broad impact
3. **todo_write validator review** — `_validate_manual_todo_completion` may need adjustment; balance evidence-gating vs agent getting stuck
4. **754156 (Laos) answer type** — agent returns relationship phrase not entity name; likely answer synthesis issue
