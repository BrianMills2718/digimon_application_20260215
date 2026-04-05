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
  Artifact history now shows three distinct truths:
  - `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T032944Z.json` was the
    pre-repair failure: `A1 -> Myanmar`, `A2/A3/A4` pending, repeated submit
    rejections, `CONTROL_CHURN_THRESHOLD_EXCEEDED`, forced-final answer
    `by airplanes`
  - `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T040232Z.json` is the
    post-repair truthful artifact: still unresolved, but now
    `predicted=''`, `submit_completion_mode=missing_required_submit`, and
    `forced_terminal_accept_reason='control_churn'`
  - `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T051256Z.json` is the
    post-idempotence artifact: still unresolved, but now the repeated
    `todo_write` runtime-error loop on completed atom `a2` is gone. The run
    records `atom_manual_reused` events instead of `atom_manual_rejected`,
    ends with `predicted=''`, `submit_completion_mode=missing_required_submit`,
    and `first_terminal_failure_event_code='REQUIRED_SUBMIT_NOT_ACCEPTED'`.
    The remaining blocker is upstream controller reasoning: `a3` resolves to
    `soviet union`, then `a4` stays pending and submit retries churn.
  - `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T053035Z.json` is the
    post-bridge-hardening artifact: the bad `a3 -> soviet union` completion is
    gone, but the controller still fails to ground the Portuguese hop. The run
    leaves `a3` and `a4` pending, burns the full 20-call tool budget, and then
    forced-finalizes `communist takeover` with
    `forced_terminal_accept_reason='budget_exhaustion'`.
- This shell has `LLM_CLIENT_TIMEOUT_POLICY=ban`, so benchmark output must
  distinguish planned per-turn timeout from runtime-enforced timeout.
- A new runtime clue emerged during the same probes:
  `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T035805Z.json` logged
  `LINEARIZATION_DATA_LOSS` for `chunk_retrieve(method=by_ids)`, meaning raw
  evidence existed but the controller-facing linearized summary collapsed to an
  effectively empty message.
- The focused unit ladder is restored after making `Config/LLMConfig.region_name`
  nullable again. This was a harness defect, not a controller defect, but it
  needed to be repaired so the verification ladder stayed trustworthy.

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

**Status**
- Complete. Verified by focused unit suite plus live probe
  `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T040232Z.json`.

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

**Status**
- Complete on the shared/runtime boundary plus DIGIMON state boundary.
  - Shared `llm_client` worktree commit `0fda376` replaced pending-atom
    submit-churn forced-finalization with a TODO-progress gate.
  - DIGIMON artifact `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T041229Z.json`
    proved the failure moved from `control_churn` forced-finalization to a more
    truthful `budget_exhaustion` / runtime-error path.
  - DIGIMON artifact `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T051256Z.json`
    then proved unchanged completed atoms are now idempotent under
    full-list `todo_write`, removing the repeated `a2` manual-rejection loop.

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

**Current frontier**
- The latest `754156` probe shows the right first change: the false
  `soviet union` bridge path is gone. The remaining failure is now controller
  follow-through: `a3` stays unresolved, the run does not capitalize on the
  Portuguese clue, and broad retrieval loops consume the full tool budget
  before forced-finalization. The next slice should strengthen reflected
  recovery routing and loop suppression on unresolved atoms, not revisit bridge
  validation.
- Follow-up probe `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T054718Z.json`
  validates the narrowed recovery-surface guard: the earlier `a2` mis-blocking
  regression from `...T053930Z.json` is gone, `a4` no longer remains pending,
  and the controller reaches later-hop entity/subgraph work without
  policy-induced tool runtime errors. The remaining frontier is narrower and
  more truthful: unresolved `a3` plus repeated rejected-submit churn under an
  unchanged evidence digest.
- Follow-up probe `results/MuSiQue_gpt-5-4-mini_consolidated_20260405T060338Z.json`
  validates the new early breaker for repeated suppressed submits without TODO
  progress. The controller still fails, but it now fails earlier and more
  honestly: `forced_terminal_accept_reason='control_churn'`, tool calls drop to
  `28` from `32`, and benchmark artifacts no longer pretend the late failure
  was ordinary budget exhaustion. The next frontier is the unresolved-hop
  reasoning for `atom3/atom4`, not more submit-loop hygiene.

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
