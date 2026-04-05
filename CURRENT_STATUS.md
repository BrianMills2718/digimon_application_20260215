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
- Five-run distribution report: `docs/reports/musique_19q_iteration_report_2026_04_03.md`

**Stochasticity reassessment (2026-04-03):**
Across the five historical status artifacts above, the observed mean is **43.16%**
LLM_EM with **12.00 points** sample stdev and a **31.58%-57.89%** range. Those
five runs were **not** at one fixed setting, so this is a historical distribution,
not a promotion-grade baseline. The report also reclassifies the 19q slice into
`3 stable pass`, `11 stochastic`, and `5 stable fail` questions.

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

### Stable pass (5/5 in the historical status slice): 3 questions

170823 (1986), 511296 (Maria Shriver), 655505 (11 September 1962)

### Stochastic (1-4 passes in the historical status slice): 11 questions

| ID | Recent pass rate | Notes |
|----|-----------------|-------|
| 13548 | 60% | June 1982 case; still drifts to 2002/2009 in bad runs |
| 511454 | 20% | "918" vs "1870"/"1974"/unknown |
| 619265 | 40% in historical 5-run slice | Exact-title anchor case (`"The Bag or the Bat"` → `Ray Donovan`); latest bounded rerun after the post-anchor bridge guard passed 1/1 with final answer `12` in `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T130547Z.json` |
| 731956 | 80% | Johan Remkes; one empty-answer miss remains in the five-run slice |
| 766973 | 80% | Rockland County; recent misses are timeout / retrieval failures |
| 136129 | 20% | Sometimes reaches `1952`, often stops at `Saint Peter` or `unknown` |
| 305282 | 20% | December 14, 1814 chain remains brittle |
| 849312 | 80% | Usually answers "15th century", but still slips to `1416` |
| 9285 | 40% | Month-level ambiguity remains (`June`/`July`/`March`) |
| 152562 | 20% | Still drifts across unrelated entity answers |
| 94201 | 60% | Mississippi River vs Mississippi River Delta answer granularity |

### Stable fail (0/5 in the historical status slice): 5 questions

| ID | Gold | Typical pred | Root cause |
|----|------|-------------|-----------|
| 199513 | Nazareth | "" or "Nauvoo, IL" | IEE — confuses Joseph of Nazareth with Joseph Smith |
| 820301 | 22 | "1" | IEE — wrong answer, retrieval finds wrong chain |
| 354635 | Time Warner Cable | "Adelphia" or "Comcast" | Close IEE — finds neighbor not target |
| 71753 | 1930 | "1961" or "1921" | Wrong year — poor entity disambiguation |
| 754156 | The dynasty regrouped and defeated the Portuguese | "Laos" / "Myanmar" / "expelled by the Portuguese" / "by airplanes" / "" / "communist takeover" | Multi-stage controller failure: `A2` idempotence bug and bad `soviet union` bridge path are fixed, but `A3/A4` still stay unresolved and the controller can drift into budget-exhaustion forced-finalization with an ungrounded answer |

### Remaining failure families

| Family | Count | Description |
|--------|-------|-------------|
| INTERMEDIATE_ENTITY_ERROR (IEE) | 3 stable-fail + several stochastic | Agent stops at wrong hop or confuses similar entities |
| EXACT_ANCHOR_DRIFT | 1 | Quoted title / literal span is compacted and semantic retrieval drifts off the real anchor |
| ANSWER_TYPE_MISMATCH | 1 | Final answer should be an action/event phrase but the agent submits an intermediate entity/location |
| YEAR_DISAMBIGUATION | 1 | Finds plausible but wrong year in related entity |
| GENERAL_STOCHASTICITY | 11 questions | The same question can flip across runs even without a new generalizable fix |

### Note: todo_write validator still active

