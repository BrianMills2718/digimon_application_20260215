# Plan #11: Strengthen Completeness Promotion Gating

**Status:** Complete
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Further unattended grounded-endpoint supervisor cycles

---

## Gap

**Current:** The grounded-endpoint completeness target can still score `0.95`
while missing `throat cancer` as a standalone entity record, because the
current evaluator blends required-entity recall and forbidden-entity
suppression into one lightly weighted `entity_policy` score and the supervisor
promotes on overall target mean.

**Target:** The evaluator exposes required-entity recall explicitly and the
supervisor can promote completeness families on that metric instead of only on
overall score.

**Why:** A failure family named `grounded_named_endpoint_completeness` must not
be promotable while required endpoint entities are still absent.

---

## References Reviewed

- `eval/extraction_prompt_eval.py` - current `entity_policy` scoring and overall weighting
- `eval/run_extraction_iteration_supervisor.py` - current promotion-basis extraction and gate logic
- `eval/continuous_extraction_iteration.grounded_named_endpoint.yaml` - active unattended family config
- `docs/plans/05_extraction_quality_repair.md` - current extraction-quality target
- `docs/plans/10_open_schema_type_contract.md` - just-completed open-schema repair
- `/home/brian/projects/investigations/Digimon_for_KG_application/2026-03-22-completeness-gate-strength-review.md` - evidence for the gate-strength issue

---

## Files Affected

- `docs/plans/11_completeness_promotion_gate.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `eval/extraction_prompt_eval.py` (modify)
- `eval/run_extraction_iteration_supervisor.py` (modify)
- `eval/continuous_extraction_iteration.grounded_named_endpoint.yaml` (modify)
- `tests/unit/test_extraction_prompt_eval.py` (modify)
- `tests/unit/test_extraction_iteration_supervisor.py` (modify)

---

## Plan

## Progress

- 2026-03-22: The evaluator now exposes `required_entity_recall` and
  `forbidden_entity_suppression` as explicit zero-weight dimensions while
  preserving the legacy combined `entity_policy` score for overall-score
  continuity.
- 2026-03-22: The extraction supervisor now supports a typed
  `family.promotion_dimension` contract, and the active grounded-endpoint
  config promotes on `required_entity_recall` instead of overall target mean.
- 2026-03-22: A real rerun on the grounded-endpoint fixture with
  `gemini/gemini-2.5-flash` (execution `de0dd4170024`) proved the new gate is
  truthful: the `medical_leave` target case still scored `0.95` overall while
  exposing `required_entity_recall=0.5`, so future unattended cycles can no
  longer treat that miss as near-perfect progress.

### Steps

1. Expose explicit completeness metrics in prompt-eval.
   - Preserve the existing combined `entity_policy` score for continuity.
   - Add explicit zero-weight diagnostic dimensions for:
     - `required_entity_recall`
     - `forbidden_entity_suppression`

2. Make supervisor promotion metric configurable by family.
   - Add a typed optional `promotion_dimension` config field.
   - When configured, compute promotion from the target-case mean of that
     dimension instead of the overall target score.

3. Use the stronger gate for the grounded-endpoint family.
   - Configure `grounded_named_endpoint_completeness` to promote on
     `required_entity_recall`.
   - Keep sentinel non-regression unchanged.

4. Prove on the smallest real slice.
   - Rerun the grounded-endpoint `prompt_eval` slice.
   - Confirm the target case still scores highly overall but only `0.5` on
     `required_entity_recall` while `throat cancer` is missing.
   - Confirm the supervisor would therefore not promote the candidate.

---

## Required Tests

### New Tests (TDD)

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_extraction_prompt_eval.py` | `test_extraction_output_evaluator_exposes_required_entity_recall_metric` | required-entity recall is surfaced separately from the combined entity-policy score |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_extract_variant_score_snapshot_uses_configured_promotion_dimension` | supervisor can promote on a target-case dimension mean instead of overall score |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_extraction_prompt_eval.py` | frozen-case evaluator semantics must remain stable |
| `tests/unit/test_extraction_iteration_supervisor.py` | unattended gating/revert/commit behavior must remain stable |

---

## Acceptance Criteria

- [ ] `prompt_eval` trial payloads expose `required_entity_recall` and `forbidden_entity_suppression`
- [ ] the existing overall score remains stable unless the configured promotion metric changes
- [ ] the supervisor can promote on a configured target-case dimension
- [ ] the grounded-endpoint family config uses `required_entity_recall` as its promotion dimension
- [ ] a real rerun on the grounded-endpoint fixture confirms the target completeness miss is no longer hidden by the promotion surface
