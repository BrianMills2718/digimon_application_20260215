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

**Acceptance:**
- Unit tests cover atom-value extraction and dependent-query forwarding.
- Targeted smoke traces show resolved values entering downstream retrieval.

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

**Acceptance:**
- The failure slice improves over the current post-prompt baseline.
- Lady Godiva and similarly structured bridge questions are either fixed or
  classified with a concrete next repair.

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
- [ ] Atom lifecycle observability is present in benchmark artifacts.
- [ ] The benchmark environment completes end-to-end on the canonical run path.
- [ ] Frozen MuSiQue failure slice rerun shows measurable improvement over the
      current post-prompt baseline.
- [ ] Remaining misses are classified into concrete failure families.
- [ ] Overnight results are written into plans / knowledge artifacts.

---

## Escalation Criteria

Escalate only if:
- required benchmark dependencies cannot be made runnable in any documented env,
- three materially different control-layer fixes fail without shifting the same
  frozen failure family,
- or the budget/throughput guardrail from `ROADMAP.md` is exceeded.
