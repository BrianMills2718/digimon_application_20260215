# Continuous Execution: Diagnostic Infrastructure + Failure Iteration

**Mission:** Build oracle diagnostic infrastructure for DIGIMON benchmark failure analysis, then use it to drive the iteration loop on failing MuSiQue questions.
**Started:** 2026-04-01 19:10 PDT

## Phase 1: Oracle Diagnostic — DONE
- [x] Chunk text search, graph reachability, trace analysis
- [x] LLM-verified classification with conversation trace context
- [x] Markdown + JSON report generation
- [x] Makefile: `make oracle` (LLM) + `make oracle-fast` (heuristic)

## Phase 2: Sentinel Set — DONE
- [x] eval/fixtures/sentinel_set.txt (2 passing questions)
- [x] `make sentinel` target

## Phase 3: Initial Diagnosis — DONE
Results on 17 failing questions:
- QUERY_FORMULATION: 9 (agent queries too broad)
- INTERMEDIATE_ENTITY_ERROR: 6 (wrong intermediate entity cascades)
- CONTROL_FLOW: 1 (harness rejected valid submission)
- RETRIEVAL_RANKING: 1

## Phase 4: Fix Attempt 1 — IN PROGRESS
- [x] Prompt improvement: added intermediate entity verification (steps 3c, 3e, 3i)
- [x] Sentinel run: 1/2 pass (regression is stochastic, not prompt-caused)
- [ ] Full 19q rerun in progress
- [ ] Oracle re-diagnosis pending

## Phase 5: Next iteration — PENDING
Waiting for Phase 4 results.

## Failure Taxonomy
1. TOOL_SELECTION — answer findable by simpler tool
2. QUERY_FORMULATION — right tool, wrong query
3. EXTRACTION_GAP — answer not in corpus
4. GRAPH_REPRESENTATION — graph lacks needed entity/edge
5. RETRIEVAL_RANKING — answer in results but ranked too low
6. ANSWER_SYNTHESIS — found answer, picked wrong fact
7. CONTROL_FLOW — atom lifecycle, submit rejection
8. INTERMEDIATE_ENTITY_ERROR — wrong entity at intermediate hop
9. OTHER — uncategorized
