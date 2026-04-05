# Plan #30: Overnight Controller Grounding And Truthful Finalization

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Next trustworthy 19q rerun

---

## Mission

Stabilize the maintained DIGIMON benchmark lane so overnight iteration stays
truthful and grounded. The immediate frontier is no longer "more retrieval";
it is:

1. stop scoring ungrounded forced-final answers as if they were valid submits,
2. stop unresolved-hop submit churn from escalating into a scored forced-final
   answer,
3. verify that recovery/reflection changes actually alter controller behavior on
   the real failing questions.

This plan assumes all work happens in worktrees with frequent verified commits.

---

## Current Verified State

- `619265` is no longer the main blocker. The current lane can answer it with a
  grounded submit after the submit-breaker repair.
- `754156` is currently the clearest live controller failure family.
  Artifact:
  `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T032944Z.json`
  shows:
  - `A1 -> Myanmar`
  - `A2/A3/A4` still pending
  - repeated submit rejections
  - `CONTROL_CHURN_THRESHOLD_EXCEEDED`
  - forced-final answer `by airplanes`
- This shell has `LLM_CLIENT_TIMEOUT_POLICY=ban`, so benchmark output must
  distinguish planned per-turn timeout from runtime-enforced timeout.

---

## Phases

### Phase 0 — Sprint Contract

**Tasks**
- Strengthen `CLAUDE.md` with explicit worktree/commit/autonomy language.
- Register this plan in `docs/plans/CLAUDE.md`.
- Create a progress artifact that records mission, acceptance criteria, and the
  current phase.

**Acceptance**
- `CLAUDE.md` explicitly requires worktree-only implementation and commit-per-slice.
- This plan is linked from the plan index.
- A progress file exists and is updated as phases complete.

### Phase 1 — Truthful Finalization And Timeout Provenance

**Tasks**
- Ensure benchmark artifacts do not preserve/scored forced-final answers when:
  - normal `submit_answer` was never accepted,
  - semantic-plan atoms remain pending,
  - and the forced-final path was triggered by control churn rather than true
    budget/turn exhaustion.
- Keep timeout artifacts truthful:
  - reconstruct partial telemetry from observability when cancellation loses it,
  - record requested/planned/runtime-enforced timeout separately.
- Add deterministic tests for the above.

**Acceptance**
- A `control_churn` forced-final answer with pending atoms is not preserved as
  the scored prediction.
- Timeout artifacts contain partial tool provenance when available.
- Focused unit suite passes.

### Phase 2 — Controller Anti-Churn Repair

**Tasks**
- Repair the active controller path so repeated pending-atom submit rejections
  do not route directly into "give best final answer now".
- Prefer one of these general repairs:
  - inject explicit active-atom continuation guidance after pending-atom reject,
  - suppress submit retries while the active atom is unchanged and unresolved,
  - or route forced-final termination on this family into honest failure rather
    than a scored answer.
- Keep the fix general; no question-shaped prompt hacks.

**Acceptance**
- At least one targeted failing question no longer ends with a scored forced-final
  answer while pending atoms remain.
- Unit/integration coverage exists for the repaired policy.

### Phase 3 — Recovery Loop Strengthening

**Tasks**
- Verify that repeated unresolved-atom traces produce a materially different
  next retrieval/control move.
- If the current reflection hint is still too weak, strengthen controller-side
  consumption of the hint:
  - better query override,
  - avoid-values respected,
  - target tool/method preferred on the next step.
- Keep this bounded and typed.

**Acceptance**
- A focused probe shows the controller taking a changed next step because of
  the recovery hint, not just emitting another trace event.

### Phase 4 — Targeted Tranche Verification

**Target questions**
- `2hop__619265_45326`
- `4hop3__754156_88460_30152_20999`
- `2hop__199513_801817` or another currently active unresolved-hop control case

**Tasks**
- Rerun each question under fixed settings.
- Reclassify from live artifacts:
  - grounded success
  - honest unresolved failure
  - control churn
  - timeout/runtime issue

**Acceptance**
- Three fresh artifacts exist.
- The failure-family table in `CURRENT_STATUS.md` reflects the new artifacts.

### Phase 5 — Promotion Gate

**Tasks**
- Decide whether the lane is ready for the next broader rerun.
- If yes, run the next bounded slice.
- If no, stop broad spend and document the blocker family precisely.

**Acceptance**
- Either:
  - a bounded broader rerun artifact exists,
  - or the blocker is explicitly documented with no ambiguity about what the
    next local fix should be.

---

## Verification Ladder

1. Unit tests
2. Single-question probe
3. Small frozen tranche
4. Broader rerun only after the targeted tranche is clean enough

---

## Non-Negotiable Constraints

- No question-specific prompt hacks.
- No canonical-checkout implementation.
- Commit after every verified slice.
- If uncertainty remains, document it in the plan and `KNOWLEDGE.md`, then
  continue with the safest next bounded step.
