# Plan #26: DIGIMON isolated governed refresh and ownership-baseline repair

**Status:** ✅ Complete

**Verified:** 2026-04-03T02:27:04Z
**Verification Evidence:**
```yaml
completed_by: scripts/complete_plan.py
timestamp: 2026-04-03T02:27:04Z
tests:
  unit: 5/5 commands passed
  e2e_smoke: covered by plan-declared commands
  e2e_real: covered by plan-declared commands
  doc_coupling: covered by plan-declared commands
commit: d319f9a
```
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** project-meta Plan #67 closeout for the DIGIMON stale-tooling wave

---

## Gap

**Current:** DIGIMON's canonical branch carries the maintained benchmark lane,
but the governed refresh wave found one remaining stale-tooling and baseline
gap:

- stale local copies of the authoritative shared plan-coordination runtime
  (`scripts/meta/check_coordination_claims.py`, `create_plan.py`,
  `plan_reservations.py`)
- `AGENTS.md` not in sync with `CLAUDE.md`
- missing repo-local `meta_process.capability_ownership` declaration and source
  of record

The canonical DIGIMON checkout is also dirty in benchmark and documentation
surfaces, so this repair must stay in a clean worktree.

**Target:** Repair the governed baseline in the clean DIGIMON worktree only:

- add the minimum capability-ownership source-of-record surface
- declare that surface in `meta-process.yaml`
- refresh stale authoritative shared tooling through the sanctioned installer
- restore `AGENTS.md` sync
- leave the worktree ready for landing-safety comparison against the dirty
  canonical root

**Why:** DIGIMON is the last remaining stale-tooling repo in the current
governed refresh wave. Until this bounded repair exists in a clean worktree,
`project-meta` cannot truthfully classify the repo as ready for safe replay or
precise blocker preservation.

---

## References Reviewed

> **REQUIRED:** Cite specific code/docs reviewed before planning.

- `CLAUDE.md` - DIGIMON runtime, benchmark, and governance policy
- `docs/ACTIVE_DOCS.md` - current documentation authority map
- `docs/plans/CLAUDE.md` - DIGIMON plan index
- `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md` - DIGIMON versus `onto-canon6` boundary lane
- `docs/plans/25_authoritative-coordination-prerequisite-remediation.md` - prior DIGIMON governed prerequisite repair
- `~/projects/project-meta_worktrees/plan-67-digimon-isolated-governed-refresh/docs/plans/67_digimon-isolated-governed-refresh-and-ownership-baseline-repair.md` - parent governance wave
- `~/projects/project-meta_worktrees/plan-67-digimon-isolated-governed-refresh/scripts/meta/install_governed_repo.py` - sanctioned refresh surface
- `~/projects/project-meta_worktrees/plan-67-digimon-isolated-governed-refresh/scripts/meta/audit_governed_repo.py` - authoritative governed audit
- `~/projects/project-meta_worktrees/plan-67-digimon-isolated-governed-refresh/scripts/capability_ownership_registry.yaml` - shared DIGIMON capability registry rows
- `~/projects/Digimon_for_KG_application/Makefile` - sanctioned worktree defaults and start-point behavior

---

## Files Affected

> **REQUIRED:** Declare upfront what files will be touched.

- `docs/plans/CLAUDE.md` (modify)
- `docs/plans/26_digimon-isolated-governed-refresh-and-ownership-baseline-repair.md` (create/update)
- `docs/ACTIVE_DOCS.md` (modify)
- `docs/ops/CAPABILITY_DECOMPOSITION.md` (create)
- `meta-process.yaml` (modify)
- `AGENTS.md` (modify via renderer)
- `.gitignore` (modify if runtime-coordination sync changes)
- `.claude/hooks/gate-edit.sh` (modify if refreshed)
- `.claude/hooks/track-reads.sh` (modify if refreshed)
- `.claude/settings.json` (modify if refreshed)
- `scripts/check_truth_surface_drift.py` (install)
- `scripts/render_truth_surface_status.py` (install)
- `scripts/meta/check_coordination_claims.py` (sync)
- `scripts/meta/create_plan.py` (sync)
- `scripts/meta/plan_reservations.py` (sync)
- `scripts/meta/worktree-coordination/check_claims.py` (sync)
- `scripts/meta/worktree-coordination/safe_worktree_remove.py` (sync)

---

## Plan

### Phase 0 — Local plan contract and baseline freeze

1. Record the exact governed gap and the minimal repair scope in this plan.
2. Add a repo-local capability ownership source of record that matches the
   current shared registry posture without reopening broad architecture work.

### Phase 1 — Minimum governed baseline repair

3. Declare `meta_process.capability_ownership` in `meta-process.yaml`.
4. Run the authoritative shared installer from `project-meta` against this
   worktree.
5. Allow only the installer-managed shared-tooling and AGENTS sync footprint,
   not unrelated benchmark or architecture churn.

### Phase 2 — Verification

6. Re-run the authoritative governed audit from `project-meta`.
7. Re-run the local entrypoints needed for future DIGIMON work:
   - `create_plan.py --dry-run`
   - `check_agents_sync.py --check`
   - local plan validation on this plan
8. Leave the worktree committed and ready for parent-wave landing-safety
   comparison.

---

## Required Tests

### Mechanical Verification

| Command | What It Verifies |
|---------|------------------|
| `python ~/projects/project-meta_worktrees/plan-67-digimon-isolated-governed-refresh/scripts/meta/audit_governed_repo.py --repo-root . --json` | Authoritative governed audit after the repair |
| `python scripts/meta/create_plan.py --dry-run --title "coordination smoke" --no-fetch` | Local plan reservation / creation surface still runs |
| `python scripts/meta/check_agents_sync.py --check` | `AGENTS.md` remains generated and in sync |
| `python scripts/meta/validate_plan.py --plan-file docs/plans/26_digimon-isolated-governed-refresh-and-ownership-baseline-repair.md` | Local plan contract remains valid |
| `python scripts/check_markdown_links.py docs/plans/26_digimon-isolated-governed-refresh-and-ownership-baseline-repair.md docs/plans/CLAUDE.md docs/ACTIVE_DOCS.md docs/ops/CAPABILITY_DECOMPOSITION.md` | New documentation links resolve |

---

## Acceptance Criteria

- [x] Repo-local capability ownership source of record exists and is declared in `meta-process.yaml`
- [x] The authoritative shared installer refreshes the intended shared-tooling slice in this worktree
- [x] `AGENTS.md` is in sync after the repair
- [x] The authoritative governed audit narrows to the post-repair state expected by the parent wave
- [x] This plan and the new capability-ownership source-of-record doc pass link and plan validation
- [x] The worktree is left committed and ready for parent-wave landing-safety comparison

---

## Notes

- This plan is intentionally narrower than the older ecosystem-alignment design
  work. It creates the minimum repo-local source-of-record required by the
  governed contract without trying to land the full decomposition design in one
  tooling-refresh slice.
- The authoritative replay decision into the dirty canonical DIGIMON root is
  owned by `project-meta` Plan 67, not by this local plan.
