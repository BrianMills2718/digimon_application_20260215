# Plan #23: Semantic Build Boundary And onto-canon6 Experiment

**Status:** Planned
**Type:** design
**Priority:** High
**Blocked By:** None
**Blocks:** Any decision to promote onto-canon6-backed semantic build outputs onto DIGIMON's default benchmark path

---

## Gap

**Current:** DIGIMON and onto-canon6 now overlap enough in "graph build"
responsibility to create architectural ambiguity:

- DIGIMON still owns benchmark-facing graph construction, projection, and some
  local identity behavior,
- onto-canon6 owns governed semantic state, canonical entities, aliases, and
  promoted assertions,
- the current bridge between them is thin and lossy:
  - DIGIMON import merges entities by flat `entity_name`,
  - relationships are merged by sorted endpoint pair,
  - missing endpoints are skipped,
  - the export/import contract does not carry full alias, role, passage, or
    artifact-lineage structure.

**Target:** Define the intended long-term boundary and specify one bounded
experiment for testing richer semantic-build interchange without disturbing the
maintained DIGIMON benchmark lane.

**Why:** DIGIMON needs a benchmark-first near-term path, but it also needs a
clear long-term ownership model so temporary DIGIMON-native build repairs do
not silently become the permanent semantic-build architecture.

---

## References Reviewed

- `CLAUDE.md` - DIGIMON core architecture and cross-project bridge note
- `docs/GRAPH_ATTRIBUTE_MODEL.md` - DIGIMON projection/build model
- `docs/REPO_SURFACE.md` - core vs experimental lane rule
- `Core/Interop/onto_canon_import.py` - current DIGIMON import seam
- `scripts/import_onto_canon_jsonl.py` - current CLI import wrapper
- `/home/brian/projects/onto-canon6/src/onto_canon6/adapters/digimon_export.py` - current flat DIGIMON JSONL export
- `/home/brian/projects/onto-canon6/src/onto_canon6/adapters/foundation_assertion_export.py` - richer assertion-oriented export surface
- `/home/brian/projects/project-meta/vision/ONTO_CANON6_DIGIMON_CONVERGENCE.md` - current documented convergence state
- `docs/plans/17_retest_thesis.md` - benchmark-first default lane
- `docs/plans/21_autonomous_failure_iteration_sprint.md` - latest evidence that representation/canonicalization is now the frontier

---

## Pre-made Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default DIGIMON lane | Stay DIGIMON-native for active benchmark work | Protect the core thesis lane |
| onto-canon6 role | Semantic build / canonicalization producer | Matches the stronger governed-state ownership model |
| DIGIMON role | Retrieval projection / materialization / runtime consumer | Matches the current benchmark thesis |
| Analysis role | Keep conceptually separate; do not spin out a new repo now | Avoid extra architectural churn |
| Interchange v1 | Current flat `entities.jsonl` / `relationships.jsonl` stays as proof-of-life only | It is already useful but too lossy to be the long-term seam |
| Interchange v2 candidate | Foundation-style assertion/artifact envelope plus DIGIMON-side projection compiler | Best current candidate for richer semantic interchange |
| Promotion gate | No default-path switch without benchmark evidence | Keeps architecture work subordinate to benchmark proof |

---

## Files Affected

