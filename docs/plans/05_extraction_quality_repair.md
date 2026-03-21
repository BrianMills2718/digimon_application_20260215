# Plan #5: Extraction Quality Repair for Entity-Graph Builds

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Full MuSiQue rebuild, fixed-graph sanity rerun, renewed benchmark interpretation

---

## Gap

**Current:** The new build architecture can now rebuild aliased ER/TKG artifacts truthfully, but the first real-corpus MuSiQue smoke run still produced malformed relation slots and weak/null entity typing on some chunks.

**Target:** Introduce a typed, schema-guided extraction validation path that fails loudly on malformed entity/relationship records and improves slot fidelity enough for a trustworthy TKG smoke rebuild.

**Why:** DIGIMON cannot claim to reproduce GraphRAG-style TKG methods if the build contract is truthful at the artifact level but untruthful at the extracted-record level.

---

## References Reviewed

> **REQUIRED:** Cite specific code/docs reviewed before planning.

- `ISSUES.md` - `ISSUE-003` from the `MuSiQue_TKG_smoke` run
- `docs/plans/04_graph_build_rearchitecture.md` - current graph rebuild milestone and blockers
- `Core/Graph/DelimiterExtraction.py` - current delimiter-based extraction and parsing path
- `Core/Prompt/GraphPrompt.py` - profile-aware extraction prompt builder
- `Core/Common/graph_schema_guidance.py` - current schema guidance support
- `Core/Schema/EntityRelation.py` - current entity/relationship object contract

---

## Files Affected

> **REQUIRED:** Declare upfront what files will be touched.

