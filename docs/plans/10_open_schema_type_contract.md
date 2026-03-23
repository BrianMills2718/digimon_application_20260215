# Plan #10: Truthful Open-Schema Type Contract for TKG Extraction

**Status:** Complete
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Further grounded-endpoint supervisor cycles, trustworthy open-TKG prompt iteration

---

## Gap

**Current:** `schema_mode=open` still injects the hardcoded fallback palette
`organization, person, geo, event` into active extraction prompts when no
explicit type list is declared.

**Target:** Open schema mode becomes truthful: no hidden palette is injected,
the prompt contract changes accordingly, and the smallest real proof runs on
the frozen grounded-endpoint completeness fixture.

**Why:** DIGIMON cannot claim configurable GraphRAG-style build semantics if
`open` mode is actually a silent four-type schema. This also likely blocks the
remaining `throat cancer` / `Silver Ball` completeness failures.

---

## References Reviewed

> **REQUIRED:** Cite specific code/docs reviewed before planning.

- `Core/Common/graph_schema_guidance.py` - current fallback type resolution
- `Core/Common/Constants.py` - current `DEFAULT_ENTITY_TYPES`
- `Core/Prompt/GraphPrompt.py` - active one-pass and two-pass entity contracts
- `Config/GraphConfig.py` - current schema-mode defaults
- `docs/GLOSSARY.md` - canonical `open` / palette terminology
- `docs/plans/05_extraction_quality_repair.md` - current extraction-quality loop and live findings
- `docs/plans/06_two_pass_extraction_proof.md` - current two-pass completeness findings
- `results/continuous_extraction/live-grounded-onecycle-targeted-20260322/ledger.jsonl` - live supervisor proof
- `/home/brian/projects/investigations/Digimon_for_KG_application/2026-03-22-open-tkg-type-palette-followup.md` - evidence synthesis for this slice

---

## Files Affected

> **REQUIRED:** Declare upfront what files will be touched.

- `docs/plans/10_open_schema_type_contract.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `docs/adr/012-open-schema-does-not-inject-default-type-palette.md` (create)
- `docs/adr/CLAUDE.md` (modify)
- `docs/GLOSSARY.md` (modify)
- `docs/plans/05_extraction_quality_repair.md` (modify)
- `docs/plans/06_two_pass_extraction_proof.md` (modify)
- `Core/Common/graph_schema_guidance.py` (modify)
- `Core/Prompt/GraphPrompt.py` (modify)
- `tests/unit/test_graph_schema_guidance.py` (create)
- `tests/unit/test_extraction_prompt_eval.py` (modify)

---

## Plan

## Progress

- 2026-03-22: Open schema mode no longer injects the hidden four-type fallback
  palette when no explicit type list is declared. The active one-pass and
  two-pass prompts now render a truthful open-type instruction instead of
  pretending the model is constrained to `organization`, `person`, `geo`, and
  `event`.
- 2026-03-22: Deterministic coverage now locks the new contract in
  `tests/unit/test_graph_schema_guidance.py` and the prompt-variant surface in
  `tests/unit/test_extraction_prompt_eval.py`.
- 2026-03-22: A real `prompt_eval` rerun on the grounded-endpoint completeness
  fixture completed cleanly on `gemini/gemini-2.5-flash` (execution
  `82bcc6e1f12d`). Both variants improved to `0.975` mean and recovered clean
  `award`, `date`, `city`, `competition`, `location`, and `year` type labels
  without malformed tuples. The remaining gap is now clearer: `throat cancer`
  still did not materialize as a standalone entity record, while the evaluator
  still scored the target case `0.95`. That scoring weakness is the next issue,
  not the open-schema type contract itself.

### Steps

1. Make open-mode type resolution truthful.
   - When `schema_mode=open` has no explicit `schema_entity_types` and no
     custom ontology entity list, return an empty palette instead of
     `DEFAULT_ENTITY_TYPES`.
   - Preserve explicit palettes when the caller actually declares them.

2. Make the prompt contract truthful for empty palettes.
   - One-pass and two-pass entity contracts must stop saying “one of the
     following types” when there is no declared list.
   - Replace that wording with an open semantic-type instruction that still
     requires a stable non-placeholder type value.

3. Add deterministic unit coverage.
   - Lock the open-mode resolution behavior.
   - Lock the explicit-palette behavior.
   - Lock the prompt wording for empty vs declared type lists.

4. Prove on the smallest real slice.
   - Rerun the grounded-endpoint completeness `prompt_eval` slice on
     `gemini/gemini-2.5-flash` for the two-pass entity-inventory family.
   - Record whether the open-type contract improves the target case or at least
     removes the hidden-schema contradiction without regressing the sentinel.

---

## Required Tests

### New Tests (TDD)

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_graph_schema_guidance.py` | `test_open_schema_without_explicit_palette_returns_no_entity_types` | open schema no longer injects the hardcoded four-type fallback |
| `tests/unit/test_graph_schema_guidance.py` | `test_open_schema_preserves_explicit_entity_palette` | explicit palettes remain authoritative in open mode |
| `tests/unit/test_graph_schema_guidance.py` | `test_schema_guided_without_explicit_palette_keeps_default_entity_types` | non-open modes keep current fallback behavior for this slice |
| `tests/unit/test_extraction_prompt_eval.py` | `test_build_prompt_variants_uses_open_type_instruction_without_default_palette` | active prompt variants render truthful open-type wording instead of a hidden type list |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_extraction_prompt_eval.py` | prompt-eval harness and frozen-case contract must remain stable |
| `tests/unit/test_two_pass_extraction.py` | two-pass extraction contract must remain valid |
| `tests/unit/test_graph_config_profiles.py` | graph-profile/schema-mode config semantics must remain stable |

---

## Acceptance Criteria

- [ ] open schema mode no longer injects `DEFAULT_ENTITY_TYPES` when no explicit palette is declared
- [ ] explicit `schema_entity_types` or custom ontology entity names still drive the active type palette
- [ ] active extraction prompts render truthful empty-palette wording in open mode
- [ ] deterministic unit coverage exists for both resolution behavior and prompt wording
- [ ] a real `prompt_eval` rerun completes on the grounded-endpoint completeness fixture and its outcome is recorded in plan progress

---

## Notes

- This slice is intentionally about prompt/type-contract truth, not a broader ontology redesign.
- Do not introduce a new hidden fallback under a different field name.
- If a broader default open palette is still needed later, it must be explicit
  in config and manifest truth, not silently inferred.
