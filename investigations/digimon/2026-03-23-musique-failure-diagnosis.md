# MuSiQue Failure Diagnosis — Consolidated Tools + PPR Fix

**Date**: 2026-03-23
**Status**: In progress
**Run**: MuSiQue 19q, gpt-5.4-mini, consolidated tools, PPR damping=0.5
**Results**: 7/19 pass (36.8% LLM-judge), 12/19 fail

## Methodology

1. Run baseline (no graph, same model) on same 19 questions
2. Cross-reference: find questions where BOTH baseline and GraphRAG fail
3. Diagnose those overlap failures — these are where GraphRAG *should* add value
4. Fix systemic issues, re-run only the failing questions
5. Show that GraphRAG can answer questions baseline can't

## Systemic Issues Identified

### Issue 1: Agent never decomposes multi-hop questions

**Evidence**: 0/19 questions used `reason(method="decompose")`. All 3-4 hop questions failed. The `reason` tool description says "decompose: Call FIRST for complex questions" but the agent ignores this.

**Impact**: StepChain ablation shows decomposition alone adds +15 EM. This is the single biggest lever.

**Diagnosis**: The benchmark prompt (`prompts/agent_benchmark_hybrid.yaml`) may not explicitly instruct the agent to decompose complex questions. Or the instruction is buried among other guidance and the agent doesn't prioritize it.

**Proposed fix**: Either (a) update the benchmark prompt to explicitly instruct "For questions with 3+ reasoning hops, FIRST call reason(method='decompose')" or (b) add a pre-processing step in the benchmark runner that auto-decomposes.

### Issue 2: Agent often skips chunk retrieval

**Evidence**: 4/12 failures never called `chunk_retrieve`. The agent answered from entity metadata (names, types, descriptions) without fetching source text. Entity metadata is a summary — the ground truth is in the chunks.

**Impact**: Answering without evidence is guessing. Chunk retrieval grounds the answer in source text.

**Diagnosis**: The agent may think entity_info provides enough information, or it doesn't understand that chunk_retrieve gives the actual source passages.

**Proposed fix**: Update `entity_info` tool description to explicitly say "Returns summary only — for definitive answers, use chunk_retrieve to get source text." Update `chunk_retrieve` description to emphasize it as the grounding step.

### Issue 3: Multi-hop chain breaks at entity resolution

**Evidence**: Questions like "What is the birthplace of the person after whom São José dos Campos was named?" require resolving "the person" → "Saint Joseph" → birthplace = "Nazareth". The agent predicted "Saint Joseph of the Fields" — it found the city but couldn't resolve the person behind the naming.

**Impact**: This is the core multi-hop challenge. Each hop requires entity disambiguation.

**Diagnosis**: The agent doesn't use `entity_traverse(method="ppr")` to spread activation through the graph. PPR should help here — start from "São José dos Campos", spread to connected entities, find "Saint Joseph", then spread to "Nazareth".

**Proposed fix**: This may improve naturally once Issues 1 and 2 are fixed (decompose the question, then use PPR per sub-question).

## Per-Question Analysis

| ID | Hops | LLM | GraphRAG Pred | Gold | Failure Type |
|----|------|-----|---------------|------|-------------|
| 3hop1__9285 | 3 | FAIL | May | mid-June | Wrong date, no decomposition |
| 2hop__766973 | 2 | FAIL | Monroe County | Rockland County | Wrong entity, graph has wrong data? |
| 2hop__170823 | 2 | FAIL | 1981 | 1986 | No chunk_retrieve, wrong year |
| 2hop__511454 | 2 | FAIL | 1974 | 918 | Off by 1000 years — answered modern date |
| 4hop2__71753 | 4 | FAIL | Lebanon | 1930 | Wrong answer type (country vs year) |
| 4hop1__94201 | 4 | FAIL | georgia state university library | Mississippi River Delta | Complete miss — wrong entity chain |
| 4hop1__152562 | 4 | FAIL | September 2, 2009 | August 3, 1769 | Off by 240 years |
| 3hop1__305282 | 3 | FAIL | 1485 | December 14, 1814 | Wrong battle, no decomposition |
| 4hop3__754156 | 4 | FAIL | Brunei | dynasty defeated Portuguese | Wrong answer type |
| 2hop__199513 | 2 | FAIL | Saint Joseph of the Fields | Nazareth | Chain broke at entity resolution |
| 3hop1__136129 | 3 | FAIL | 1305 | 1952 | Wrong century |
| 3hop1__849312 | 3 | FAIL | unknown | built in the 15th century | Gave up — retrieval stagnation |

## Baseline comparison (pending)

Baseline run on same 19 questions in progress. Will cross-reference when complete.
