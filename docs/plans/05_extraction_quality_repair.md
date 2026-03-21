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
- `docs/adr/006-open-tkg-grounded-entity-policy.md` - accepted decision for how abstraction policy must be proven before deterministic filtering
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
- `docs/adr/006-open-tkg-grounded-entity-policy.md` (create)
- `ISSUES.md` (modify)
- `Core/Graph/DelimiterExtraction.py` (modify)
- `Core/Prompt/GraphPrompt.py` (modify)
- `Core/Common/graph_schema_guidance.py` (modify)
- `Core/Schema/EntityRelation.py` or a new extraction-record schema module (modify/create)
- `eval/extraction_prompt_eval.py` (create)
- `eval/fixtures/musique_tkg_extraction_prompt_eval_cases.json` (create)
- `eval/fixtures/musique_tkg_grounded_entity_prompt_eval_smoke_cases.json` (create)
- `tests/unit/test_extraction_record_validation.py` (create)
- `tests/unit/test_musique_smoke_extraction_cases.py` (create)
- `tests/unit/test_extraction_prompt_eval.py` (create)
- `tests/unit/test_graph_build_manifest.py` (modify)
- `tests/unit/test_graph_config_profiles.py` (modify)
- `tests/unit/test_prebuild_graph_cli.py` (modify)

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
- 2026-03-21: Slice 4 added deterministic anaphora filtering in the extraction validator. A follow-up live rebuild to `MuSiQue_TKG_smoke_strict_slots_no_anaphora` dropped the 10-chunk smoke artifact further to `99` nodes / `78` edges and removed `his` from the persisted graph. Residual low-value abstractions such as `form` still survive, which means the next unresolved question is abstraction policy rather than pronoun handling.
- 2026-03-21: ADR-006 was accepted to resolve that ambiguity. DIGIMON will prove the grounded-entity policy with frozen `prompt_eval` cases that include both "drop this abstraction" and "keep this named borderline entity" examples before encoding a deterministic abstraction validator.
- 2026-03-21: The first live grounded-entity `prompt_eval` smoke run over the mixed case set failed before scoring the actual policy question. `grounded_entity_contract` on the long `musique_doc_1_barcelona_2006_07` case produced a truncated `201360`-character response, which then caused the paired comparison to fail because the variants no longer had matching scored input IDs. The next live proof must therefore start with a short policy-focused smoke fixture before reintegrating the long structural cases.
- 2026-03-21: The first live run on that short policy-focused smoke fixture completed cleanly (`gemini/gemini-2.5-flash-lite`, execution `dcdbe4ebda95`) and produced a small nominal improvement for `grounded_entity_contract` (`0.448` mean score vs `0.425`). But the run also exposed a deeper parser bug: every trial had `entity_validity=0.0` because legitimate typed values like `<person>` were stripped to the empty string by the current field-tag cleaner. This means the short smoke proof is now blocked on parser repair, not on policy ambiguity.
- 2026-03-21: Slice 5 repaired that parser bug. `strip_extraction_field_markup()` now removes only known placeholder wrappers like `<entity_type>...</entity_type>` and preserves legitimate angled values like `<person>`, with deterministic unit coverage for both cases.
- 2026-03-21: The short grounded-entity smoke fixture was rerun after the parser fix (`gemini/gemini-2.5-flash-lite`, execution `0bd80b942644`). Both variants recovered `entity_validity=1.0` across all four cases, and the grounded variant finished slightly higher (`0.989` vs `0.981`) but without a statistically meaningful advantage. The only clear policy win was the `medical_leave` case, where the grounded variant suppressed the generic `medical leave` entity while keeping `throat cancer`; both variants still missed `Silver Ball` as a standalone entity node.
- 2026-03-21: ADR-007 accepted entity/relationship closure as a build contract. The short grounded-entity smoke fixture was rerun with closure-aware scoring (`gemini/gemini-2.5-flash-lite`, execution `04b5479be557`): `slot_disciplined_contract` scored `0.907`, `grounded_entity_contract` scored `0.921`, and both variants were now penalized when a relationship endpoint appeared without a corresponding entity record.
- 2026-03-21: A first live closure-aware 10-chunk rebuild completed as `MuSiQue_TKG_smoke_closure` with `strict_extraction_slot_discipline=true`. The artifact finished at `123` nodes / `68` edges. It no longer contains `form`, `fitness`, or `medical leave`, and it still contains `silver ball` and `throat cancer`. This proves the fail-closed closure path is live, but Unicode-damaged IDs like `supercopa de espa a` still remain and one chunk fell back from Gemini to DeepSeek during extraction, so this slice is useful evidence rather than final graph-quality proof.
- 2026-03-21: The same 10-chunk slice was rebuilt with `prefer_grounded_named_entities=true` as `MuSiQue_TKG_smoke_closure_grounded`. The artifact dropped to `100` nodes / `70` edges, but the grounded variant over-pruned useful named nodes that the prompt-eval smoke cases were supposed to protect: `silver ball` disappeared and `throat cancer` disappeared. This means the grounded flag has not earned promotion into the live path.
- 2026-03-21: Both live closure-aware smoke builds used mixed-model extraction because Gemini fell back to DeepSeek after provider policy blocks. That is a real experimental confound. The next live artifact comparison must run on a pure-lane/no-fallback build path before DIGIMON treats the result as decision-grade evidence.
- 2026-03-21: Slice 6 added a dedicated pure-lane evaluation build path plus manifest runtime truth. `eval/prebuild_graph.py` can now run extraction with `--lane-policy pure`, and `graph_build_manifest.json` records the primary model, fallback models, and lane policy used for the build.
- 2026-03-21: The 10-chunk closure-aware MuSiQue slice was rerun on that controlled path as `MuSiQue_TKG_smoke_closure_pure` (`93` nodes / `63` edges) and `MuSiQue_TKG_smoke_closure_grounded_pure` (`104` nodes / `79` edges). This corrected the earlier mixed-lane conclusion: the grounded pure-lane build preserved `silver ball`, but both pure-lane variants still missed `throat cancer`, and the grounded build introduced more conceptual nodes such as `european club`, `treble`, and `sextuple`.

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
8. Decide and implement the low-value abstraction policy.
   - Define what counts as a named/groundable entity versus an abstract common-noun concept for open `TKG` extraction.
   - Do not solve this with an ad hoc benchmark-only stoplist.
   - Once the rule is defined, encode it in deterministic validation and rerun the 10-chunk smoke slice again.
