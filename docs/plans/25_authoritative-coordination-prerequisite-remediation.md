# Plan #25: authoritative coordination prerequisite remediation

**Status:** ✅ Complete

**Verified:** 2026-04-02T12:30:14Z
**Verification Evidence:**
```yaml
completed_by: scripts/complete_plan.py
timestamp: 2026-04-02T12:30:14Z
tests:
  unit: 8/8 commands passed
  e2e_smoke: covered by plan-declared commands
  e2e_real: covered by plan-declared commands
  doc_coupling: covered by plan-declared commands
commit: 3bd1311
```
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** project-meta Plan #60 closeout for the DIGIMON rollout wave

---

## Gap

**Current:** DIGIMON had active planning and benchmark work, but it was missing the
sanctioned local plan-coordination entrypoints, generated `AGENTS.md` contract,
validator scripts, and worktree Makefile entrypoints that the new
project-meta authoritative coordination rollout expects. The canonical root is
also dirty, so remediation must happen in a clean worktree without touching the
ongoing benchmark lane.

**Target:** The clean remediation worktree should audit as mechanically
`governed`, expose local plan reservation / claim / validation entrypoints, and
carry a repo-local plan that documents exactly what was remediated and how it
was verified.

**Why:** DIGIMON is currently the blocked repo in the authoritative
coordination rollout. Until it exposes the sanctioned local interfaces, agents
cannot safely allocate plans, claim work, or bootstrap future DIGIMON work from
inside the repo without falling back to external `project-meta` tooling.

---

## Scope Boundary

This plan is **only** about authoritative coordination prerequisites:

- generated `AGENTS.md` compatibility
- local plan-coordination scripts
- local validators required by governed audit
- local worktree entrypoints and read-gating sync

This plan explicitly does **not** change:

- benchmark architecture
- graph build logic
- retrieval operators
- MuSiQue evaluation methodology

---

## References Reviewed

- `CLAUDE.md` — DIGIMON repo governance, execution, and benchmark policy
- `docs/plans/CLAUDE.md` — DIGIMON plan index and active benchmark lane
- `meta-process.yaml` — local governed-repo configuration and enabled features
- `Makefile` — existing repo interface and missing worktree entrypoints before remediation
- `scripts/relationships.yaml` — current coupling surface for DIGIMON docs/scripts
- `/home/brian/projects/project-meta/scripts/meta/install_governed_repo.py` — sanctioned installer used for this remediation
- `/home/brian/projects/project-meta/scripts/meta/audit_governed_repo.py` — external mechanical governed audit used as the acceptance oracle
- `/home/brian/projects/project-meta/docs/plans/60_wave-1-authoritative-coordination-adoption-and-digimon-prerequisite-remediation.md` — parent rollout plan this remediation unblocks

---

## Files Affected

- `CLAUDE.md` — add generated-AGENTS-compatible governance sections
- `AGENTS.md` — replace symlink with rendered generated output
- `Makefile` — append sanctioned worktree coordination targets
- `docs/plans/CLAUDE.md` — index this remediation plan
- `docs/plans/25_authoritative-coordination-prerequisite-remediation.md` — this plan
- `meta-process/templates/agents.md.template` — installer-synced template input
- `scripts/check_doc_coupling.py` — local validator entrypoint
- `scripts/check_markdown_links.py` — local validator entrypoint
- `scripts/check_required_reading.py` — local read-gating verifier
- `scripts/sync_plan_status.py` — local plan-status verifier
- `scripts/meta/check_agents_sync.py` — generated AGENTS verifier
- `scripts/meta/check_coordination_claims.py` — local claim registry entrypoint
- `scripts/meta/create_plan.py` — local plan reservation / creation entrypoint
- `scripts/meta/file_context.py` — required plan/file-scope validator dependency
- `scripts/meta/hook_log.py` — local hook runtime helper
- `scripts/meta/plan_reservations.py` — local plan reservation backend
- `scripts/meta/render_agents_md.py` — generated AGENTS renderer
- `scripts/meta/validate_plan.py` — local plan validator
- `scripts/meta/worktree-coordination/create_worktree.py` — sanctioned worktree entrypoint

