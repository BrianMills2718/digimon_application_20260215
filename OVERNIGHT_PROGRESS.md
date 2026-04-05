# Overnight Progress

## Mission

Keep the maintained DIGIMON benchmark lane truthful overnight by:

1. preventing ungrounded forced-final answers from being scored like valid submits,
2. stopping unresolved-hop submit churn from escalating into scored answers,
3. verifying that recovery/reflection changes materially alter controller behavior.

## Acceptance Criteria

- Benchmark artifacts distinguish planned timeout from runtime-enforced timeout.
- A control-churn forced-final answer with pending atoms is not preserved as a
  scored prediction.
- `754156`-style runs either ground the remaining atoms or fail honestly rather
  than ending as scored forced-final answers.
- Each verified slice lands as its own commit from this worktree.

## Current Phase

- Phase 0 complete.
- Phase 1 complete.
- Phase 2 complete.
- Next active phase: Phase 3 — Recovery Loop Strengthening.

## Current Verified Blocker

- Artifact `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T054718Z.json`
  is the latest truthful controller probe. It validates the narrowed
  recovery-surface guard: the earlier `a2` mis-blocking regression from
  `...T053930Z.json` is gone, `a4` is no longer pending, and the controller
  reaches the Portuguese hop without policy-induced drift.
- The earlier repeated `todo_write` runtime-error loop is gone. The same probe
  shows `atom_manual_reused` events for completed atoms (`a2`, later `a3`)
  instead of repeated `atom_manual_rejected` failures, so unchanged done atoms
  now survive full-list `todo_write` rewrites idempotently.
- The next blocker is now unchanged-evidence submit churn around unresolved
  `a3`, not bad bridge acceptance: the run still ends in
  `submit_completion_mode='missing_required_submit'`,
  `forced_terminal_accept_reason='budget_exhaustion'`, and seven tool-call
  errors after repeated rejected submit attempts and broad late chunk/entity
  loops.
- New runtime clue from `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T035805Z.json`:
  `chunk_retrieve(method=by_ids)` can emit `LINEARIZATION_DATA_LOSS` warnings
  when raw tool content exists but the linearized summary says empty. This is a
  likely Phase 3 contributor because it can hide evidence from the controller.

## Notes

- Work only from dedicated worktrees.
- Commit every verified slice immediately.
- If a new uncertainty appears, record it here and in the active plan before
  proceeding.
- Verification restored for this slice:
  - `pytest -q tests/test_tool_consolidation.py tests/unit/test_semantic_plan_query_contract.py tests/unit/test_benchmark_tool_modes.py`
  - `101 passed`
  - `make truth-check` clean