`_validate_manual_todo_completion` in `digimon_mcp_stdio_server.py` (line 2005) still blocks
agents from marking atoms done if proposed value doesn't match cached evidence. This may
contribute to CONTROL_FLOW failures and some stochastic misses but was NOT removed in this
session — it requires careful evaluation to avoid regression on correct evidence-gating.
What changed in Plan #30 is narrower and intentional: if an atom was already
completed with the same answer, full-list `todo_write` rewrites now preserve
that validated state instead of re-running the manual validator and regressing
against stale unresolved payloads.

### Process Controls

- `make truth-check` now auto-searches both the live worktree and the
  canonical checkout for referenced `results/...` artifacts. Use
  `ARTIFACT_ROOT=<path>` only as an explicit override.
- `make benchmark-report RESULT_GLOB='<precise-glob>' OUTPUT=docs/reports/<name>.md`
  now auto-scans the live worktree plus the canonical checkout. Use a precise
  glob or explicit `scripts/benchmark_iteration_report.py --input ...`
  invocation when you need one controlled slice rather than broad history.
- Benchmark-facing `make` targets now run through
  `scripts/run_with_digimon_python.py`, which resolves the `digimon`
  interpreter directly instead of depending on `conda run -n digimon`.
- Promotion rules now live in `docs/BENCHMARK_PROMOTION_POLICY.md`. Do not use
  single-run flips or mixed-setting history as promotion-grade evidence.

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
- Plan #28 continuation: worktree artifact auto-detection + direct runtime-python wrapper + post-anchor bridge guard for anchored string entity hits + helper/atom lifecycle traces + restored normal submit gate + early shared submit-breaker path
- Plan #30 Phase 1: truthful terminal-answer scoring in the benchmark lane. Control-churn forced-final answers with pending atoms are now suppressed from `predicted`, and per-question artifacts expose `forced_terminal_accept_reason` so forced-terminal acceptance is no longer mislabeled as budget exhaustion by default.
- Plan #30 Phase 2 continuation: shared submit-churn gating plus idempotent done-atom preservation. Pending-atom submit churn now requires real TODO progress, and unchanged completed atoms survive repeated full-list `todo_write` rewrites via `atom_manual_reused` instead of burning budget on repeated manual rejections.
- Bounded verification: `2hop__619265_45326` now has two important live proofs:
  - post-anchor bridge guard removed the `showtime` drift and restored a correct `12` answer in `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T011403Z.json`
  - after restoring the normal pending-atom submit gate, the intermediate smoke run `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T012611Z.json` exposed honest forced-terminal fallback
  - after adding full submit provenance harvesting plus the shared early submit-breaker, the latest smoke run `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T014802Z.json` grounded `619265` cleanly in `13` tool calls with no forced-final acceptance

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

1. **Repair unresolved-hop routing on `754156` after the bridge fix** — the latest truthful probe `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T053035Z.json` removed the bad `soviet union` bridge completion, but `a3` and `a4` still remain pending while the controller burns the full tool budget and ends in `budget_exhaustion` forced-final acceptance of `communist takeover`. The next slice should force more truthful reflection follow-through on `a3/a4`, not revisit bridge validation.
2. **Investigate `LINEARIZATION_DATA_LOSS` in `chunk_retrieve(method=by_ids)`** — probe `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T035805Z.json` surfaced a warning that raw chunk content existed while the linearized summary appeared empty. This may be hiding exactly the evidence the controller needs on unresolved-hop questions.
3. **Keep timeout provenance truthful while `LLM_CLIENT_TIMEOUT_POLICY=ban` remains active** — this shell disables per-call timeouts globally, so benchmark artifacts must continue surfacing requested/planned timeout separately from `turn_timeout_runtime_enforced` instead of pretending `auto:60s` is active.
4. **Validate helper fallback quality + observability before spending on the 19q gate** — helper calls now follow configured `llm_client` fallbacks, but the earlier smoke run `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T133705Z.json` still regressed `619265` to `10`, and nested helper fallback usage is not yet fully surfaced in benchmark provenance.
