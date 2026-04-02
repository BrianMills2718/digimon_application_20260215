# Continuous Execution: Diagnostic Infrastructure + Failure Iteration

**Mission:** Build oracle diagnostic infrastructure for DIGIMON benchmark failure analysis, then use it to drive the iteration loop on failing MuSiQue questions.
**Started:** 2026-04-01 19:10 PDT
**NEVER STOP until all phases complete or a real blocker appears.**

## Acceptance Criteria
- Oracle diagnostic runs on all 15 failing questions from latest benchmark
- Each failure classified into taxonomy with fix recommendation
- Sentinel set defined and runnable
- At least one failure family fixed and verified
- All changes committed

## Phase 1: Build oracle_diagnostic.py (~3h)
- [ ] 1.1: Chunk text search — find gold answer substrings in raw chunks
- [ ] 1.2: VDB search — embed question, check if top-k chunks contain answer
- [ ] 1.3: Graph reachability — find gold entities in graph, compute shortest path
- [ ] 1.4: Optimal strategy determination — simplest tool that would work
- [ ] 1.5: Trace comparison — load actual agent trace, compare to optimal
- [ ] 1.6: Auto-classification into taxonomy (8 families + OTHER)
- [ ] 1.7: Markdown report generation
- [ ] 1.8: Integration with Makefile (make diagnose)

## Phase 2: Build sentinel set (~30min)
- [ ] 2.1: Identify currently-passing questions from latest run
- [ ] 2.2: Create sentinel_set.txt
- [ ] 2.3: Add make sentinel target

## Phase 3: Run diagnostics on current failures (~30min)
- [ ] 3.1: Run oracle on all 15 failing questions
- [ ] 3.2: Group by failure family
- [ ] 3.3: Write diagnostic report to investigations/

## Phase 4: Fix highest-yield failure family (~2-4h)
- [ ] 4.1: Implement fix for the largest family
- [ ] 4.2: Run sentinel (regression check)
- [ ] 4.3: Rerun failing questions from that family
- [ ] 4.4: Commit if improved, iterate if not

## Phase 5: Second iteration cycle (~2-4h)
- [ ] 5.1: Re-diagnose remaining failures
- [ ] 5.2: Fix next family
- [ ] 5.3: Sentinel + rerun
- [ ] 5.4: Commit

## Failure Taxonomy
1. TOOL_SELECTION — answer findable by simpler tool, agent used complex one
2. QUERY_FORMULATION — right tool, wrong query
3. EXTRACTION_GAP — answer not in chunks or graph (data missing)
4. GRAPH_REPRESENTATION — answer needs graph but graph lacks entity/edge
5. RETRIEVAL_RANKING — right tool+query, answer in results but ranked too low
6. ANSWER_SYNTHESIS — agent found answer but extracted wrong fact
7. CONTROL_FLOW — atom lifecycle, early stopping, stagnation
8. OTHER — doesn't fit above categories (capture details for new taxonomy entries)
