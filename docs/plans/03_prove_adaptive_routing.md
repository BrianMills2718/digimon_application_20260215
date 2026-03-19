# Plan #3: Prove Adaptive Operator Routing

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** All future DIGIMON investment decisions
**Deadline:** April 1, 2026

---

## Gap

**Current:** DIGIMON has 28 composable operators and an agent-driven composition system that scored 52% EM / 80% LLM_EM on 50q MuSiQue (pre-cleanup). After infrastructure fixes on March 17-18, previously-failing questions went from 0/16 → 9/16 passing. But we have no comparison against simpler baselines, and the "adaptive routing beats fixed pipelines" thesis is untested.

**Target:** One reproducible benchmark comparing simple baseline vs graph pipeline vs adaptive router on a fixed dataset, with a go/no-go decision.

**Why:** The review agent correctly identified that DIGIMON is an ambitious research sandbox, not yet a proven product. We need to answer: "Does adaptive graph-assisted retrieval beat simpler approaches enough to justify this complexity?" If yes, continue. If no, stop building custom graph infrastructure.

---

## Thesis

**Adaptive operator-routing over graph retrieval — selecting retrieval strategies per question rather than forcing one fixed pipeline — outperforms the best single pipeline on heterogeneous multi-hop QA.**

---

## References Reviewed

- External review agent assessment (March 18, 2026)
- `docs/COMPETITIVE_ANALYSIS.md` — SOTA comparison, benchmark strategy
- `docs/SYSTEM_OVERVIEW.md` — architecture overview
- `eval/run_agent_benchmark.py` — existing benchmark harness
- `prompts/agent_benchmark_hybrid.yaml` — current agent prompt
- March 17-18 failure analysis: 14 infrastructure fixes, 0/16→9/16 on hard questions
- SOTA research: HippoRAG 2, EcphoryRAG, LEGO-GraphRAG
- `~/projects/project-meta/research_texts/tool_Calling_optimization_guide.txt`
- `~/projects/project-meta/research_texts/mcp_best_practices.md`

---

## Acceptance Criteria (Go/No-Go Gate)

By April 1, 2026, deliver:

1. **One truthful README** — reflects actual repo state (no references to deleted files)
2. **One reproducible core slice** — fresh conda env, imports work, benchmark runs
3. **One benchmark report** — 200q balanced sample on MuSiQue, comparing:
   - (A) Non-graph baseline: chunk retrieval + rerank + answer synthesis
   - (B) Fixed graph pipeline: entity search → one-hop → chunk → answer
   - (C) Adaptive DIGIMON router: agent composes operators per question
4. **One go/no-go memo** — if (C) beats (B) by ≥3 EM or ≥5 LLM_EM, continue. Otherwise stop.

---

## Milestones

### M1: Repo Cleanup (March 19-20) — PARTIALLY DONE

Make the repo surface match reality. No new features.

**Done (March 17-18):**
- [x] Delete dead entry points, orchestrator variants, React UI, deploy/
- [x] Untrack generated data (node_modules, results, storage, cache)
- [x] Rewrite CLAUDE.md operators-first
- [x] Clean method references from 8 docs files
- [x] Delete Core/Methods/, OperatorComposer, auto_compose

**Remaining:**
- [ ] Fix README.md — remove references to deleted files, reflect actual usage
- [ ] Archive dead docs: README_SOCIAL_MEDIA_ANALYSIS.md, AGENT_INTELLIGENCE_ENHANCEMENTS.md
- [ ] Deduplicate pytest config (remove duplication between pytest.ini and setup.cfg)
- [ ] Update ISSUES.md with concrete problems found during cleanup
- [ ] Fix FUNCTIONALITY.md to match current state

**Acceptance:** `grep -r 'main.py\|api.py\|digimon_cli' README.md FUNCTIONALITY.md` returns nothing.

### M2: Tool Result Compactness (March 21-22)

Reduce context window waste. Research shows JSON costs 2x tokens vs text.

