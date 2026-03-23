# Plan #6: Two-Pass Extraction Proof for Entity Completeness

**Status:** Blocked — paused pending Plan #17 strategic pivot results
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Next live entity-graph smoke rebuild under Plan #5

---

## Gap

**Current:** One-pass grounded prompting can suppress broad conceptual nodes on
the current completeness-focused frozen fixture, but it still struggles to materialize named
relationship endpoints such as `throat cancer` and `Silver Ball` as standalone
entity records. A direct prompt-only completeness instruction regressed into
truncated and malformed outputs.

**Target:** Add a config-backed two-pass extraction path for delimiter-based
entity graphs:

1. extract the grounded entity inventory first
2. extract relationships against that explicit inventory
3. prove the contract on the same completeness-focused frozen fixture before any live rebuild

**Why:** DIGIMON now has truthful closure semantics (ADR-007) and truthful
pure-lane build comparisons (ADR-008). The remaining gap is stable entity
completeness. Two-pass extraction is the smallest non-hacky architectural
change that can address that without more one-pass prompt sprawl.

---

## References Reviewed

- `docs/adr/007-entity-relationship-closure.md`
- `docs/adr/008-pure-lane-build-comparisons.md`
- `docs/adr/009-two-pass-extraction-for-completeness.md`
- `docs/plans/05_extraction_quality_repair.md`
- `Core/Graph/DelimiterExtraction.py`
- `Core/Prompt/GraphPrompt.py`
- `Config/GraphConfig.py`
- `Core/Schema/GraphBuildManifest.py`
- `eval/extraction_prompt_eval.py`

---

## Files Affected

