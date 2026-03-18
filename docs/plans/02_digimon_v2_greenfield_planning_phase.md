# Plan #02: DIGIMON V2 Greenfield Planning Phase

**Status:** Complete
**Type:** design
**Priority:** High
**Blocked By:** None
**Blocks:** Future DIGIMON v2 implementation phases

---

## Gap

**Current:** DIGIMON mixes a graph-native research agenda, legacy orchestration paths, partial ontology work, and ecosystem-integration ideas in one codebase without a clean greenfield boundary.

**Target:** A verified planning package for DIGIMON v2 that defines product goals, domain model, system boundaries, phased delivery, and executable acceptance evidence for the planning phase itself.

**Why:** The next build needs to preserve DIGIMON's graph-native identity while fitting into the wider ecosystem through explicit contracts rather than accidental coupling.

---

## References Reviewed

- `README.md` - current DIGIMON framing and JayLZhou lineage
- `CLAUDE.md` - current repo conventions and operator-pipeline intent
- `docs/adr/002-universal-graph-schema-and-extraction.md` - graph schema, ontology modes, reification direction
- `~/projects/project-meta/vision/START_HERE.md` - ecosystem placement of DIGIMON
- `~/projects/project-meta/vision/FRAMEWORK.md` - multimodal north-star and assertion IR
- `~/projects/project-meta/vision/FOUNDATION.md` - artifact/provenance contract
- `~/projects/whygame4/WRITEUP_FOR_CHATGPT_v2.md` - graph pressure and DIGIMON grounding role
- `~/projects/theory-forge/README.md` - schema-to-executable analysis pattern
- `~/projects/dodaf/README.md` - profile-driven validation and assertion contract posture
- `~/projects/orgchart/ONTOLOGY_V2.md` - domain/range-governed application ontology

---

## Files Affected

- `config/config.yaml` (create)
- `docs/plans/02_digimon_v2_greenfield_planning_phase.md` (create)
- `docs/planning/digimon_v2/ARCHITECTURE.md` (create)
- `acceptance_gates/digimon_v2_planning_phase.yaml` (create)
- `scripts/validate_digimon_v2_planning_phase.py` (create)
- `tests/unit/test_validate_digimon_v2_planning_phase.py` (create)
- `docs/plans/CLAUDE.md` (modify)
- `docs/reports/digimon_v2_planning_phase_evidence.json` (generated)

---

## Plan

### Steps

1. Freeze the rebuild goals and non-goals from the top down.
2. Define a greenfield domain model that keeps DIGIMON graph-first internally.
3. Specify the full multi-phase delivery path with explicit success criteria at each phase.
4. Add a machine-readable planning-phase acceptance gate and validator.
5. Generate execution evidence for this planning phase and store it in-repo.

---

## Required Tests

### New Tests (TDD)

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_validate_digimon_v2_planning_phase.py` | `test_validator_passes_for_repo_artifacts` | The planning package validates end-to-end and writes an evidence report |
| `tests/unit/test_validate_digimon_v2_planning_phase.py` | `test_validator_fails_for_missing_required_file` | Validation fails loudly when required planning artifacts are missing |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_validate_digimon_v2_planning_phase.py` | This phase is documentation plus validation harness only; repo-wide test health is intentionally out of scope for the planning package |

---

## Acceptance Criteria

- [x] The repo contains a greenfield DIGIMON v2 architecture blueprint with product goals, non-goals, domain model, phases, and exit criteria.
- [x] The planning package has a machine-readable acceptance gate and config-driven validator.
- [x] Validation writes execution evidence to `docs/reports/digimon_v2_planning_phase_evidence.json`.
- [x] Required tests pass by execution, not inspection.
- [x] The plan states future implementation phases without claiming they are already complete.

---

## Open Questions

1. **Where v2 should live**
   Choice: keep the greenfield plan inside the current repo for now.
   Alternatives: sibling repo, full in-place rewrite.
   Tradeoff: lower startup cost now, but eventual extraction to a dedicated repo may still be the cleaner long-term move.
   Confidence: 0.74

2. **Interop depth in the first executable version**
   Choice: keep DIGIMON v2 graph-first internally and treat ecosystem interoperability as projection/adapter work in a later phase.
   Alternatives: assertion-first core, dual-write from day one.
   Tradeoff: preserves JayLZhou-style GraphRAG focus, but delays deeper ecosystem convergence.
   Confidence: 0.82

3. **Method scope for the first benchmarkable milestone**
   Choice: phase the reference methods so operator/runtime correctness lands before full benchmark breadth.
   Alternatives: implement all named methods immediately.
   Tradeoff: less feature surface early, better observability and faster debugging.
   Confidence: 0.79

---

## Verification Evidence

- Validator command: `python scripts/validate_digimon_v2_planning_phase.py`
- Test command: `pytest --noconftest tests/unit/test_validate_digimon_v2_planning_phase.py -v --junitxml=docs/reports/digimon_v2_planning_phase_pytest.xml`
- Evidence artifact: `docs/reports/digimon_v2_planning_phase_evidence.json`
- Test evidence artifact: `docs/reports/digimon_v2_planning_phase_pytest.xml`