---

## Plan

### Steps

1. Install the sanctioned governed-repo surfaces into the clean DIGIMON
   remediation worktree using the shared installer from `project-meta`.
2. Patch `CLAUDE.md` so `AGENTS.md` can be generated without symlink coupling or
   missing required sections.
3. Re-run the installer to completion and confirm the external governed audit is
   `PASS`.
4. Verify the repo-local entrypoints from inside DIGIMON:
   - claim check
   - plan creation
   - plan validation
   - generated AGENTS sync
5. Commit the DIGIMON remediation slice with the plan and verification evidence.

---

## Failure Modes And Responses

| Failure Mode | Diagnosis | Response |
|--------------|-----------|----------|
| Installer stops on AGENTS render | `render_agents_md.py` complains about missing `CLAUDE.md` sections or symlinked `AGENTS.md` | Add the required sections to `CLAUDE.md`, remove symlink coupling by letting installer render a real file, rerun installer |
| Audit still reports `partial` after install | Missing validators or Makefile targets remain | Use the audit JSON as the source of truth, install only the missing sanctioned primitives, rerun |
| Local entrypoint exists but fails at runtime | Missing repo-local dependency or bad path assumptions | Run the entrypoint directly inside the DIGIMON worktree and patch the local script or config until it passes |
| Remediation drifts into benchmark code | Production graph/retrieval files appear in the diff | Stop, split that work into a separate benchmark plan, and keep this plan limited to coordination prerequisites |

---

## Required Tests

### New / Explicit Verification For This Plan

| Command | What It Verifies |
|---------|------------------|
| `python scripts/meta/check_agents_sync.py --check` | `AGENTS.md` is generated, refreshable, and in sync with `CLAUDE.md` |
| `python scripts/meta/check_coordination_claims.py --check --project Digimon_for_KG_application --json` | Local claim entrypoint works inside DIGIMON |
| `python scripts/meta/create_plan.py --dry-run --title "coordination smoke" --no-fetch` | Local plan reservation / creation path works |
| `python scripts/meta/validate_plan.py --plan-file docs/plans/25_authoritative-coordination-prerequisite-remediation.md` | This plan passes the local validator |
| `python /home/brian/projects/project-meta_worktrees/plan-58-authoritative-registry-rollout/scripts/meta/audit_governed_repo.py --repo . --json` | DIGIMON audits as mechanically governed from the shared rollout oracle |

### Existing Checks That Must Still Pass

| Command | Why |
|---------|-----|
| `python scripts/sync_plan_status.py --check` | Plan index remains in sync after adding Plan 25 |
| `python scripts/check_markdown_links.py docs/plans/25_authoritative-coordination-prerequisite-remediation.md docs/plans/CLAUDE.md` | New plan links are valid |
| `python scripts/check_doc_coupling.py --strict` | Local doc-coupling validator still passes after the remediation |

---

## Acceptance Criteria

- [x] DIGIMON remediation worktree audits as mechanically `governed`
- [x] `AGENTS.md` is a generated file, not a symlink to `CLAUDE.md`
- [x] Local `check_coordination_claims.py`, `create_plan.py`, and
      `plan_reservations.py` are present and runnable
- [x] Local `validate_plan.py`, `file_context.py`, and
      `check_markdown_links.py` are present and runnable
- [x] The Makefile exposes sanctioned `worktree`, `worktree-list`, and
      `worktree-remove` targets
- [x] This plan records the remediation scope and verification commands clearly
- [x] The remediation slice is committed in the clean DIGIMON worktree

---

## Notes

- This plan intentionally remediates the clean worktree only. The canonical
  DIGIMON checkout is dirty and should remain untouched during this slice.
- Capability ownership metadata is not part of the blocking governed audit for
  DIGIMON in this wave; that remains a later cross-project planning concern.
