# Plan #12: MuSiQue Representation Audit

**Status:** In Progress
**Type:** investigation
**Priority:** High
**Blocked By:** None
**Blocks:** Further extraction-policy changes, retrieval-strategy changes, and renewed 10-20 question iteration

---

## Gap

**Current:** ADR-013 defines the first-principles rule for node vs edge vs
attribute vs chunk-only representation, but DIGIMON still lacks a
benchmark-grounded map of which MuSiQue reasoning patterns actually require
which representation and operator path.

**Target:** Freeze a small representative MuSiQue audit slice, classify each
case by answer-critical datum, current representation, minimal sufficient
representation, intended operator path, and first loss point, then use that
evidence to decide whether the next work belongs in build/extraction, retrieval
tools, planner/validator semantics, or answer synthesis.

**Why:** Without a benchmark-grounded representation audit, DIGIMON will keep
oscillating between over-materializing the ontology and making case-shaped
repairs that do not generalize.

---

## References Reviewed

- `CLAUDE.md` - current representation policy and extraction-iteration rules
- `docs/adr/013-answer-critical-fact-representation.md` - accepted
  node/edge/attribute/chunk-only policy
- `docs/plans/03_prove_adaptive_routing.md` - current benchmark thesis and
  evaluation gate
- `docs/plans/05_extraction_quality_repair.md` - active extraction-quality work
- `docs/plans/batch_01_musique_dev.md` - development-batch format and failure
  taxonomy
- `docs/composability_handoff_for_chatgpt.md` - trace-backed contract and
  composability findings
- `results/MuSiQue_gemini-2-5-flash_20260221T051240Z.json` - 10-question
  benchmark slice with full traces
- `results/MuSiQue_gemini-2-5-flash_20260221T051240Z_judged.json` - judged
  outcomes for that slice
- `results/MuSiQue_gemini-2-5-flash_baseline_20260319T032753Z.json` - direct
  baseline failure on `2hop__511454_120259`
- `results/MuSiQue_gemini-2-5-flash_fixed_graph_20260319T032940Z.json` -
  fixed-graph success on the same question

---

## Files Affected

- `docs/plans/12_musique_representation_audit.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `docs/plans/05_extraction_quality_repair.md` (modify)
- `CLAUDE.md` (modify)

---

## Plan

## Progress

- 2026-03-22: `llm_client` imports cleanly again in both the shared editable
  repo and the project venv, so trace/eval-backed audit work is no longer
  blocked by the earlier syntax break.
- 2026-03-22: Slice 1 is frozen to four exact MuSiQue cases:
  - `2hop__511454_120259` (`baseline` fail vs `fixed_graph` success)
  - `2hop__766973_770570` (clean success reference)
  - `4hop1__94201_642284_131926_89261` (4-hop miss with wrong anchor chain)
  - `4hop2__71753_648517_70784_79935` (4-hop miss with composition-semantics drift)
- 2026-03-22: The first audit artifact is recorded in
  `~/projects/investigations/Digimon_for_KG_application/2026-03-22-musique-representation-audit-slice-01.md`.
  The strongest current finding is that the next high-value fixes are not
  “add more granular entities” by default. The first two benchmark-facing gaps
  are:
  - anchor discovery/disambiguation that can complete a chain on weak evidence
  - planner/compose semantics that force impossible geographic intersections

### Steps

1. Freeze the audit contract.
   - Use exact question IDs and source artifacts.
   - Record whether each case is graph-helped, graph-neutral, or graph-hurt.
   - Include at least one true graph-helped delta case, one clean success, and
     one hard miss in the first slice.

2. Diagnose each case with the representation loop.
   - Answer-critical datum
   - Current useful representation
   - Minimal sufficient representation
   - Intended operator path
   - First loss point
   - Recommended implementation lane

3. Prove the method on the smallest real slice.
   - Finish the 4-case slice first.
   - Do not widen to 15-25 cases until the audit categories are stable enough
     to guide action.

4. Aggregate the findings into change priorities.
   - Distinguish build/extraction issues from retrieval/operator issues and
     planner/validator issues.
   - State explicitly whether the next justified work is graph-build,
     tool-surface, planner, or answer-synthesis work.

5. Expand only after the first slice earns it.
   - The larger audit target is 15-25 representative MuSiQue questions.
   - Expand only when the 4-case slice produces a stable taxonomy rather than
     ad hoc observations.

---

## Required Checks

| Check | What It Verifies |
|-------|------------------|
| `git diff --check` | no doc/markdown whitespace regressions |
| `python scripts/meta/check_doc_coupling.py --validate-config --config scripts/doc_coupling.yaml` | plan/doc links stay valid |

---

## Acceptance Criteria

- [ ] the audit names an exact frozen MuSiQue slice with question IDs and
      source artifacts
- [ ] each audited case records the answer-critical datum, minimal sufficient
      representation, intended operator path, and first loss point
- [ ] the first slice includes at least one graph-helped delta case and one
      graph-hurt or graph-miss case
- [ ] the audit ends with a prioritized recommendation for the next
      implementation lane
- [ ] the audit explicitly states what not to do yet, so representation changes
      do not drift into ontology inflation or case-shaped prompt hacks

---

## Notes

- This is a benchmark-grounding plan, not a prompt-tuning plan.
- Do not change extraction prompts or graph-build policy on the basis of one
  isolated case if the audit points to planner or retrieval failures instead.
- The first slice should bias toward cases with full traces and controlled
  comparison artifacts, even if the later expanded slice uses a wider sample.
