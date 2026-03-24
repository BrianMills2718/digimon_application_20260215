# ADR-015: Strategic Risks and Open Questions for Thesis Test

**Status**: Proposed
**Date**: 2026-03-23

## Context

Plan #17 will test the thesis "GraphRAG adds value for multi-hop QA beyond what simpler retrieval can achieve." Before executing, these strategic risks and methodological concerns need to be documented and either mitigated or accepted.

## Risks

### R1: Prescribed prompt vs adaptive routing

The consolidated prompt (`agent_benchmark_consolidated.yaml` v2.0) tells the agent exactly what pipeline to follow: decompose → entity_search → entity_traverse(ppr) → relationship_search → chunk_retrieve → reason(answer). If the agent follows this prescription, it's executing a fixed pipeline, not doing adaptive routing.

**Impact**: The thesis test may prove "a good prompt helps" rather than "adaptive routing adds value."

**Mitigation options**:
- (a) Accept this for now — proving graph value is the first priority; adaptive vs fixed is a second-order question
- (b) Run a comparison with a minimal prompt (just tool descriptions, no strategy guidance) after the primary test
- (c) Add question-type detection that selects different strategies per question (true adaptive routing)

**Decision**: Accept (a) for Plan #17. The current test answers "does the graph help?" which is prerequisite to "does adaptive routing help?" If graph value is confirmed, Plan #18 or a future plan can test adaptive routing specifically.

### R2: MuSiQue overfitting

All development (19q diagnostic, prompt tuning, failure analysis, graph rebuild) is on MuSiQue. The prompt contains MuSiQue-specific language ("most questions here are 2-4 hops"). No cross-benchmark validation is planned.

**Impact**: Results may not generalize to other multi-hop benchmarks (HotpotQA, 2WikiMultiHopQA) or real-world queries.

**Mitigation**: After Plan #17, run at least a 10q HotpotQA comparison with the same consolidated tools and prompt. This doesn't need to be part of the thesis test but should be done before declaring generalizability. Add to Plan #17 Phase 3 as a stretch goal.

### R3: Cost asymmetry

Baseline costs ~$0.01/question (no tools, just LLM answer). GraphRAG costs ~$0.03-0.05/question (tool calls, graph traversal). The "graph wins" methodology counts questions without cost-adjusting.

**Impact**: If GraphRAG costs 5x more but only wins on 30% of questions, the cost-per-correct-answer may not justify the graph.

**Mitigation**: Track cost per question alongside accuracy. Report cost-per-correct-answer as a secondary metric. The graph build cost ($3-5 one-time) amortizes over many queries and is not the concern — per-query cost is.

### R4: Small sample size (n=19)

The diagnostic set is 19 questions. A single question flip = 5.3 percentage points. Statistical significance is not achievable at this sample size.

**Impact**: Intermediate decisions (whether to rebuild, which failures to fix) are made on noisy data.

**Mitigation**: The 19q set is for diagnosis and iteration, not for statistical claims. Plan #17 Phase 3 (50q) provides larger n. Phase 4 (200q/1000q) would be needed for publishable claims. Accept n=19 for development iteration.

### R5: Model-dependent results

Results depend on gpt-5.4-mini. A different routing model might produce different results (better or worse). If gpt-5.4-mini is exceptionally good at QA, the marginal value of graph tools is harder to demonstrate.

**Impact**: Results may not transfer to other models.

**Mitigation**: After Plan #17, spot-check with one other model (e.g., deepseek-chat or gemini-2.5-flash). Not blocking, but needed before generalizing.

## Off-the-shelf alternatives

The audit identified areas where DIGIMON hand-rolls functionality that libraries provide:

| Area | DIGIMON | Alternative | Assessment |
|------|---------|-------------|------------|
| Graph construction | Custom extraction pipeline | Microsoft GraphRAG, HippoRAG OSS | DIGIMON's composable operator model is the differentiator. Swapping extraction backend is possible but the operator routing layer is custom by design. |
| VDB indexing | FAISS directly | ChromaDB, Qdrant, LlamaIndex | FAISS is fine for the current scale. Higher-level abstractions would add dependency without clear value. |
| Benchmark eval | Custom EM/F1/LLM-judge | RAGAS, DeepEval | Worth considering for publishable results. Custom eval gives us control but means results aren't directly comparable to papers. |
| Question decomposition | Single-shot `meta.decompose_question` | IRCoT (iterative), StepChain (on-the-fly) | The consolidated prompt enables iterative decomposition via retry strategies. A dedicated iterative loop could be added as a `reason` method later. |
| PPR | igraph via BaseGraph | HippoRAG's PPR implementation | Same algorithm (igraph PPR). IDF seeding is custom but equivalent to HippoRAG's. No need to switch. |

**Decision**: No immediate action on off-the-shelf alternatives. The current architecture works and the composable operator model is the unique contribution. Revisit benchmark eval (RAGAS) if/when results need to be published.

## Missing long-term planning

| Gap | Impact | Action |
|-----|--------|--------|
| No Plan #19 for 200q/1000q scale-up | Can't plan beyond Plan #17 | Write at gate-time per ROADMAP policy |
| No connection to causal-epistemic reasoning goal | DIGIMON is a tool in a larger system but this isn't documented | Add a section to CLAUDE.md or a separate vision doc when the pipeline crystallizes |
| No cost tracking against ROADMAP budget | Spend may exceed estimates | Query observability DB before Phase 3 |

## Consequences

Documenting these risks makes them visible to future agents and to Brian. Each risk has a mitigation path. None are blocking for Plan #17 execution, but R1 (prescribed vs adaptive) is the most important to address after the thesis test.