- [ ] Switch `chunk_text_search` to compact text format (key fields only, not full JSON)
- [ ] Make chunk count a parameter (top_k with default, not hardcoded 10)
- [ ] Switch `entity_neighborhood` to compact text format
- [ ] Benchmark token usage before/after on 5 representative questions

**Acceptance:** Average tool result size drops by ≥40%. No accuracy regression on 5q sample.

### M3: Non-Graph Baseline (March 23-24)

Build the simplest competitive baseline to test against.

- [ ] Implement baseline: chunk_text_search + chunk_vdb_search + meta.generate_answer (no graph traversal)
- [ ] Wire into run_agent_benchmark.py as a `--mode baseline` option
- [ ] Run on 50q MuSiQue sample (same questions as existing benchmarks)
- [ ] Record EM, F1, LLM_EM, cost, latency

**Acceptance:** Baseline runs end-to-end and produces scored results.

### M4: Fixed Graph Pipeline (March 25-26)

One non-adaptive graph pipeline for comparison.

- [ ] Implement fixed pipeline: entity_string_search → entity_neighborhood → chunk_get_text → generate_answer
- [ ] Wire as `--mode fixed_graph` option
- [ ] Run on same 50q MuSiQue sample
- [ ] Record EM, F1, LLM_EM, cost, latency

**Acceptance:** Fixed pipeline runs end-to-end with no agent reasoning (deterministic).

### M5: Full Benchmark (March 27-29)

Run all three approaches on 200q balanced sample.

- [ ] Select 200q balanced sample from MuSiQue (proportional 2/3/4-hop)
- [ ] Run baseline (A), fixed graph (B), adaptive router (C) on same split
- [ ] Run with same model (gemini-2.5-flash) and judge (deepseek-chat)
- [ ] Produce comparison table: EM, F1, LLM_EM, cost/q, latency/q, tools/q
- [ ] Break down by hop count (2-hop, 3-hop, 4-hop)

**Acceptance:** All 3 approaches complete 200q with ≥95% completion rate.

### M6: Go/No-Go Memo (March 30-April 1)

- [ ] Write decision memo with benchmark evidence
- [ ] If adaptive (C) beats fixed graph (B) by ≥3 EM or ≥5 LLM_EM: CONTINUE
- [ ] If graph (B) doesn't beat non-graph (A) materially: STOP graph investment
- [ ] If adaptive wins: identify top 3 improvements for next phase
- [ ] If adaptive loses: identify what to replace and what to keep

**Acceptance:** Memo exists with clear recommendation backed by data.

---

## What NOT To Spend Time On

- Full-repo mypy cleanup (only the core slice)
- More planning docs beyond this plan
- Agent memory/intelligence layers
- Storage rewrite (Neo4j, etc.) — only after benchmark proof
- Social media demo
- New graph types
- More orchestrator variants
- Cross-modal tools

---

## Files Affected

- `README.md` (rewrite)
- `FUNCTIONALITY.md` (rewrite)
- `docs/README_SOCIAL_MEDIA_ANALYSIS.md` (archive)
- `docs/AGENT_INTELLIGENCE_ENHANCEMENTS.md` (archive)
- `ISSUES.md` (update)
- `digimon_mcp_stdio_server.py` (compact tool results)
- `eval/run_agent_benchmark.py` (add baseline/fixed_graph modes)
- `prompts/` (baseline prompt)

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Rate limiting blocks 200q run | High | Delays M5 | Use direct Gemini API, batch with delays |
| Non-graph baseline beats graph | Medium | Kills thesis | Honest result — better to know now |
| Stochastic variation masks real differences | High | False conclusions | Run each approach 2x, report variance |
| Graph rebuild needed for smaller chunks | Low | Delays M5 | Use existing graph, note as limitation |

---

## Notes

- The review agent recommended replacing NetworkX with Neo4j. Disagree for now — the bottleneck is information presentation, not storage. entity_neighborhood proved this.
- The review agent's "keep/cut/replace/prove" framework is correct. This plan follows it.
- March 17-18 infrastructure fixes (14 commits) already addressed many review agent concerns. The remaining work is benchmark proof.
