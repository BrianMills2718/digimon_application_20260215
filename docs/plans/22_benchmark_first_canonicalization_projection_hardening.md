# Plan #22: Benchmark-First Canonicalization And Projection Hardening

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None — grounded by the current results of Plan #17 and Plan #21
**Blocks:** Next decision-grade MuSiQue rerun, renewed failure-tranche iteration on the namesake/canonicalization family

---

## Gap

**Current:** DIGIMON's benchmark lane has already cleared the earlier
tool-surface and control-loop bottlenecks enough to expose a narrower live
failure family. The remaining high-yield misses now cluster around lossy
identity handling and weak connective representation:

- unicode display names collapse into lossy lookup strings,
- alias-like variants split into separate useful-but-incompatible nodes,
- city/name glosses are not consistently materialized as retrievable links,
- and indirect place evidence can be retrieved without a durable projected path
  from resolved subject to answerable relation completion.

The architecture docs already describe the intended remedy. The current repo
still does not fully implement:

- canonical display names separate from normalized lookup keys,
- truthful identity strategy in the build manifest,
- stable alias/search metadata that retrieval can consume,
- or the minimal extra projection needed for namesake/gloss questions.

**Target:** Land one bounded DIGIMON-native build/projection slice that attacks
the current benchmark failure family directly:

1. preserve human-readable canonical names without collapsing them into lossy
   IDs,
2. persist normalized search keys and alias truth separately,
3. materialize the smallest general representation needed for name-gloss /
   namesake / subject-to-place retrieval,
4. rerun a frozen canonicalization-heavy benchmark tranche immediately.

**Why:** The repo's fastest path to breaking the benchmark further is no longer
another prompt or atom-gating tweak. It is a general representation repair for
the currently concentrated failure family. This must remain DIGIMON-native and
benchmark-first until proven otherwise.

---

## References Reviewed

- `CLAUDE.md` - current thesis, representation policy, generalization mandate
- `KNOWLEDGE.md` - latest namesake/canonicalization failure evidence
- `CURRENT_STATUS.md` - current benchmark deltas and remaining failure counts
- `docs/GRAPH_ATTRIBUTE_MODEL.md` - intended canonical-name/search-key split and projection model
- `docs/REPO_SURFACE.md` - default core-lane rule
- `docs/plans/17_retest_thesis.md` - current benchmark thesis plan
- `docs/plans/21_autonomous_failure_iteration_sprint.md` - latest control-loop iteration record
- `Config/GraphConfig.py` - current build contract surface
- `Core/Schema/GraphBuildManifest.py` - persisted build truth
- `Core/Graph/BaseGraph.py` - current co-occurrence and passage-node materialization
- `Core/Interop/onto_canon_import.py` - current identity-lossy import behavior that mirrors the same weakness
- `eval/graph_manifest.py` - benchmark-time manifest consumption
- `tests/unit/test_eval_graph_manifest.py` - current manifest regression coverage

---

## Pre-made Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Maintained lane | DIGIMON-native benchmark lane | Do not block benchmark progress on cross-project convergence |
| Benchmark backend | `--backend direct` | Keep the maintained core path |
| First eval slice | Frozen canonicalization-heavy MuSiQue tranche | Highest signal-to-cost ratio for the current frontier |
| Initial identity contract | Preserve canonical display names and add normalized search keys, not a full node-ID redesign | Smallest useful slice that matches `GRAPH_ATTRIBUTE_MODEL.md` |
| Gloss repair policy | Add only general name-gloss / namesake representation that survives outside one question | Enforces the generalization mandate |
| Passage/projection repair | Only add if the frozen tranche shows identity fixes alone are insufficient | Avoid unnecessary graph churn |
| onto-canon6 usage | Experimental only, not part of this plan's default implementation path | Keep core thesis lane isolated |

---

## Files Affected