9. Expand the frozen prompt-eval cases for grounded-entity policy.
   - Add focused real-corpus snippets for abstractions that should be dropped, such as `form`, `fitness`, and `medical leave`.
   - Add focused real-corpus snippets for named borderline entities that should still be kept, such as `Silver Ball` and `Copa del Rey`.
   - Score both required and forbidden entity names so prompt changes are judged on pruning quality, not only tuple shape.
10. Compare the current best prompt contract against a grounded-entity variant.
   - Baseline the comparison on the current best contract, not the original pre-slice prompt.
   - Start with a short policy-focused smoke fixture so the first live run measures grounded-entity behavior rather than long-case output explosion.
   - Reintegrate the long structural cases only after the shorter live slice completes without truncation or missing-score failures.
   - Only if the grounded variant suppresses abstractions without over-pruning legitimate entities should it move into the live build path.
11. Repair the extraction field-tag stripper so typed values survive scoring.
   - `strip_extraction_field_markup()` must remove leaked placeholder wrappers like `<entity_type>...</entity_type>` without erasing legitimate angled values like `<person>`.
   - Add deterministic unit coverage for both the leaked-wrapper and legitimate-value cases.
   - Rerun the short grounded-entity smoke fixture after the parser fix before trusting any prompt-policy comparison.
12. Decide whether grounded-entity preference has earned promotion into the live build path.
   - The first clean smoke rerun is a tie-to-slight-win for the grounded variant, not a decisive gain.
   - Do not promote the grounded flag by default unless it improves the next real artifact slice, not just the tiny policy fixture.
   - The next extraction-quality question is entity completeness: named values like `Silver Ball` can still appear only as relationship endpoints instead of entity records.
13. Compare closure-aware live smoke artifacts before promoting grounded extraction.
   - Rebuild the same 10-chunk MuSiQue slice with and without `prefer_grounded_named_entities`.
   - Inspect whether the grounded variant preserves useful named nodes such as `Silver Ball` and `throat cancer` while continuing to suppress low-value abstractions.
   - Treat any mixed-model build caused by provider fallback as non-final evidence that must be called out explicitly in the plan and issues.
14. Add a pure-lane extraction build mode before the next live comparison.
   - Graph-build smoke comparisons should be able to fail loudly instead of silently mixing providers/models.
   - Wire a no-fallback extraction option into the ER build path so prompt/build comparisons can be rerun with one controlled model lane.
   - Only after that rerun should DIGIMON decide whether the grounded prompt policy is helping or over-pruning on real corpus slices.
15. Use the pure-lane evidence to tighten the next grounded-entity prompt_eval slice.
   - Freeze new policy cases that test the remaining real-slice tradeoff: preserve medical diagnoses such as `throat cancer` while avoiding conceptual-node inflation such as `european club`, `treble`, and `sextuple`.
   - Judge prompt variants on those cases with `prompt_eval` before another live rebuild.
   - Do not promote the grounded policy into the default live path unless the frozen cases improve and the next pure-lane smoke rerun reflects the same direction.

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
- [ ] a pure-lane/no-fallback extraction mode exists for decision-grade live build comparisons and is recorded in manifest truth
- [ ] docs and ADRs are updated to reflect the extraction contract

---

## Notes

- This slice is intentionally about extraction quality, not retrieval tuning.
- Do not combine this with a storage migration, VDB redesign, or benchmark agent prompt work.
- The smallest proof is the 10-chunk MuSiQue smoke build, not a full rebuild.
- `prompt_eval` is the required iteration surface for extraction prompt changes in this plan; ad hoc prompt edits without the frozen-case harness do not count as progress.
- Residual Unicode/name damage like `supercopa de espa a` and `el cl sico` is a real issue, but it belongs to the canonical identity redesign in Plan #4 rather than being patched opportunistically here.
