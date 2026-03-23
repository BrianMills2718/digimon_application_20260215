# Plan #17: Re-Test Thesis with Clean Architecture

**Status:** Planned (detailed plan at gate-time — write when Plans #14, #15, #16 are complete)
**Type:** implementation
**Priority:** High
**Blocked By:** Plan #14 (benchmark runner), Plan #15 (operator consolidation), Plan #16 (build attributes)
**Blocks:** Plan #18 (conditional)

---

## Gap

**Current:** Adaptive-routing thesis tested with 50+ tools and an overwhelmed agent (32% EM, worst mode). The comparison is invalid — it measures agent confusion, not architectural value.

**Target:** Clean three-mode comparison (baseline/fixed/adaptive) with consolidated tools (8-10), HippoRAG-aligned build attributes, and gpt-5.4-mini as routing agent.

**Why:** This is the thesis test. Everything else is infrastructure to make this test fair.

---

## Plan

### Placeholder — Detailed Plan at Gate-Time

Detailed steps, error taxonomy, and diagnostic framework will be written when Plans #14-#16 are complete. Their results inform:
- Which consolidated tools to include in each mode
- Which build attributes to enable (passage nodes, PPR damping, decomposition)
- Baseline model/prompt configuration
- Exact question set (same seed=42 MuSiQue 50q, or updated if prior results suggest a different set)

## Gate Criteria (from ROADMAP.md)

- **H1 (graph value):** Fixed pipeline EM > baseline EM by ≥2.0 on MuSiQue 50q
- **H2 (adaptive value):** Adaptive EM ≥ fixed pipeline EM (any margin)

## Decision Tree

| H1 Result | H2 Result | Action |
|-----------|-----------|--------|
| Pass | Pass | Thesis validated. Scale to 200q, then 1000q. |
| Pass | Fail | Graph helps but adaptive routing doesn't. Try question-type classifier → 3-4 fixed pipelines, or PTC (Plan #18). |
| Fail | — | Graph architecture is the problem. Escalate to Brian. Consider forking HippoRAG/PropRAG. |

## Budget

~$15-25 for three 50q benchmark runs with gpt-5.4-mini.