- `docs/plans/22_benchmark_first_canonicalization_projection_hardening.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `eval/fixtures/musique_canonicalization_tranche.txt` (create)
- `eval/fixtures/musique_canonicalization_tranche.json` (create)
- `eval/fixtures/README.md` (modify)
- `Config/GraphConfig.py` (modify)
- `Core/Schema/GraphBuildManifest.py` (modify)
- `Core/Graph/BaseGraph.py` (modify)
- `Core/Graph/ERGraph.py` (modify if entity-identity persistence requires it)
- `Core/Interop/onto_canon_import.py` (modify if importer parity is included in the slice)
- `digimon_mcp_stdio_server.py` (modify only if graph identity metadata must be surfaced through `entity_info` / `entity_search`)
- `eval/prebuild_graph.py` (modify if rebuild orchestration needs new identity flags)
- `tests/unit/test_eval_graph_manifest.py` (modify)
- `tests/unit/test_onto_canon_import.py` (create or modify)
- `tests/unit/test_entity_profile_identity_fields.py` (create)

---

## Plan

## Progress

- 2026-03-31: Phase 0 is frozen in checked-in fixtures:
  - `eval/fixtures/musique_canonicalization_tranche.txt`
  - `eval/fixtures/musique_canonicalization_tranche.json`
- The tranche includes four primary failure targets:
  - `2hop__199513_801817` — namesake/gloss + subject alias
  - `3hop1__136129_87694_124169` — saint-name canonicalization
  - `2hop__159215_779396` — descriptive person anchor resolution
  - `2hop__77233_33207` — title/epithet anchor resolution
- Two green sentinels are frozen beside it:
  - `2hop__511454_120259`
  - `2hop__766973_770570`
- One overflow case is explicitly deferred rather than silently mixed into the
  tranche:
  - `3hop1__305282_282081_73772` — conceptually related, but the current 50q
    artifact is contaminated by a runtime error rather than a clean
    canonicalization miss.
- 2026-03-31: Phase 1 additive identity-contract slice landed:
  - `GraphConfig` now exposes explicit identity toggles:
    - `entity_node_id_strategy`
    - `preserve_canonical_display_names`
    - `enable_entity_lookup_search_keys`
    - `enable_entity_alias_metadata`
  - `GraphBuildManifest` now persists an `identity_contract` and advertises the
    canonical-name / search-key / alias node fields when enabled.
  - Graph builders now attach canonical display and lookup metadata beside the
    legacy normalized node IDs instead of overloading `entity_name`.
  - `entity_string_search` and `entity_profile` now consume canonical-name and
    `search_keys` metadata, so lossy stored node IDs can still resolve from
    human-facing Unicode queries.
  - The onto-canon importer now preserves the same identity metadata contract
    for imported graphs.
  - Verified with:
    - `.venv/bin/pytest -q tests/unit/test_graph_build_manifest.py tests/unit/test_graph_config_profiles.py tests/unit/test_onto_canon_import.py tests/unit/test_entity_string_search.py`
    - `ruff check Config/GraphConfig.py Core/Common/entity_name_hygiene.py Core/Schema/GraphBuildManifest.py Core/Graph/BaseGraph.py Core/Graph/ERGraph.py Core/Graph/DelimiterExtraction.py Core/Interop/onto_canon_import.py tests/unit/test_graph_build_manifest.py tests/unit/test_graph_config_profiles.py tests/unit/test_onto_canon_import.py tests/unit/test_entity_string_search.py`
    - `git diff --check`
- Phase 1 remains intentionally additive:
  - node IDs are still `clean_str`-normalized for compatibility,
  - no graph rebuild or benchmark rerun has happened yet,
  - namesake/gloss projection repair is still Phase 2 work.
- 2026-03-31: Phase 2 uncertainty narrowed:
  - the persisted `results/MuSiQue/er_graph/graph_build_manifest.json` still
    reports `enable_chunk_cooccurrence=false`, `cooccurrence_edges=false`, and
    no passage-node surface in `node_fields`.
  - so the maintained MuSiQue artifact has not yet exercised the existing
    projection features Plan #17 expected.
  - `eval/prebuild_graph.py` now exposes `--enable-chunk-cooccurrence` and
    `--enable-passage-nodes`, making a bounded projection experiment runnable
    without inventing a new build path.
  - verified with:
    - `.venv/bin/pytest -q tests/unit/test_prebuild_graph_cli.py`
    - `ruff check eval/prebuild_graph.py tests/unit/test_prebuild_graph_cli.py`
- 2026-03-31: Phase 2 smoke rebuild passed on a bounded 5-chunk artifact:
  - command:
    - `/home/brian/miniconda3/envs/digimon/bin/python eval/prebuild_graph.py MuSiQue --artifact-dataset-name MuSiQue_plan22_proj_smoke5 --force-rebuild --graph-profile tkg --enable-chunk-cooccurrence --enable-passage-nodes --chunk-limit 5 --skip-entity-vdb --skip-relationship-vdb`
  - resulting artifact:
    - `results/MuSiQue_plan22_proj_smoke5/er_graph/graph_build_manifest.json`
    - `results/MuSiQue_plan22_proj_smoke5/er_graph/nx_data.graphml`
  - verified outcomes:
    - `manifest_version=6`
    - `identity_contract` persisted
    - `canonical_name` / `search_keys` / `aliases` advertised in `node_fields`
    - GraphML contains `passage_chunk_*` nodes
    - GraphML contains `chunk_cooccurrence` edges
  - new uncertainty surfaced by the smoke artifact:
    - `graph_build_manifest.json` still leaves `config_flags.graph_profile=null`
      and `config_flags.enable_passage_nodes=null` even though the GraphML
      proves the projected structures exist.
    - treat that as a manifest-truthfulness follow-on, not a reason to block
      the tranche rerun.

### Phase 0: Freeze The Failure Family

1. Freeze a canonicalization-heavy MuSiQue tranche with exact question IDs.
2. Record for each case which loss pattern dominates:
   - unicode / normalized-name mismatch
   - alias split
   - namesake or gloss relation missing
   - indirect place evidence not reachable through current projection
3. Keep Lady Godiva and any already-green namesake/bridge sentinels as
   regression guards.

**Acceptance:**
- The tranche is exact and checked in.
- Every case is classified before code changes begin.

### Phase 1: Identity Contract Slice

4. Extend the build contract so canonical display names and normalized lookup
   keys are separate concepts rather than one overloaded `entity_name` field.
5. Persist the chosen identity strategy in the graph build manifest.
6. Ensure graph artifacts and importer paths preserve unicode-facing canonical
   names while still supporting normalized lookup/search behavior.
7. Surface alias/search metadata truthfully where benchmark retrieval can use
   it.

**Acceptance:**
- The manifest records the effective identity strategy.
- Graph/profile surfaces can show canonical names without forcing lossy lookup IDs.
- Tests prove canonical display names and normalized lookup keys do not collapse into one field.

### Phase 2: Minimal General Projection Repair

8. Add the smallest general representation that fixes the dominant
   namesake/gloss loss point in the frozen tranche.
9. Prefer operator-usable structure over buried description text:
   - gloss/name-meaning link,
   - alias cluster metadata,
   - or direct entity↔passage / entity↔chunk provenance path.
10. Reject topic-specific patches or case-shaped special handling.

**Acceptance:**
- The added representation is framed as a failure-family repair, not a single-question rule.
- The operator path from question → resolved subject → supporting evidence is inspectable on at least one previously failing case.

### Phase 3: Bounded Rebuild And Rerun

11. Rebuild only the bounded graph artifacts needed for the frozen tranche.
12. Re-run the tranche on the maintained direct benchmark lane.
13. Compare against the pre-change frozen results and classify any remaining misses.

**Acceptance:**
- The rerun is decision-grade for the frozen tranche.
- Improvements and regressions are recorded question-by-question.

### Phase 4: Promote Or Redirect

14. If the tranche moves meaningfully, update Plan #17 / Plan #21 and continue on the next failure family.
15. If the tranche does not move after the planned representation slice, record the failed hypothesis and hand the next question to the boundary experiment in Plan #23.

**Acceptance:**
- The next gate is explicit.
- No benchmark-facing conclusion is left only in chat.

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_graph_build_manifest_identity_fields.py` | `test_manifest_records_identity_strategy_and_search_fields` | build manifest truthfully records canonical-name/search-key identity policy |
| `tests/unit/test_onto_canon_import.py` | `test_import_preserves_unicode_display_name_and_lookup_metadata` | importer parity does not silently ascii-strip canonical names |
| `tests/unit/test_entity_profile_identity_fields.py` | `test_entity_profile_surfaces_canonical_name_aliases_and_lookup_refs` | benchmark-facing entity profile exposes the new identity metadata truthfully |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_eval_graph_manifest.py` | manifest-driven tool gating must remain truthful |
| `tests/unit/test_semantic_plan_query_contract.py` | benchmark planning/query forwarding cannot regress while representation changes land |

### Benchmark Checks

| Check | What It Verifies |
|-------|------------------|
| Frozen canonicalization tranche rerun | the current failure family actually moves |
| Lady Godiva + green sentinel rerun | no regression on already-repaired bridge logic |

---

## Acceptance Criteria

- [x] A frozen canonicalization-heavy MuSiQue tranche is defined with exact question IDs.
- [x] The build manifest truthfully records the identity strategy used by the rebuilt graph.
- [x] DIGIMON graph/build surfaces preserve canonical display names separately from normalized lookup keys.
- [ ] At least one general representation repair for namesake/gloss retrieval lands or is explicitly rejected with trace-backed evidence.
- [ ] The frozen tranche improves by at least 2 additional correct answers with no regressions on the maintained bridge/namesake sentinels.
- [ ] Remaining misses are reclassified honestly after the rerun.

---

## Open Questions / Uncertainty Tracking

### Q1: How much of the current miss family is identity loss vs missing gloss edges?
**Status:** Open
**Why it matters:** The first slice should not overbuild if normalized lookup and alias truth already solve most cases.
**Plan handling:** Phase 0 classifies the frozen tranche before implementation.

### Q2: Can DIGIMON preserve unicode canonical names without breaking existing graph-node assumptions?
**Status:** Open
**Why it matters:** Current node identity still leans on cleaned strings and exact node IDs.
**Plan handling:** Keep the first slice additive where possible; avoid a full node-ID redesign.

### Q3: Does the namesake family require more passage/entity-passage projection, or only better identity metadata?
**Status:** Open
**Why it matters:** Passage/provenance repair is valuable but should only be promoted if the tranche proves it is the next bottleneck.
**Plan handling:** Add projection repair only after the identity slice is evaluated against the frozen tranche.

### Q4: Is DIGIMON-native canonicalization durable ownership or benchmark-lane debt?
**Status:** Open
**Why it matters:** Some identity work may later move upstream to onto-canon6.
**Plan handling:** Treat this plan as benchmark-first. Ownership cleanup is handled separately in Plan #23.

### Q5: Must manifest truthfulness be repaired before wider projection promotion?
**Status:** Open
**Why it matters:** The 5-chunk smoke artifact proves passage nodes and chunk-cooccurrence edges can be built, but the manifest still does not serialize all effective projection flags truthfully.
**Plan handling:** Do not block the tranche rerun on this if the benchmark path only needs the built graph. Promote it immediately if later build gating or artifact consumers depend on those flags.

---

## Notes

- This plan is intentionally benchmark-first and DIGIMON-native.
- It is allowed to be transitional, but it is not allowed to be case-shaped.
- If the frozen tranche improves, that is evidence to keep pushing the benchmark lane before larger architecture churn.
