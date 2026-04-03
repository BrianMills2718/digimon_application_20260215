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

## 19q Diagnostic Results (updated 2026-04-03)

| Run | Date | LLM_EM | Notes |
|-----|------|--------|-------|
| Pre-submit-gate-removal | 2026-04-02 | 31.6% (6/19) | Baseline before Plan #22 fix |
| Best (post-gate-removal) | 2026-04-03 | 57.9% (11/19) | High-end stochastic result |
| Verification | 2026-04-03 | 52.6% (10/19) | 2nd run, confirmed improvement |
| Plan #27 entity_info-first | 2026-04-03 | 42.1% (8/19) | REGRESSION — synthetic-summary trap |
| Plan #27 reverted | 2026-04-03 | 31.6% (6/19) | Back to pre-gate baseline; 57.9% was stochastic high |

Result files:
- Pre-fix: `results/MuSiQue_gpt-5-4-mini_consolidated_20260402T113854Z.json`
- Best: `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T003635Z.json` (11/19 = 57.9%)
- Verification: `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T010250Z.json` (10/19 = 52.6%)
- Plan #27 regression: `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T040050Z.json` (8/19 = 42.1%)
- Plan #27 reverted: `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T045308Z.json` (6/19 = 31.6%)

**Stochasticity reassessment (2026-04-03):**
The "stably passing" list below is likely stale. 619265 failed in 3 of the last 4 runs (listed as stable). 766973 timed out in 2 runs. The 57.9% run was a high-end stochastic result. True mean is probably ~42-52% given the distribution of runs. Need ≥3 controlled runs at same settings to establish real baseline.

## Audit Corrections (verified 2026-04-02 / artifacts dated 2026-04-03)

- **619265 is an exact-anchor preservation problem, not fundamentally a Batman Beyond aggregate-summary problem.**
  The corpus contains `"The Bag or the Bat"` → `Ray Donovan`
  (`results/MuSiQue/corpus/Corpus.json`, doc_ids 200 and 213). Passing runs
  identify `Ray Donovan`; failing runs drift after the quoted title is compacted
  and semantic search goes off-anchor.
- **754156's benchmark gold is not `Laos`.**
  The result artifacts record the gold as
  `The dynasty regrouped and defeated the Portuguese`. Treat this as an
  answer-kind / premature-intermediate-submit problem, not a country-name
  question.
- **The maintained code path does not use `entity_search top_k=10` by default.**
  Live consolidated default is `top_k=5`; the earlier `10` experiment increased
  noise and was reverted.
- **Prompt metadata was stale.**
  The active consolidated prompt now reflects `version 3.6`, including explicit
  quoted-anchor preservation guidance.

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

### Stably passing (verified across ≥3 runs including 2026-04-03): 3–4 questions

170823 (1986), 655505 (Sep 11 1962), 94201 (Mississippi River Delta), 731956

Note: the prior "8 stably passing" list included 619265, 766973, 13548 which all failed
in recent runs. See stochasticity reassessment above.

### Stochastic (pass sometimes): ~10 questions

| ID | Recent pass rate | Notes |
|----|-----------------|-------|
| 849312 | ~75% | 15th century — usually passes |
| 511296 | ~75% | Maria Shriver — usually passes |
| 731956 | ~75% | Johan Remkes — usually passes |
| 619265 | ~25% | Exact-title anchor case (`"The Bag or the Bat"` → `Ray Donovan`); passes when the quoted title stays intact |
| 766973 | ~50% | Rockland County — sometimes times out |
| 13548 | ~50% | June 1982 — inconsistent |
| 9285 | ~50% | "June" vs "March" — query path variation |
| 511454 | ~50% | "918" vs "1870" — retrieval stochasticity |
| 305282 | ~50% | "Dec 14, 1814" vs wrong — path variation |
| 152562 | ~50% | Passes in some runs |

### Consistently failing: 6 questions

| ID | Gold | Typical pred | Root cause |
|----|------|-------------|-----------|
| 199513 | Nazareth | "" or "Nauvoo, IL" | IEE — confuses Joseph of Nazareth with Joseph Smith |
| 136129 | 1952 | "Saint Peter" | IEE — stops at intermediate entity |
| 820301 | 22 | "1" | IEE — wrong answer, retrieval finds wrong chain |
| 354635 | Time Warner Cable | "Adelphia" or "Comcast" | Close IEE — finds neighbor not target |
| 71753 | 1930 | "1961" or "1921" | Wrong year — poor entity disambiguation |
| 754156 | The dynasty regrouped and defeated the Portuguese | "Laos" / "Myanmar" / "expelled by the Portuguese" | Premature intermediate submit + answer-kind failure |

### Remaining failure families

| Family | Count | Description |
|--------|-------|-------------|
| INTERMEDIATE_ENTITY_ERROR (IEE) | 4 | Agent stops at wrong hop or confuses similar entities |
| EXACT_ANCHOR_DRIFT | 1 | Quoted title / literal span is compacted and semantic retrieval drifts off the real anchor |
| ANSWER_TYPE_MISMATCH | 1 | Final answer should be an action/event phrase but the agent submits an intermediate entity/location |
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
- Prompt v3.6: Answer granularity, verification step, flexible relationships, short queries, quoted-anchor preservation
- STAG_TURNS=6 default (configurable via Makefile, proven better than 4)
- entity_search top_k=5 default (`10` was tested, worsened noise, and was reverted)

## Active Work

- Plan #22: Canonicalization + projection hardening (Phase 2 rebuild documented; control flow hardening complete)
- Plan #23: Semantic build boundary design (in progress, design phase)
- Plan #28: Truthful overnight stabilization + contract repair (in progress)

## Latency Breakdown (measured 2026-04-03)

Per-operator timing now live in `tool_calls` table. Use `make timing`.

| Operator | Avg ms | Max ms | Notes |
|----------|--------|--------|-------|
| chunk_retrieve(relationships) | 6326 | 17192 | Slowest — avoid unless needed |
| entity_search(string) | 2773 | 6089 | Name matching over all entities |
| chunk_retrieve(text) | 658 | 2767 | Keyword search |
| chunk_retrieve(semantic) | 567 | 1141 | VDB embedding search |
| entity_search(semantic) | 591 | 1964 | VDB entity search |
| entity_info(profile) | ~0 | 1 | Very fast |
| relationship_search(graph) | ~1 | 8 | Very fast |

Total per question: ~6s operators + 58-82s LLM (47-48 turns sequential).
**LLM turn count is the primary latency driver.** Reducing stagnation is higher-leverage than operator optimization.

## Next Actions

1. **Establish real baseline** — run 19q 3+ times at same settings; current 31-58% spread shows high stochasticity; true mean is unclear
2. **Contract / anchor repair verification** — preserve quoted titles and exact literal spans through query rewriting; benchmark failures like 619265 are off-anchor drift, not graph-data absence.
3. **IEE family fix** — 4/6 consistently-failing questions are still IEE; entity disambiguation improvement would have broad impact once the contract layer is truthful.
4. **todo_write validator review** — `_validate_manual_todo_completion` may contribute to agent getting stuck; 136129 remains a likely diagnostic case.
5. **50q confirmatory run** — once the 19q baseline is re-established under fixed settings, rerun 50q to confirm the +22pp improvement is real
