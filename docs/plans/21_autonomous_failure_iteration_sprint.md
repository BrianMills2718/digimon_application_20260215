# Plan #21: Autonomous Failure-Iteration Sprint

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** Plan #17 🚧, Plan #20 ✅
**Blocks:** Decision-grade MuSiQue re-test under the restored planning surface

---

## Gap

**Current:** The direct benchmark lane now restores `semantic_plan` and
`todo_write`, and retrieval tools can rewrite broad question-shaped queries to
the active atom. This fixed one control failure family: the agent no longer has
to guess which sub-question to search for. But the benchmark still stalls
because the model often fails to close atoms, promote resolved values into the
TODO state, and advance deterministically to downstream atoms.

**Target:** Run a continuous overnight iteration loop that removes the next
control bottlenecks in order: atom closure, atom advancement, observability of
the plan lifecycle, and failure-family-driven reruns on the frozen MuSiQue
slice.

**Why:** Prompt tweaks already plateaued. The next gains require harness-level
enforcement, better atom-state telemetry, and fast reruns on the same failures.

**Latest observed bottleneck (2026-03-27, updated):**
- The frozen Lady Godiva bridge case now passes after three structural repairs:
  failed-submit observability is derived from tool calls, consolidated
  linearization now preserves graph one-hop payloads, and bridge-probe
  auto-advance accepts a configurable score gap.
- The active bottleneck has moved up one level: scale the repaired bridge logic
  from the single frozen case to the 3-question smoke slice and the 16-question
  failure tranche without reintroducing invalid tool calls or unsupported
  free-form final answers.
- The next implementation order is therefore fixed: persist this slice,
  rerun the 3q smoke set, rerun the 16-failure slice, then classify any
  remaining misses before touching broader MuSiQue dev.

---

## Pre-made Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary benchmark lane | `--backend direct` | Keep the maintained CLI/Python path; no MCP transport in the thesis loop |
| Iteration dataset | Frozen MuSiQue failure slice first | Highest signal-to-cost ratio |
| Control strategy | Harness-managed atom lifecycle, not prompt-only compliance | Previous prompt tweaks did not change behavior enough |
| Verification order | Unit tests → 3q smoke → failure slice rerun | Small real slice before full batch |
| Environment policy | `.venv` for unit tests, `conda env digimon` for full benchmark runs until envs are reconciled | Current dependency split is known and documented |
| Stop condition for this sprint | Complete all phases below or hit explicit escalation criteria | "Still needs iteration" is not sufficient to stop |

---

## 24-Hour Phase Sequence

### Phase 0: Root-Cause Audit

0. Read the latest 1q/3q artifacts, tool traces, and atom lifecycle logs.
1. Convert the current failure into one explicit control diagnosis before
   editing code.

**Acceptance:**
- The next implementation slice is tied to observed trace evidence, not prompt
  speculation.
- The active plan names the current failure family and why it happens.

### Phase 1: Instruction + Plan Alignment

1. Update project `CLAUDE.md` to state the autonomous execution mandate.
2. Add this plan to `docs/plans/` and the plan index.
3. Record runtime findings in `KNOWLEDGE.md` as each overnight slice finishes.

**Acceptance:**
- `CLAUDE.md` explicitly says to continue through uncertainty.
- This plan is indexed and committed.

### Phase 2: Atom Closure Enforcement

4. Implement harness support for resolved atom values, not just query rewriting.
5. Detect when tool output plus TODO state is sufficient to mark the current
   atom complete, even if the model is reluctant.
6. When an atom resolves, persist a compact resolved value that downstream
   retrieval can consume.
7. Ensure consolidated wrappers pass dataset/graph/query context into the
   atom-completion hook so bridge probes can run on top-level retrieval calls.

**Acceptance:**
- Unit tests cover atom-value extraction and dependent-query forwarding.
- Targeted smoke traces show resolved values entering downstream retrieval.
- Top-level `entity_info(profile)` / `relationship_search(graph)` runs can
  perform bridge inference without relying on a hidden auto-profile branch.

### Phase 3: Atom Advancement + Guardrails

7. Prevent the loop from repeatedly searching the same unresolved atom with only
   superficial query variation.
8. Add a harness-level notion of `current_atom`, `completed_atoms`, and
   `next_atom` so the control loop can detect when retrieval should advance.
9. If the current atom is unresolved after repeated equivalent retrieval, force
   a strategy change instead of another near-duplicate search.

**Acceptance:**
- Smoke runs show fewer repeated searches on the same atom.
- At least one previously failing question visibly advances from `a1` to `a2`.
- The current Lady Godiva path shows a hard transition from subject resolution
  to a downstream `Mercia abolished` style retrieval, not another generic
  birthplace search.

### Phase 4: Observability + Benchmark Environment Repair

10. Log atom lifecycle events, query rewrites, dependency values, and advance
    decisions into benchmark artifacts.
11. Repair the current post-run benchmark env gap (`prompt_eval` import in the
    `digimon` env) or document a canonical execution path that completes.

**Acceptance:**
- Benchmark artifacts make the atom lifecycle inspectable.
- A benchmark run completes end-to-end without crashing after results are saved.

### Phase 5: Failure Slice Rerun

12. Re-run the frozen MuSiQue failure slice.
13. Group remaining misses by systemic family: representation, entity
    resolution, atom closure, answer synthesis, or tool contract.
14. Fix the highest-yield family first and rerun immediately.
15. If bridge questions improve but submission still blocks on dependent
    disambiguation atoms, implement harness-side handling for those optional
    clarifier atoms before scaling further.

