# Plan #8: Sentinel-Aware Extraction Supervisor Gating

**Status:** Completed
**Type:** implementation
**Priority:** High
**Blocked By:** Plan #7
**Blocks:** Trustworthy unattended extraction-family promotion

---

## Gap

**Current:** The extraction supervisor added in Plan #7 can baseline, rerun,
revert, and commit, but it still promotes changes on a single family-level mean
score.

**Target:** Make promotion role-aware:

1. use `case_role` metadata from the frozen family cases
2. require strict improvement on the promotion surface
3. reject any regression on protected sentinels

**Why:** Repo policy already says prompt/schema/validator changes must improve a
failure family without regressing protected sentinels. The supervisor should
enforce that policy directly instead of relying on average score movement alone.

---

## References Reviewed

- `CLAUDE.md`
- `docs/plans/05_extraction_quality_repair.md`
- `docs/plans/07_extraction_iteration_supervisor.md`
- `eval/extraction_prompt_eval.py`
- `eval/fixtures/musique_tkg_extraction_prompt_eval_cases.json`
- `eval/run_extraction_iteration_supervisor.py`

---

## Files Affected

- `docs/plans/08_supervisor_sentinel_gating.md` (create)
- `eval/run_extraction_iteration_supervisor.py` (modify)
- `tests/unit/test_extraction_iteration_supervisor.py` (modify)

---

## Progress

- 2026-03-22: The supervisor now loads family-filtered `case_role` metadata
  from the frozen cases and derives role-aware score snapshots from prompt-eval
  trial `input_id` data instead of relying on one aggregate mean alone.
- 2026-03-22: Promotion is now explicit and truthful:
  - strict gain on `target` score when target cases exist
  - otherwise strict gain on overall family score
  - no sentinel regression allowed when sentinel cases exist
- 2026-03-22: The loop ledger now records previous/current overall, target,
  sentinel, and promotion-basis fields plus the gate decision booleans.
- 2026-03-22: Unit tests now pin all three policy-critical cases:
  - target plus sentinel role parsing from prompt-eval trials
  - sentinel regression forces revert even when target score rises
  - the checked-in `grounded_named_endpoint_completeness` family really is
    sentinel-only, so overall fallback is tested against the real fixture

---

## Design

- Build a role index from the family-filtered frozen cases.
- Extract role-scoped scores from the prompt-eval artifact using trial-level
  `input_id` metadata.
- Use this promotion contract:
  - if `target` cases exist: target score must strictly improve
  - if no `target` cases exist: overall family score is the promotion surface
  - if `sentinel` cases exist: sentinel score must not decrease
- Fail loudly when a role is expected but the prompt-eval artifact has no scored
  trials for that role.

---

## Steps

1. Add typed role-aware score extraction helpers in the supervisor.
2. Replace the scalar improvement gate with a role-aware decision helper.
3. Record target/sentinel/overall scores in the ledger.
4. Update loop tests to cover:
   - target improvement + sentinel hold -> commit
   - target improvement + sentinel regression -> revert
   - no-target family fallback -> overall score drives promotion

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_extract_variant_score_snapshot_reads_role_scoped_scores` | supervisor can parse target and sentinel scores from prompt-eval trials |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_verified_improvement_requires_target_gain_and_no_sentinel_regression` | promotion rejects sentinel regressions even if target score rises |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_verified_improvement_falls_back_to_overall_when_family_has_no_target_cases` | checked-in completeness family remains promotable without fake target labels |

### Existing Tests

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_extraction_iteration_supervisor.py` | loop commit/revert behavior must remain proven with real git operations |

---

## Acceptance Criteria

- [x] the supervisor can derive target and sentinel case ids from the frozen family cases
- [x] role-aware score extraction uses prompt-eval trial `input_id` metadata rather than ad hoc heuristics
- [x] promotion requires strict gain on the target surface or overall fallback when no targets exist
- [x] sentinel regressions block promotion
- [x] loop tests prove revert-on-sentinel-regression and commit-on-target-improvement behavior

---

## Notes

- Do not invent fake target labels for the current `grounded_named_endpoint_completeness`
  slice just to satisfy the gate.
- Do not add another layer of prompt-eval summary files when the trial-level
  artifact already contains the required data.
