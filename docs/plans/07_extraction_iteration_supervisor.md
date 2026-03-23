# Plan #7: Extraction Iteration Supervisor

**Status:** Completed
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Reliable long-running autonomous extraction iteration

---

## Gap

**Current:** DIGIMON has the plans, frozen cases, and prompt-eval harness needed
for extraction-quality work, but it still relies on an interactive session to
continue from one verified milestone to the next.

**Target:** Add an external supervisor in the active repo that can run a bounded
family-scoped improvement loop:

1. baseline one failure-family gate
2. invoke a coding agent
3. rerun the same gate
4. revert or commit based on verified improvement

**Why:** The chat agent is not a reliable enforcement mechanism for "keep going
until criteria are satisfied." DIGIMON needs explicit durable loop state and
external stop/continue mechanics.

---

## References Reviewed

- `docs/plans/05_extraction_quality_repair.md`
- `docs/plans/06_two_pass_extraction_proof.md`
- `docs/adr/011-extraction-iteration-supervisor.md`
- `eval/extraction_prompt_eval.py`
- `eval/fixtures/musique_tkg_grounded_entity_prompt_eval_smoke_cases.json`
- investigation artifact `~/projects/investigations/Digimon_for_KG_application/2026-03-22-autoloop-supervisor-salvage-review.md`
- prior supervisor `~/projects/Digimon_for_KG_application__autoloop/eval/run_continuous_iteration.py`

---

## Files Affected

- `docs/plans/07_extraction_iteration_supervisor.md` (create)
- `docs/adr/011-extraction-iteration-supervisor.md` (create)
- `eval/extraction_prompt_eval.py` (modify)
- `eval/run_extraction_iteration_supervisor.py` (create)
- `eval/continuous_extraction_iteration.grounded_named_endpoint.yaml` (create)
- `prompts/continuous_extraction_fix.yaml` (create)
- `tests/unit/test_extraction_prompt_eval.py` (modify)
- `tests/unit/test_extraction_iteration_supervisor.py` (create)

---

## Progress

- 2026-03-22: ADR-011 accepted the architectural direction. DIGIMON will reuse
  the old autoloop supervisor skeleton only for durable loop mechanics, while
  replacing its question-level benchmark objective with the current
  extraction-family gates.
- 2026-03-22: The first thin slice is now proven in the active repo.
  `eval/extraction_prompt_eval.py` supports `failure_family` filtering,
  `eval/run_extraction_iteration_supervisor.py` persists session state and a
  JSONL ledger, and the checked-in config plus prompt template can launch
  through the real CLI entrypoint.
- 2026-03-22: Real unit tests now prove the first commit-or-revert loop against
  a temporary git repository:
  - flat validation score -> worktree revert, clean repo, durable state kept
  - improved validation score -> real git commit, baseline advanced
- 2026-03-22: The supervisor entrypoint now bootstraps repo-root imports when
  launched as `python eval/run_extraction_iteration_supervisor.py`, so the
  checked-in command path works outside module-invocation-only contexts.
- 2026-03-22: The first real one-cycle live proof exposed an operational config
  drift before any fix attempt ran:
  - the checked-in agent task label used the non-canonical `coding` alias
  - the checked-in agent model used `codex`, but the repo `.venv` had plain
    editable `llm_client` without the Codex SDK extra
  The supervisor now normalizes `coding -> code_generation`, fails fast before
  baseline prompt-eval spend when a Codex-backed agent lane lacks
  `openai_codex_sdk`, and the checked-in config now uses the supported
  non-Codex lane `gpt-5.2-pro` for the default fix-agent path.

---

## Steps

1. Extend `eval/extraction_prompt_eval.py` so a supervisor can filter frozen
   cases by `failure_family`.
2. Add a typed extraction-iteration supervisor config.
3. Port the minimal durable loop mechanics into the active repo:
   - session dir
   - state file
   - ledger
   - signal stop handling
   - clean-worktree check
4. Add the first family-scoped validation path.
   - family: `grounded_named_endpoint_completeness`
   - prompt family: `two_pass_entity_inventory`
   - target variant: `grounded_entity_contract`
5. Add coding-agent dispatch through `llm_client`.
6. Add improvement gating:
   - revert on no improvement
   - commit on verified improvement
7. Defer smoke-build and later benchmark gates to the next slice once the
   family-scoped prompt-eval loop is stable.

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_load_config_validates_pinned_production_model` | decision-grade extraction lane stays pinned |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_extract_variant_mean_score_reads_prompt_eval_output_json` | supervisor can parse the target gate |
| `tests/unit/test_extraction_iteration_supervisor.py` | `test_improvement_gate_requires_strictly_higher_target_score` | no-improvement cycles are rejected |

### Existing Tests

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_extraction_prompt_eval.py` | family-filtered prompt-eval cases must remain stable |

---

## Acceptance Criteria

- [x] `eval/extraction_prompt_eval.py` can filter cases by failure family
- [x] the active repo contains an external extraction-iteration supervisor entrypoint
- [x] the supervisor persists loop state and ledger data outside chat context
- [x] the first supervisor slice can baseline and rerun one family-scoped prompt-eval gate
- [x] the supervisor rejects no-improvement cycles and can revert the worktree
- [x] the supervisor can create a verified commit after an improved family-scoped gate
- [x] the first slice keeps decision-grade extraction validation pinned to `gemini/gemini-2.5-flash`

---

## Notes

- The first slice is intentionally narrow: one failure family, one prompt family,
  one target variant.
- Do not add smoke-build orchestration until the family-scoped prompt-eval loop
  is proven.
- Do not reintroduce question-level benchmark reruns as the first gate.
