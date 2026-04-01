# Plan #18: PTC Validation with Code-Capable Model (Conditional)

**Status:** Planned (conditional — only if Plan #17 shows adaptive routing underperforms despite clean tool surface)
**Type:** implementation
**Priority:** Medium (conditional on Plan #17 results)
**Blocked By:** Plan #17
**Blocks:** None

---

## Gap

**Current:** PTC (Programmatic Tool Calling) implemented on trip-backup branch (commit 0a4c2be, 26 tests). Not validated because: (1) llm_client v1 broke the benchmark runner, (2) flash-lite can't write operator chain code, (3) agents always choose sequential over PTC when given the choice.

**Target:** Validate whether PTC improves routing quality when the agent is forced to compose operators in code rather than sequential calls, using a code-capable model.

**Why:** If Plan #17's operator consolidation (8-10 tools) is sufficient for good routing, PTC is unnecessary. But if even 8-10 sequential tool calls still pollute context (intermediate results accumulate), PTC keeps intermediates in code variables — the next lever for context management.

---

## Trigger Condition

Only proceed if Plan #17 shows:
- H1 passes (graph value confirmed)
- H2 fails (adaptive routing still underperforms fixed pipeline with 8-10 tools)
- Context analysis suggests intermediate results are the remaining bottleneck

If H2 passes with consolidated tools, PTC is deprioritized.

## Plan

### Placeholder — Detailed Plan at Gate-Time

Model: gpt-5.4-mini (strong tool calling + code generation).
Comparison: PTC mode vs sequential mode on same consolidated tool surface.
Infrastructure: PTC implementation already exists on trip-backup branch.

## Acceptance Criteria

- [ ] PTC branch code (trip-backup, commit 0a4c2be) merged or cherry-picked onto a testable branch with current consolidated tool surface
- [ ] Comparative benchmark run completed: PTC mode vs sequential mode on the same consolidated tool surface (8-10 tools), same dataset slice, same model (gpt-5.4-mini)
- [ ] Results show whether PTC reduces context pollution from intermediate results compared to sequential calls
- [ ] If PTC wins: quantified improvement (EM or LLM-judge delta) documented with statistical significance
- [ ] If PTC loses or ties: documented conclusion that consolidated tools are sufficient, PTC deprioritized
- [ ] Context analysis artifact produced showing intermediate-result token counts in PTC vs sequential mode
- [ ] Results recorded in ROADMAP.md with gate decision (proceed with PTC adoption or close Plan #18)

## Budget

~$5-10 for comparative benchmark runs.
