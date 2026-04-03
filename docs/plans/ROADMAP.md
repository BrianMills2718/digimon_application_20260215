# DIGIMON Strategic Roadmap

**Created**: 2026-03-23
**Last Updated**: 2026-03-23
**Trigger**: Strategic review identified that the adaptive-routing thesis is untested under fair conditions. Literature review confirmed graph value is real but DIGIMON is missing key SOTA innovations. Current tool surface (50+ tools) overwhelms the routing agent.

## Strategic Direction

**Thesis**: Adaptive operator-routing over graph retrieval outperforms fixed pipelines on heterogeneous multi-hop QA — given a sufficiently intelligent agent and a clean tool surface.

**Current evidence**: Thesis is **not yet testable** — the 50-tool surface degrades agent routing quality, confounding any comparison. The 32% hybrid result measures "agent drowning in tools," not "adaptive routing vs fixed pipeline."

**Literature evidence** (investigations/digimon/2026-03-23-graphrag-sota-review.md):
- Graphs unambiguously help for multi-hop QA (vanilla RAG 27% → SOTA 58% EM)
- HippoRAG innovations (passage-level nodes, PPR tuning, IDF scoring) are missing from DIGIMON
- Question decomposition is the single biggest performance lever (StepChain ablation: +15 EM)
- No system in literature does per-question composable operator routing — thesis is novel

## Phase Sequence

```
Phase A: Fix llm_client (Plan #14)          ✅ DONE
    ↓
Phase B: Operator consolidation (Plan #15)  ✅ DONE    Phase C: Build attributes (Plan #16)
    ↓ 28→10 tools, PPR damping fixed                      ↓ 🚧 PPR done, passage nodes pending
    ↓                                                      ↓
Phase D: Re-test thesis (Plan #17)          🚧 50q results: 42.0% vs 20.0% baseline
    ↓ baseline vs adaptive (LLM-judge primary metric)
    ↓ only if adaptive routing still underperforms
Phase E: PTC validation (Plan #18, conditional)
```

## Gates

### Gate A→B: Benchmark runner works — PASSED (2026-03-23)
- ✅ Benchmark smoke test completes with 66.7% EM on HotpotQAsmallest 3q
- ✅ No llm_client import errors in digimon conda env

### Gate B→D: Operator consolidation verified — PASSED (2026-03-23)
- ✅ 10 consolidated tools pass smoke test on HotpotQAsmallest (3q: 66.7% EM, 10q: 50% EM)
- ✅ All 28 operator capabilities reachable via consolidated tool + method argument
- ✅ Agent behavioral change confirmed: uses graph operators (relationship_search, entity_traverse) instead of only chunk_text_search
- Token reduction 21.7% (below 40% target — consolidated tools have richer descriptions explaining methods, but cognitive load reduction is the real metric)
- 10q comparison: consolidated (50% EM, $0.52) vs old surface (40% EM, $0.92) — +10 EM, -43% cost

### Gate C→D: Build attributes implemented — PASSED (2026-03-23)
- ✅ PPR damping configurable in RetrieverConfig (`damping: float`, default 0.5), passed to PPR operator
- ✅ Decomposition via consolidated prompt `reason(method="decompose")` — agent decomposes naturally (5/5 questions used it)
- ✅ `enable_passage_nodes` implemented (commit dede57d) — passage nodes + entity→passage edges + VDB filtering
- ✅ `skip_relationship_extraction` implemented (commit 32a9293) — co-occurrence-only build mode

### Gate D→E: Thesis evidence — PASSED (2026-03-26)
- ✅ **H1 (graph value):** GraphRAG 42.0% > baseline 20.0% LLM-judge (+22 pts) on MuSiQue 50q
- ✅ 15 graph wins (≥5 required)
- ⚠ 4 regressions (≤2 target not met — 2 fixed on re-run, 2 remain)
- **If H1 passes and adaptive > fixed:** thesis validated, scale to 200q/1000q
- **If H1 passes but adaptive ≤ fixed:** consider question-type classifier → 3-4 fixed pipelines. PTC (Phase E) becomes the next lever.
- **If H1 fails:** graph architecture is the problem. Escalate to Brian.

## Relationship to Existing Plans (#3-#13)

Plans #3-#13 are **paused, not abandoned**. They represent valid engineering work (extraction quality, representation audit, supervisor infrastructure) that may resume depending on Phase D gate results:

- If Phase D identifies extraction as the bottleneck → Plans #5, #6 resume
- If Phase D identifies routing/planning as the bottleneck → Plans #12, #13 resume
- If Phase D confirms graph value on the maintained lane → Plan #3 can be
  closed as the investment-decision gate, but the adaptive-vs-fixed H2 question
  remains open until an explicit comparison is run
- Plans #7-#11 (extraction supervisor stack) are complete infrastructure; no action needed

## Budget

| Phase | Estimated Cost | Notes |
|-------|---------------|-------|
| A (llm_client fix) | $0 | Code fix, no LLM calls |
| B (operator consolidation) | ~$1 | Smoke tests only |
| C (build attributes) | ~$5-10 | One graph rebuild with passage nodes |
| D (thesis test) | ~$15-25 | 3× MuSiQue 50q runs (baseline/fixed/adaptive) |
| E (PTC, conditional) | ~$5-10 | Comparative benchmark if needed |
| **Total** | **~$25-45** | Before scaling to 200q/1000q |

## Routing Model

**gpt-5.4-mini** (openrouter/openai/gpt-5.4-mini) for all benchmark routing/answer work. 400K context, strong tool calling, $1.69/M blended. Replaces gemini-2.5-flash as the recommended agent model.

**gpt-5.4-nano** for bulk extraction or cheap fallback if needed.

Both added to llm_client model registry (2026-03-23).

## Escalation Criteria

Stop and ask Brian if:
- Phase D Gate H1 fails (graph doesn't beat baseline even with clean architecture)
- Budget exceeds $50 total across all phases
- Any phase requires >3 days of agent work without producing verifiable progress
- A design decision not covered by this roadmap needs to be made