**Acceptance:**
- The failure slice improves over the current post-prompt baseline.
- Lady Godiva and similarly structured bridge questions are either fixed or
  classified with a concrete next repair.

**Progress update (2026-03-27):**
- `2hop__511454_120259` now passes end-to-end in the frozen single-question
  lane (`atom_bridge_gap_r9`) after:
  - failed-submit observability override from tool calls
  - relationship/neighbor linearization repair
  - configurable bridge-probe score-gap threshold
- The follow-up `atom_bridge_priority_r14` rerun kept Lady Godiva green on the
  maintained direct lane (`EM/F1 = 1.0`) after making bridge-qualified updates
  win over weaker direct profile completions in the subject auto-profile path.
- The 3q smoke rerun `atom_bridge_priority_smoke_r14` is only partially valid:
  one question failed before any tool use due OpenRouter DNS/timeout errors,
  one timed out mid-run, and the remaining namesake question exposed a new
  logic family (`person after whom...` drifting to place / saint-name
  candidates).
- A follow-up single-question rerun on `2hop__199513_801817`
  (`atom_bridge_type_filter_r15`) confirmed that coarse-type filtering removes
  the previous `brazil` bridge error, but the question still resolves to the
  city-name gloss (`Saint Joseph of the Fields`) rather than the gold answer.
- `namesake_submit_gate_r16` changed the benchmark contract so failed
  `submit_answer` calls no longer leak a free-form or metadata fallback into
  the scored prediction. The same question now fails as an honest
  `missing_required_submit` with an empty prediction instead of scoring
  `Saint Joseph of the Fields`.
- `namesake_alias_probe_r17` preserved alias-like entity queries grounded in
  cached evidence instead of always collapsing them back to the generic active
  atom. That changed the search path, but also exposed a second benchmark leak:
  retrieval-stagnation forced-final answers could still score `Saint Joseph`
  while all semantic-plan atoms remained pending.
- `namesake_forced_final_guard_r18` closed that second leak. Forced-terminal
  freeform answers are now suppressed when the final conversation trace still
  shows pending TODO atoms. The same question again ends as
  `missing_required_submit` with an empty prediction, but it now spends longer
  exploring alias-related retrieval paths before failing.
- `namesake_birthcue_guard_r20` removed the next false-positive control path.
  Birthplace atoms no longer auto-complete from unrelated connected places like
  `california` after `Saint Joseph` is resolved. The same question now reaches
  a cleaner state: `a1` closes to `Saint Joseph`, `a2` stays pending, the run
  retrieves `Nazareth` only indirectly through Holy Family evidence, and
  `submit_answer("Nazareth")` is correctly rejected because the atom lifecycle
  still lacks a defensible completion update for the birthplace relation.
- Next verification rung is no longer another 1q tweak. It is:
  - preserve the verified Lady Godiva and bridge-priority slice
  - repair the namesake / semantic-gloss failure family by adding a stronger
    evidence-ranked completion path for unresolved place relations instead of
    further answer gating
  - rerun the 3q smoke slice once provider conditions are stable enough to make
    it decision-grade
  - only then rerun the larger failure tranche

### Phase 6: Scale And Record

15. If the failure slice meaningfully improves, run the larger MuSiQue dev
    batch.
16. Update `Plan #17`, `KNOWLEDGE.md`, and investigation artifacts with the
    overnight results, remaining failures, and next gate.

**Acceptance:**
- Results are written down, not left in chat.
- The next gate for Plan #17 is explicit.

---

## Error Taxonomy

| Error | Diagnosis | Next Action |
|-------|-----------|-------------|
| Atom never closes | Model sees evidence but never writes resolved value | Add harness-level atom completion heuristics or force explicit resolved-value writeback |
| Query rewrite fires but answer stays wrong | Retrieval now reaches the right sub-question, but answer synthesis latches on to an earlier distractor | Tighten atom advancement and answer gating |
| Repeated equivalent retrieval | Same atom queried with shallow paraphrases | Add duplicate-query detection and force method/entity change |
| Benchmark run crashes after evaluation | Missing post-run dependency | Fix env contract or move post-run step behind optional import gate |
| Failure slice improves only on stochastic reruns | Non-deterministic model behavior | Require repeated runs or stronger control constraint before promotion |

---

## Backtracking Ladder

1. If atom forwarding is visible but atoms still do not close, implement
   harness-side atom completion.
2. If atoms close but downstream retrieval still ignores them, enforce
   downstream query construction from resolved values.
3. If retrieval reaches the right evidence but final answers are still wrong,
   tighten answer synthesis and evidence gating.
4. After three materially different control fixes without movement on the frozen
   slice, update the plan with the failed hypotheses and escalate the strategy.

---

## Acceptance Criteria

- [ ] Project instructions explicitly codify autonomous continuous execution.
- [ ] Plan index includes this sprint plan.
- [x] Atom lifecycle observability is present in benchmark artifacts.
- [ ] The benchmark environment completes end-to-end on the canonical run path.
- [x] Frozen single-question bridge rerun (`2hop__511454_120259`) shows
      measurable improvement over the post-prompt baseline.
- [ ] Frozen MuSiQue failure slice rerun shows measurable improvement over the
      current post-prompt baseline.
- [ ] Remaining misses are classified into concrete failure families.
- [x] Overnight results are written into plans / knowledge artifacts.

---

## Escalation Criteria

Escalate only if:
- required benchmark dependencies cannot be made runnable in any documented env,
- three materially different control-layer fixes fail without shifting the same
  frozen failure family,
- or the budget/throughput guardrail from `ROADMAP.md` is exceeded.