- `docs/plans/05_extraction_quality_repair.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `docs/adr/005-typed-extraction-validation.md` (create)
- `ISSUES.md` (modify)
- `Core/Graph/DelimiterExtraction.py` (modify)
- `Core/Prompt/GraphPrompt.py` (modify)
- `Core/Common/graph_schema_guidance.py` (modify)
- `Core/Schema/EntityRelation.py` or a new extraction-record schema module (modify/create)
- `eval/extraction_prompt_eval.py` (create)
- `eval/fixtures/musique_tkg_extraction_prompt_eval_cases.json` (create)
- `tests/unit/test_extraction_record_validation.py` (create)
- `tests/unit/test_musique_smoke_extraction_cases.py` (create)
- `tests/unit/test_extraction_prompt_eval.py` (create)

---

## Plan

## Progress

- 2026-03-21: Slice 1 landed. Parser-level extraction validation now rejects null typed entities in `TKG`, rejects obvious predicate phrases in subject/object slots, strips leaked field-tag wrappers before validation, and locks the observed MuSiQue smoke failures into deterministic tests.
- 2026-03-21: Live `MuSiQue_TKG_smoke` rebuild after Slice 1 produced a materially cleaner artifact: `119` nodes / `90` edges, with no empty or single-letter IDs, no `entity name ...` pseudo-nodes, no null/placeholder typed nodes, and none of the original heuristic bad edges.
- 2026-03-21: Slice 2 shifts extraction prompt iteration onto shared infrastructure. Frozen MuSiQue extraction cases now have a dedicated `prompt_eval` harness with deterministic structural scoring so prompt changes can be compared before another smoke rebuild.
- 2026-03-21: A live one-case `prompt_eval` smoke run completed successfully on the frozen extraction harness. Both `current_contract` and `slot_disciplined_contract` scored `1.0` on the first case, which proves the shared experiment path works but does not yet show prompt separation.
- 2026-03-21: The first full 3-case comparison exposed a shared-tooling compatibility issue: `prompt_eval`'s bootstrap comparison path is not compatible with the current SciPy version in this environment. The DIGIMON harness now defaults to `paired_t` for paired multi-case comparisons so prompt iteration can continue without patching the sibling repo first.
- 2026-03-21: The first full 3-case paired run completed after that harness fix. `slot_disciplined_contract` scored `1.00` mean structural quality versus `0.85` for `current_contract`, with the main remaining failure on the Vilanova case caused by malformed relationship tuple endings in the baseline prompt contract.
- 2026-03-21: Slice 3 landed as a typed build contract. `strict_extraction_slot_discipline` is now part of `GraphConfig`, the ER build override surface, the manifest snapshot, the prebuild CLI, and the live extraction prompt renderer.
- 2026-03-21: A live `MuSiQue_TKG_smoke_strict_slots` rebuild completed successfully with the new flag and a truthful manifest (`strict_extraction_slot_discipline=true`). The artifact improved from `119` nodes / `90` edges to `105` nodes / `95` edges on the same 10-chunk slice, but it still includes semantically weak entities such as `his`, `form`, and `medical leave`, plus normalization-damaged names such as `supercopa de espa a` and `el cl sico`. This means prompt-only tightening is not sufficient.

### Steps

1. Capture the real MuSiQue smoke failures as a small golden set.
   - Freeze the specific bad cases already observed in `MuSiQue_TKG_smoke`, including:
     - `('barcelona', 'won by', 'extra time')`
     - `('messi', 'suffered', 'tear')`
     - `('located in', 'tear', 'medial collateral ligament')`
     - null/weak typing for `left knee`, `medial collateral ligament`, `sextuple`, `silver ball`
2. Add a typed intermediate extraction-record contract.
   - Stop treating the delimiter tuple as the only contract.
   - Introduce explicit typed validation for:
     - entity name
     - entity type
     - relationship source
     - relationship target
     - relationship predicate/name
     - optional description/keywords/weight
3. Tighten schema-guided prompting and parsing.
   - Make the prompt state the intended slot semantics unambiguously for `TKG`/`RKG`.
   - Use the profile/schema guidance to constrain allowed entity/relation types when they are declared.
   - Do not add new few-shot examples without explicit user approval.
4. Fail loudly on malformed extraction output.
   - Reject records with null/placeholder types when the active profile requires typed entities.
   - Reject records whose subject/object slots are structurally invalid for the active contract.
   - Log rejected records with chunk ID and reason.
5. Move prompt iteration onto `prompt_eval`.
   - Freeze a small real-corpus extraction set instead of editing prompts ad hoc.
   - Compare at least `current_contract` vs `slot_disciplined_contract` on those same inputs.
   - Score outputs with deterministic structural validators before any judge-backed or larger-corpus evaluation.
6. Re-run the small MuSiQue TKG smoke build.
   - Rebuild `MuSiQue_TKG_smoke` and check whether the known-bad cases are gone.
   - Only after this smoke slice passes should a larger rebuild or fixed-graph sanity rerun proceed.
7. Add deterministic semantic entity filtering after structural validation.
   - Reject pronouns and other anaphoric placeholders (`his`, `her`, `their`, `he`, `she`) before graph persistence.
   - Reject low-value abstract filler nodes when they are not stable named entities for the active profile, such as `form` or `medical leave` in open `TKG` extraction.
   - Keep this separate from canonical-name redesign; Unicode-preserving identity belongs to Plan #4, not this slice.

---

## Required Tests

### New Tests (TDD)

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_extraction_record_validation.py` | `test_rejects_null_entity_type_for_tkg_profile` | TKG builds fail loudly on null/placeholder entity types |
| `tests/unit/test_extraction_record_validation.py` | `test_rejects_malformed_relationship_slots` | relation source/target/predicate validation rejects obvious slot inversions |
| `tests/unit/test_musique_smoke_extraction_cases.py` | `test_known_bad_musique_cases_are_rejected_or_rewritten` | the captured MuSiQue smoke failures no longer survive parsing as valid graph records |
| `tests/unit/test_extraction_prompt_eval.py` | `test_extraction_output_evaluator_penalizes_invalid_slots_and_missing_types` | prompt_eval scoring rejects the exact structural failure modes Plan #5 is targeting |
| `tests/unit/test_extraction_prompt_eval.py` | `test_extraction_output_evaluator_rewards_structurally_valid_tkg_output` | prompt_eval scoring gives full credit to clean TKG-style extraction output |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_graph_node_validation.py` | invalid entity IDs must remain rejected |
| `tests/unit/test_graph_capabilities.py` | graph/profile capability truth must remain stable |
| `tests/unit/test_graph_build_manifest.py` | manifest truth must remain intact while extraction changes |
| `tests/unit/test_prebuild_graph_cli.py` | alias rebuild CLI contract must remain stable |

---

## Acceptance Criteria

- [ ] a typed extraction-record validation layer exists for entity-graph builds
- [ ] TKG smoke parsing no longer accepts null/placeholder entity types as valid typed entities
- [ ] the known-bad MuSiQue relation examples are rejected or corrected before graph persistence
- [ ] rejected extraction records are logged with chunk provenance and reason
- [ ] `MuSiQue_TKG_smoke` can be rebuilt after the change without reintroducing empty/single-character junk nodes
- [ ] a frozen `prompt_eval` harness exists for extraction prompt variants on the MuSiQue smoke cases
- [ ] the strict-slot build contract is wired through graph config, build overrides, manifest truth, and the prebuild CLI
- [ ] the strict-slot smoke rebuild proves lower malformed-slot leakage than the earlier `MuSiQue_TKG_smoke` artifact
- [ ] semantic junk entities such as pronouns and low-value abstractions are rejected before graph persistence
- [ ] docs and ADRs are updated to reflect the extraction contract

---

## Notes

- This slice is intentionally about extraction quality, not retrieval tuning.
- Do not combine this with a storage migration, VDB redesign, or benchmark agent prompt work.
- The smallest proof is the 10-chunk MuSiQue smoke build, not a full rebuild.
- `prompt_eval` is the required iteration surface for extraction prompt changes in this plan; ad hoc prompt edits without the frozen-case harness do not count as progress.
- Residual Unicode/name damage like `supercopa de espa a` and `el cl sico` is a real issue, but it belongs to the canonical identity redesign in Plan #4 rather than being patched opportunistically here.
