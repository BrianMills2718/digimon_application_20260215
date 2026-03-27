# Plan #3: Prove Adaptive Operator Routing

**Status:** Blocked — paused pending Plan #17 strategic pivot results
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
2. **One reproducible core slice** — fresh documented env, imports work, benchmark runs
3. **One benchmark report** — 200q balanced sample on MuSiQue, comparing:
   - (A) Non-graph baseline: chunk retrieval + rerank + answer synthesis
   - (B) Fixed graph pipeline: entity search → one-hop → chunk → answer
   - (C) Adaptive DIGIMON router: agent composes operators per question
4. **One go/no-go memo** — apply the Decision Gate below using only the locked evaluation split.

Development methodology:
- Tune in small 10-20 question batches.
- Use those batch runs for failure analysis and iteration only.
- Do not use tuned-on batch scores as final benchmark evidence.
- After gains flatten, freeze prompts/tools/policies and run the locked evaluation split.

Definitions:
- `A` = non-graph baseline
- `B*` = best locked fixed-graph pipeline chosen during dev tuning before the locked evaluation run
- `C` = adaptive DIGIMON router

---

## Milestones

### M1: Repo Cleanup (March 19-20) — COMPLETED

Make the repo surface match reality. No new features.

**Done (March 17-18):**
- [x] Delete dead entry points, orchestrator variants, React UI, deploy/
- [x] Untrack generated data (node_modules, results, storage, cache)
- [x] Rewrite CLAUDE.md operators-first
- [x] Clean method references from 8 docs files
- [x] Delete Core/Methods/, OperatorComposer, auto_compose

**Completed after follow-up cleanup:**
- [x] Fix README.md — remove references to deleted files, reflect actual usage
- [x] Archive dead docs: README_SOCIAL_MEDIA_ANALYSIS.md, AGENT_INTELLIGENCE_ENHANCEMENTS.md
- [x] Deduplicate pytest config (remove duplication between pytest.ini and setup.cfg)
- [x] Fix FUNCTIONALITY.md to match current state
- [x] Add `docs/ACTIVE_DOCS.md` to define the canonical doc set
- [x] Define `core` / `experimental` / `historical` repo lanes and test lanes
- [x] Lazy-load `Core.MCP.DigimonToolServer` so core imports do not drag legacy MCP runtime dependencies into the default path
- [x] Make social-media tools opt-in in the default registry path
- [x] Remove hardcoded eval interpreter and repo paths from the maintained benchmark lane
- [x] Align the documented setup contract: `requirements.txt` covers the core lane, `requirements-dev.txt` covers broader test/dev tooling

**Still useful but not milestone-blocking:**
- [ ] Update ISSUES.md with concrete problems found during cleanup

**Acceptance:** `grep -r 'main.py\|api.py\|digimon_cli' README.md FUNCTIONALITY.md` returns nothing.

### M2: Tool Result Compactness (March 21-22) — COMPLETED

Reduce context window waste. Research shows JSON costs 2x tokens vs text.

- [x] Switch `chunk_text_search` to compact text format (key fields only, not full JSON)
- [x] Make chunk count a parameter (top_k with default, not hardcoded 10)
- [x] Switch `entity_neighborhood` to compact text format
- [x] Benchmark token usage before/after on 5 representative questions

**Acceptance:** Average tool result size drops by ≥40%. No accuracy regression on 5q sample.

### M3: Non-Graph Baseline (March 23-24) — COMPLETED

Build the simplest competitive baseline to test against.

- [x] Implement baseline: chunk_text_search + chunk_vdb_search + meta.generate_answer (no graph traversal)
- [x] Wire into run_agent_benchmark.py as a `--mode baseline` option
- [x] Run on 50q MuSiQue sample
- [x] Record EM, F1, LLM_EM, cost, latency

**Acceptance:** Baseline runs end-to-end and produces scored results.

Batch workflow:
- Use `docs/plans/BATCH_ITERATION_TEMPLATE.md` for each 10-20 question dev batch.
- Start with `docs/plans/batch_01_musique_dev.md`.
- If rerunning the same IDs after targeted changes, create a rerun record such as `docs/plans/batch_01_musique_dev_rerun_a.md`.

### M4: Fixed Graph Pipeline (March 25-26) — COMPLETED

Lock the best non-adaptive graph pipeline for comparison.

- [x] Implement fixed pipeline: entity_string_search → entity_neighborhood → chunk_get_text → generate_answer
- [x] Wire as `--mode fixed_graph` option
- [x] Run on same 50q MuSiQue sample
- [x] Record EM, F1, LLM_EM, cost, latency

