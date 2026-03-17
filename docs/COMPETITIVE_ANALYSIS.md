# Competitive Analysis: DIGIMON vs Multi-Hop QA SOTA

**Last Updated**: 2026-02-16

## Important: Sample Size Caveat

DIGIMON results are on 50-question subsets. Literature baselines are on 1000-question full benchmarks. These are **not directly comparable** — 50q results have wider confidence intervals and may not generalize. 1000-question runs are pending.

## Benchmark: 2WikiMultiHopQA

1000 questions across 4 types: compositional (413), comparison (244), bridge_comparison (235), inference (108). 6119 corpus paragraphs.

### Scoreboard (literature baselines, 1000q)

| Method | LLM | EM | F1 | Architecture | Source |
|--------|-----|----|----|-------------|--------|
| BM25 | GPT-4o | 40.3 | 44.8 | Sparse retrieval | HopRAG paper |
| GraphRAG (Microsoft) | GPT-4o | 22.5 | 27.5 | Community summaries | HopRAG paper |
| RAPTOR | GPT-4o | 53.8 | 61.5 | Recursive tree summarization | HopRAG paper |
| TCR-QF | ? | 59.8 | — | Query-focused text chunking | Search results |
| SiReRAG | GPT-4o | 59.6 | 67.9 | Similarity + relevance | HopRAG paper |
| HopRAG | GPT-4o | 61.1 | 68.3 | Logical passage graph | arXiv 2502.12442 |
| StepChain | GPT-4o | 62.4 | 70.7 | Step-by-step KG reasoning | arXiv 2510.02827 |
| HippoRAG | GPT-3.5 | 66.4 | 74.0 | PPR spreading activation | arXiv (ICLR 2025) |

DIGIMON has not yet been evaluated on 2WikiMultiHopQA. Our baselines are on HotpotQA and MuSiQue (see below).

### DIGIMON Results: HotpotQA (50q subset)

| Configuration | EM | F1 | LLM-judge | Source |
|--------------|----|----|-----------|--------|
| deepseek-chat direct mode | 68.0 | 82.5 | 90.0 | Our eval (50q) |
| gemini-3-flash fixed mode | 61.5 | 73.9 | — | Our eval (200q) |

### DIGIMON Results: MuSiQue (50q subset)

| Configuration | EM | F1 | LLM-judge | Source |
|--------------|----|----|-----------|--------|
| o4-mini direct mode | 52.0 | 67.7 | 80.0 | Our eval (50q) |

Notes:
- HippoRAG achieves SOTA with GPT-3.5-turbo, meaning architecture matters more than LLM.
- Microsoft GraphRAG (22.5% EM) is terrible at multi-hop QA — community summarization is wrong for this task.
- The competitive band is narrow: 59-67% EM. Small retrieval improvements have outsized impact.

## Capability Mapping

What each competitor does, and our equivalent operator:

| Technique | Who | Our Equivalent | Status |
|-----------|-----|---------------|--------|
| PPR spreading activation | HippoRAG | `entity.ppr` | Exists, untested on 2Wiki |
| NER → entity linking | HippoRAG | `meta.extract_entities` → `entity.link` | Exists |
| Question decomposition | StepChain | `meta.decompose_question` + `meta.synthesize_answers` | Exists |
| Logical passage graph | HopRAG | `PassageGraph` + passage-level retrieval | Partial — graph type exists, no retrieval pipeline |
| Multi-hop graph traversal | HopRAG, DALK | `subgraph.khop_paths`, `entity.onehop` | Exists |
| Community summaries | GraphRAG | `community.from_level` | Exists (bad for QA — 22.5% EM) |
| Subgraph optimization | GR | `meta.pcst_optimize` | Exists |
| Iterative agent reasoning | ToG, KGP | Loop operators + `entity.agent`, `relationship.agent` | Exists |
| IDF-weighted entity scoring | HippoRAG | `entity.tfidf` | Exists |

**Gap**: HopRAG's passage-level logical relationship graph. We have `PassageGraph` as a graph type but no retrieval pipeline built for it. Low priority — HopRAG (61.1%) is below HippoRAG (66.4%).

## Our Unique Advantages

### 1. Per-Question Adaptive Composition (primary differentiator)

Every competitor is a fixed pipeline. HippoRAG always runs NER→link→PPR→chunk. StepChain always decomposes. They cannot adapt per question.

2WikiMultiHopQA has 4 question types. Different types likely benefit from different strategies:

| Question Type | Count | Likely Best Strategy |
|--------------|-------|---------------------|
| Compositional | 413 | Entity linking + multi-hop chains (`hipporag`, `dalk`) |
| Comparison | 244 | Parallel entity retrieval + direct comparison (`basic_local`) |
| Bridge comparison | 235 | Multi-hop + comparison hybrid (`tog`, `kgp`) |
| Inference | 108 | Iterative reasoning with backtracking (`tog`, `kgp`) |

In Mode 1, the agent sees the question type and picks a different operator chain. In Mode 3, `auto_compose` selects from 10 methods. Neither capability exists in the literature.

**Untested hypothesis**: Per-question method selection outperforms the best single pipeline. This is the publishable contribution — not "we beat HippoRAG by 2 points" but "composable architectures with adaptive selection outperform fixed pipelines on heterogeneous QA."

### 2. Multi-Pipeline Ensemble

Run multiple pipelines on the same question, collect candidate answers, synthesize the best. Nobody else can do this because they only have one pipeline. We have 10.

```
for method in [hipporag, basic_local, tog]:
    answers.append(execute_method(method, query))
best = meta.synthesize_answers(question, answers)
```

Cost: 3x retrieval per question. Benefit: covers cases where one pipeline misses but another hits.

### 3. Entity Canonicalization (planned)

No competitor normalizes their KG after extraction. They all live with duplicate entities ("Barack Obama" / "Obama" / "President Obama" as separate nodes). PPR gets stuck at dead-end duplicates.

Post-build entity dedup via onto-canon's `match_entities_to_concepts()` merges duplicates, improving graph connectivity. PPR propagates further on a connected graph → better multi-hop recall.

Expected impact: +2-3% EM from better graph quality alone.

### 4. 27 Typed Operators with Machine-Readable Contracts

Others package retrieval as monoliths. We expose operators with typed I/O slots, compatibility metadata, and 95 valid 3-step chains. An agent can inspect intermediate results and pivot — if VDB search returns low-confidence matches, fall back to TFIDF or PPR dynamically.

This is infrastructure for research velocity, not directly a benchmark advantage. But it means we can test new retrieval strategies in minutes instead of days.

### 5. Multiple Graph Types on Same Corpus

ER + RK + Tree + Passage graphs simultaneously. Could query across representations. Competitors are locked to one.

## What We're Weak At

1. **Tuning**: Our pipelines exist but haven't been optimized. HippoRAG spent months tuning PPR damping factor, top-k, NER strategy. We've run exactly one benchmark.
2. **Passage-level retrieval**: HopRAG's logical passage graph is a different approach we haven't explored.
3. **Agent overhead**: Mode 1 (agent composition) adds latency and cost. For 1000 questions, this matters.
4. **HippoRAG's entity linking is more sophisticated**: They use NER + entity linking with schema-aware matching. Our `entity.link` does embedding similarity, which can miss exact-match entities.

## Benchmark Strategy

### Phase 1: Establish 2Wiki Baseline (immediate)

1. Build 2WikiMultiHopQA graph (6119 docs, ~2-3hr with fallback chain)
2. Run 1000 questions through auto_compose
3. Establish baseline EM/F1

### Phase 2: Pipeline Comparison (1 day)

Run all 10 methods on a 50-question sample (balanced across 4 types). Find:
- Best overall method
- Best method per question type
- Whether type-aware routing beats best single method

### Phase 3: Adaptive Composition (the publishable result)

1. Implement type-aware method routing in auto_compose
2. Run full 1000-question benchmark
3. Compare: best single pipeline vs type-aware routing vs ensemble
4. If type-aware wins → paper contribution

### Phase 4: Graph Quality (if needed)

1. Entity canonicalization via onto-canon
2. Rebuild graph, re-run benchmark
3. Measure delta from graph quality improvement

## Cost Estimates

| Step | Model | Est. Cost |
|------|-------|----------|
| Graph build (6119 docs) | gemini-2.5-flash + fallback | ~$3-5 |
| 1000q benchmark (auto_compose) | gemini-3-flash | ~$35-50 |
| 50q pipeline comparison (10 methods) | gemini-3-flash | ~$25-35 |
| 1000q final benchmark | gemini-3-flash | ~$35-50 |

Total to publishable result: ~$100-140.

## References

- HippoRAG: "HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models" (ICLR 2025)
- HopRAG: arXiv 2502.12442 — "Multi-Hop Reasoning for Logic-Aware Retrieval-Augmented Generation"
- StepChain: arXiv 2510.02827 — "StepChain GraphRAG: Reasoning Over Knowledge Graphs for Multi-Hop Question Answering"
- GraphRAG: Edge et al., 2024 (Microsoft) — community-based summarization
- Our eval: `eval/experiment_log.jsonl`