- `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `docs/GRAPH_ATTRIBUTE_MODEL.md` (modify only if this design reveals a required clarification)

Future implementation under a separate promoted slice may affect:

- `Core/Interop/onto_canon_import.py`
- `scripts/import_onto_canon_jsonl.py`
- a future richer DIGIMON-side projection importer

---

## Plan

### Phase 0: Inventory The Current Seam

1. Write down what DIGIMON currently owns that looks like semantic build.
2. Write down what onto-canon6 already owns that DIGIMON should not duplicate long-term.
3. Describe the exact losses in the current flat JSONL seam.

**Acceptance:**
- There is one explicit ownership inventory, not just conversational intuition.

### Phase 1: Define The Long-Term Boundary

4. State the intended ownership split:
   - onto-canon6: governed assertions, canonical identities, aliases, provenance
   - DIGIMON: retrieval-oriented projections, graph materialization, benchmark runtime
   - analysis: separate concern conceptually, but not a separate repo yet
5. State explicit non-goals:
   - do not move retrieval projections into onto-canon6 core,
   - do not replace DIGIMON's core lane before proof,
   - do not let benchmark-first local fixes silently redefine the long-term architecture.

**Acceptance:**
- Boundary ownership is explicit enough to guide future code movement.

### Phase 2: Compare Interchange Options

6. Compare the current flat DIGIMON JSONL seam against a richer semantic interchange option.
7. Evaluate at minimum:
   - field preservation
   - alias/canonical cluster preservation
   - directional relationship preservation
   - role structure preservation
   - provenance / passage / artifact lineage
   - DIGIMON projection complexity
   - iteration cost
8. Recommend one v2 direction.

**Acceptance:**
- There is one written recommendation, not a vague list of possibilities.

### Phase 3: Specify One Bounded Experiment

9. Define one experiment that stays outside DIGIMON's default core lane:
   - producer surface
   - input corpus / governed promoted graph
   - DIGIMON import/projection step
   - benchmark or retrieval-family evaluation target
   - success / failure criteria
10. Require that the experiment be judged on a canonicalization-heavy failure family, not on anecdotal qualitative output.

**Acceptance:**
- The experiment is small enough to run and strong enough to invalidate the wrong boundary choice.

### Phase 4: Define Promotion Criteria

11. Specify what would justify moving from experimental interchange to default DIGIMON support.
12. Specify what evidence would keep the work experimental.

**Acceptance:**
- The repo has a written promotion gate before any default-lane convergence work begins.

---

## Required Checks

| Check | What It Verifies |
|-------|------------------|
| `git diff --check` | no markdown/doc whitespace regressions |
| `python scripts/meta/check_doc_coupling.py --validate-config --config scripts/doc_coupling.yaml` | plan/doc links remain valid if the repo uses the coupling checker |

---

## Acceptance Criteria

- [ ] The current DIGIMON vs onto-canon6 ownership overlap is documented explicitly.
- [ ] The plan names one recommended long-term ownership split and explicit non-goals.
- [ ] The current flat JSONL seam is compared against at least one richer interchange option.
- [ ] One bounded experiment is specified with exact success/failure criteria.
- [ ] The plan states clearly that DIGIMON's benchmark-default lane remains DIGIMON-native until the experiment proves value.

---

## Open Questions / Uncertainty Tracking

### Q1: Is the current DIGIMON JSONL seam salvageable as a long-term interchange?
**Status:** Open
**Why it matters:** If yes, DIGIMON can evolve the current importer. If no, a richer contract should become the true v2 seam.

### Q2: Is Foundation Assertion IR rich enough by itself, or does DIGIMON need an artifact/provenance envelope above it?
**Status:** Open
**Why it matters:** DIGIMON cares about passage/projection materialization, not just assertion bodies.

### Q3: How much semantic-build logic must remain temporarily local to DIGIMON to keep benchmark iteration cheap?
**Status:** Open
**Why it matters:** Benchmark-first work may justify temporary duplication.

### Q4: Can a richer interchange improve the canonicalization-heavy benchmark family without slowing iteration unacceptably?
**Status:** Open
**Why it matters:** Convergence only matters if it helps the maintained benchmark lane enough to justify the extra complexity.

---

## Notes

- This is a boundary-and-experiment plan, not a mandate to converge immediately.
- The benchmark-first DIGIMON-native work in Plan #22 remains the default near-term path.
- If the bounded experiment under this plan proves value, a later implementation plan can move specific responsibilities upstream or add a richer DIGIMON importer.