- `docs/plans/06_two_pass_extraction_proof.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `docs/plans/05_extraction_quality_repair.md` (modify)
- `Config/GraphConfig.py` (modify)
- `Core/Schema/GraphBuildManifest.py` (modify)
- `Core/AgentSchema/graph_construction_tool_contracts.py` (modify)
- `eval/prebuild_graph.py` (modify)
- `Core/Prompt/GraphPrompt.py` (modify)
- `Core/Graph/DelimiterExtraction.py` (modify)
- `tests/unit/test_graph_build_manifest.py` (modify)
- `tests/unit/test_prebuild_graph_cli.py` (modify)
- `tests/unit/test_graph_node_validation.py` (modify)
- `tests/unit/test_extraction_prompt_eval.py` (modify if needed for strategy wiring)
- `tests/unit/test_two_pass_extraction.py` (create)

---

## Plan

## Progress

- 2026-03-21: The two-pass extraction contract landed end to end. `two_pass_extraction`
  is now part of `GraphConfig`, typed ER build overrides, manifest truth, and the
  `eval/prebuild_graph.py` CLI.
- 2026-03-21: `DelimiterExtractionMixin` now has a real two-pass dispatcher:
  entity-only extraction first, validated inventory materialization second, and
  relationship-only extraction constrained to that inventory.
- 2026-03-21: Deterministic tests now cover the two-pass boundary:
  pass-2 prompt inventory, combined entity+relationship records, fail-closed
  skip behavior when pass 1 yields no valid entities, manifest truth, and CLI
  rebuild semantics.
- 2026-03-21: Live proof on `musique_doc_5_grounded_medical_leave` showed a
  model-lane split:
  - `gemini/gemini-2.5-flash-lite` did not honor the delimiter tuple contract
    on pass 1 and the build failed closed with zero records.
  - `gemini/gemini-2.5-flash` honored the two-pass tuple contract and completed
    cleanly, but it still missed `throat cancer` as an entity record and
    instead promoted date nodes such as `19 July` and `December 2012`.
- 2026-03-21: That means Plan #6 is structurally proven but not yet
  completeness-proven. The next step is not another ad hoc live rebuild. It is
  `prompt_eval`-driven iteration on the two-pass prompts against the same
  frozen completeness cases.
- 2026-03-21: `prompt_eval` itself only supports static single-call prompt
  variants, so it cannot represent the full two-call two-pass flow directly.
  The next truthful integration point is therefore the pass-1
  entity-inventory prompt on the same frozen completeness cases, with
  relationship expectations neutralized for that evaluation slice.
- 2026-03-21: That entity-inventory `prompt_eval` slice is now live too
  (`gemini/gemini-2.5-flash`, execution `7c95be33d37a`) on the short
  grounded fixture. The grounded two-pass inventory prompt remained only
  directionally better overall (`0.821` vs `0.775`, not significant), and the
  target cases are still unresolved:
  - `musique_doc_5_grounded_medical_leave`: neither variant materialized
    `throat cancer`; the grounded variant improved over the strict variant, but
    still promoted date nodes with invalid empty types instead of the diagnosis.
  - `musique_doc_9_grounded_silver_ball`: the strict two-pass inventory prompt
    recovered `Silver Ball` cleanly, while the grounded variant regressed into
    malformed entity tuples.
- 2026-03-21: This narrows the next design question. DIGIMON now has a
  verified two-pass evaluation surface, but the remaining completeness blocker
  looks less like "need more grounding wording" and more like "the default
  open-TKG type palette is too narrow and pushes the model toward event/date
  substitutions instead of diagnoses and awards."
- 2026-03-22: That open-palette diagnosis was real. Plan #10 removed the
  hidden fallback palette from `schema_mode=open`, and a fresh two-pass
  entity-inventory rerun on the same grounded-endpoint fixture
  (`gemini/gemini-2.5-flash`, execution `82bcc6e1f12d`) finished with both
  variants at `0.975` mean and clean `award` typing for `Silver Ball`. The
  remaining completeness miss is now more precise: `throat cancer` is still not
  emitted as a standalone entity record, but the current evaluator still gives
  that target case `0.95`. The next issue is therefore the strength of the
  completeness gate, not the open-type contract.
- 2026-03-22: The grounded-endpoint family has now been widened beyond one
  target plus one sentinel. The fixture adds a second real MuSiQue sports-domain
  injury target (`broken cheekbone`) so the next completeness fix must
  generalize across grounded clinical/injury endpoints rather than overfitting
  to `throat cancer` alone.

### Steps

1. Add a first-class `two_pass_extraction` graph-build flag.
   - Wire it through `GraphConfig`, typed build overrides, and manifest truth.
   - Make explicit override use force a fresh build in `eval/prebuild_graph.py`.

2. Add two-pass prompts.
   - Build one prompt for entity inventory extraction only.
   - Build one prompt for relationship extraction constrained to the pass-1
     inventory.
   - Keep the same delimiter contract so existing validators/scorers still
     apply.

3. Implement two-pass delimiter extraction.
   - Add a helper that runs pass 1, validates/materializes entity records, then
     runs pass 2 against the validated entity inventory.
   - Keep closure fail-loud: relationships may only use pass-1 entities.
   - Do not synthesize missing entities from relationship endpoints.

4. Add deterministic tests.
   - Verify pass-2 prompts include the explicit entity inventory.
   - Verify invalid pass-1 entities do not leak into pass-2 inventory.
   - Verify two-pass flow combines pass-1 entities with pass-2 relationships.
   - Verify config/manifest/CLI truth for the new flag.

5. Prove on the smallest real slice.
   - Run one live two-pass extraction smoke proof on the `medical_leave` case.
   - Compare whether `throat cancer` appears as an entity record without the
     output-explosion regression seen in the one-pass completeness wording.
6. If the first live two-pass proof is structurally clean but still incomplete,
   move two-pass prompt iteration onto the frozen `prompt_eval` fixture before
   another live rebuild.
   - Compare the current two-pass entity-inventory prompts on the same
     completeness-focused cases that already exposed `throat cancer` and
     `Silver Ball`.
   - Do not treat structural success alone as proof that two-pass solved the
     completeness problem.

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_two_pass_extraction.py` | `test_two_pass_extraction_uses_validated_entity_inventory_in_second_prompt` | pass 2 sees only validated entity inventory |
| `tests/unit/test_two_pass_extraction.py` | `test_two_pass_extraction_combines_entity_and_relationship_records` | two-pass flow returns entity + relationship records for downstream parsing |
| `tests/unit/test_two_pass_extraction.py` | `test_two_pass_extraction_skips_second_pass_when_no_valid_entities` | no pass-2 call occurs when pass 1 yields no valid entities |

### Existing Tests

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_graph_build_manifest.py` | manifest truth must persist the new extraction strategy |
| `tests/unit/test_prebuild_graph_cli.py` | explicit two-pass builds must require fresh rebuilds |
| `tests/unit/test_graph_node_validation.py` | validation boundaries must still fail loudly |
| `tests/unit/test_extraction_prompt_eval.py` | grounded prompt fixture must remain stable while two-pass is added |

---

## Acceptance Criteria

- [x] `two_pass_extraction` exists as a typed graph-build contract
- [x] manifest truth records whether a graph used two-pass extraction
- [x] delimiter-based entity graphs can run a two-pass extraction path without
      changing the persisted tuple contract
- [x] pass-2 relationship extraction is explicitly constrained to the pass-1
      entity inventory
- [x] deterministic tests cover the two-pass call contract and inventory
      boundary
- [x] one live medical-leave smoke proof completes with the two-pass path
      without output explosion
- [ ] the live two-pass proof recovers the motivating named endpoint
      completeness failures (`throat cancer`, later `Silver Ball`)

---

## Notes

- This slice is about proving the architecture, not replacing the existing
  prompt-eval runner with a general strategy framework.
- Do not push two-pass extraction into live benchmark rebuilds until the small
  proof succeeds on both structure and named-endpoint completeness.
- Do not weaken ADR-007 closure rules to make two-pass look better.