**Acceptance:** Fixed pipeline runs end-to-end with no agent reasoning (deterministic), and the best fixed graph pipeline is locked before the 200q evaluation.

### M5: Benchmark Comparison (March 27-29) — PARTIALLY DONE

Run all three approaches on a development comparison first, then a locked evaluation split if the thesis still looks worth pursuing.

- [x] Select 50q balanced MuSiQue development sample (seed=42)
- [x] Run baseline (A), fixed graph (B), adaptive router (C) on same split
- [x] Run with same answer model (`gemini-2.5-flash`) and judge (`deepseek-chat`)
- [x] Produce comparison table with EM, LLM_EM, cost/q, tools/q
- [ ] Run locked 200q evaluation only if post-dev evidence justifies it
- [ ] Break down locked-eval results by hop count if the locked run happens

**Development results (March 18, 2026):**

| Mode | EM | LLM_EM | Run Cost | Tools/q |
|------|----|--------|----------|---------|
| A: baseline | 34.0% | 60.0% | $2.03 | 10.8 |
| B: fixed_graph | 32.0% | 54.0% | $1.85 | 8.7 |
| C: hybrid | 32.0% | 44.0% | $5.50 | 11.7 |

Current evidence does **not** support the adaptive-routing thesis on this model/sample.

**Acceptance:** Development comparison is complete. Locked evaluation remains optional and should only happen if confounders are addressed and the thesis still appears viable.

Evaluation rule:
- The 200q run must be on a locked split that was not used for iterative tuning.
- If all tuning was done on the same questions, the result is a dev score, not decision-grade evidence.
- Follow `docs/plans/LOCKED_EVAL_PROTOCOL.md` for split locking, overlap checks, and run procedure.

### M6: Go/No-Go Memo (March 30-April 1)

- [ ] Write decision memo with benchmark evidence
- [ ] Apply Gate 1 using the locked evaluation split only
- [ ] Apply Gate 2 using the locked evaluation split only
- [ ] If `B*` fails Gate 1: stop graph-specific investment
- [ ] If `B*` passes Gate 1 but `C` fails Gate 2: keep graph work, stop adaptive-thesis work
- [ ] If both gates pass: continue with graph + adaptive routing
- [ ] If results are close but below threshold: classify as inconclusive, not a win
- [ ] Identify top 3 next-phase improvements only if the relevant gate passes
- [ ] If a gate fails: identify what to replace, what to keep, and what to stop building

**Acceptance:** Memo exists with clear recommendation backed by data. If no locked evaluation is run, the memo must explicitly classify the current result as dev evidence and may recommend an early stop on the adaptive thesis.

Decision Gate:

- **Preconditions**
  - All three modes (`baseline`, `fixed_graph`, `adaptive`) run on the same locked question IDs.
  - Same answer model, same judge model, same timeout policy, same retry policy, and same scorer.
  - Completion rate for a mode must be at least 95% to be decision-grade.
  - If the final evaluation is run more than once, report the mean score across runs.

- **Gate 1: Graph Value**
  - Continue graph-specific investment only if `B*` beats `A` by at least one of:
  - `+2.0 EM`
  - `+3.0 LLM_EM`
  - If `B*` fails Gate 1, stop investing in custom graph infrastructure.

- **Gate 2: Adaptive Value**
  - Continue adaptive-routing investment only if `C` beats `B*` by at least one of:
  - `+3.0 EM`
  - `+5.0 LLM_EM`
  - If `C` fails Gate 2, stop investing in adaptive routing as the primary thesis.

- **Guardrails**
  - A mode does not count as a win if it clears a score gate but completion rate drops by more than 2 percentage points versus the comparison mode.
  - A mode does not count as a win if cost per question exceeds 1.5x the comparison mode without a clear quality win.
  - A mode does not count as a win if latency per question exceeds 1.5x the comparison mode without a clear quality win.

- **Outcome Rules**
  - If `B*` fails Gate 1: stop graph investment.
  - If `B*` passes Gate 1 but `C` fails Gate 2: keep graph work, stop adaptive-thesis work.
  - If both gates pass: continue with graph + adaptive routing.
  - If results are within the margin but below the gate: classify as inconclusive, not a win.

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

- The review agent recommended replacing NetworkX with Neo4j. Defer that question until after the thesis decision. The current bottleneck is retrieval quality and evaluation truthfulness, not storage migration.
- The review agent's "keep/cut/replace/prove" framework is correct. This plan follows it.
- March 17-18 infrastructure fixes already addressed many review agent concerns. The remaining work is a truthful stop/continue decision.
