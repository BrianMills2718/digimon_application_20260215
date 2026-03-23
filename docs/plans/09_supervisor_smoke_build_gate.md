# Plan #9: Typed Smoke-Build Gate for the Extraction Supervisor

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** Plan #8
**Blocks:** Trustworthy unattended promotion beyond prompt-eval-only evidence

---

## Gap

**Current:** The extraction supervisor can now promote changes only when the
family-scoped prompt-eval gate improves without sentinel regressions, but it
still commits without proving that the live graph-build path remains healthy.

**Target:** Add a typed optional smoke-build gate between prompt-eval success
and commit:

1. run `eval/prebuild_graph.py` against a declared smoke slice
2. require successful process completion
3. require the expected graph artifacts to exist
4. revert on smoke-build failure

**Why:** Plans #5 and #6 already treat the small MuSiQue smoke rebuild as the
next real-corpus proof surface after prompt-eval. The supervisor should encode
that explicitly instead of letting prompt-only wins commit blindly.

---

## References Reviewed

- `docs/plans/05_extraction_quality_repair.md`
- `docs/plans/06_two_pass_extraction_proof.md`
- `docs/plans/07_extraction_iteration_supervisor.md`
- `docs/plans/08_supervisor_sentinel_gating.md`
- `eval/prebuild_graph.py`
- `tests/unit/test_prebuild_graph_cli.py`
- `ISSUES.md`
- investigation artifact `~/projects/investigations/Digimon_for_KG_application/2026-03-22-smoke-build-gate-design-review.md`

---

## Files Affected

- `docs/plans/09_supervisor_smoke_build_gate.md` (create)
- `eval/run_extraction_iteration_supervisor.py` (modify)
- `eval/continuous_extraction_iteration.grounded_named_endpoint.yaml` (modify)
- `tests/unit/test_extraction_iteration_supervisor.py` (modify)

---

## Design

- Add a typed `smoke_build` config section to the supervisor.
- Keep the first slice narrow and explicit:
  - source dataset
  - artifact dataset alias
  - graph profile
  - chunk limit
  - strict-slot / two-pass / grounded flags
  - lane policy
  - VDB skip flags
  - working dir
  - required artifacts
- The gate is operational, not semantic, in its first slice:
  - `prebuild_graph.py` exits successfully
  - required artifact paths exist under the configured working dir + artifact dataset
- Semantic artifact assertions can be a later extension once the operational gate
  is stable.

---

## Steps

1. Add typed supervisor config for a smoke-build gate.
2. Build the `prebuild_graph.py` command from that config.
3. Add required-artifact existence checks after a successful build.
4. Insert the smoke-build gate after prompt-eval success and before commit.
5. Revert and log when the smoke-build gate fails.
6. Update the checked-in completeness supervisor config with the first smoke slice.

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_build_smoke_build_command_respects_typed_config` | the supervisor emits the intended `prebuild_graph.py` contract |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_expected_smoke_artifact_paths_use_working_dir_and_alias` | artifact checks are derived from typed config, not hardcoded paths |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_run_loop_reverts_when_smoke_build_fails_after_prompt_eval_gain` | prompt-eval improvement alone is insufficient when the live smoke gate fails |

### Existing Tests

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_prebuild_graph_cli.py` | the smoke-build gate must stay aligned with the real build CLI contract |
| `tests/unit/test_extraction_iteration_supervisor.py` | prompt-eval gate behavior must remain intact while the smoke-build layer is added |

---

## Acceptance Criteria

- [ ] the supervisor config can declare a smoke-build slice without hidden hardcoded build values
- [ ] the supervisor can build a truthful `prebuild_graph.py` command from typed config
- [ ] successful smoke-build validation requires both process success and required artifact existence
- [ ] smoke-build failure reverts the worktree and blocks commit
- [ ] the checked-in completeness supervisor config includes the first smoke-build slice

---

## Notes

- The first smoke-build gate should prefer bounded runtime over completeness:
  skip VDB builds unless they are needed for a later gate.
- Do not collapse this into semantic graph-quality assertions yet. First prove
  that the supervisor can drive and verify the operational build path cleanly.
