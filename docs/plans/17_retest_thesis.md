# Plan #17: Re-Test Thesis with Clean Architecture

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** Plan #14 ✅, Plan #15 ✅, Plan #16 ✅ — all prerequisites met
**Blocks:** Plan #18 (conditional)

---

## Gap

**Current:** Preliminary 19q evidence shows GraphRAG with consolidated tools beating baseline 52.6% vs 21.1% LLM-judge, with 7 "graph wins" questions. But the graph was built before our improvements — no passage nodes, PPR damping was 0.1, no synonym edges. A graph rebuild with SOTA-aligned attributes should improve further.

**Target:** Rebuild graph with all SOTA innovations, then run failure-focused iteration on questions where baseline fails. Primary metric: LLM-judge. Show that GraphRAG solves questions that simpler methods can't.

**Why:** This is the thesis test. Plans #14-#16 built the infrastructure; this plan produces the evidence.

---

## References Reviewed

- Literature review (`~/projects/investigations/digimon/2026-03-23-graphrag-sota-review.md`)
- Preliminary 19q results (2026-03-23): baseline 21.1%, GraphRAG consolidated 52.6% LLM-judge
- Failure diagnosis (`investigations/digimon/2026-03-23-musique-failure-diagnosis.md`)
- HippoRAG v2: passage nodes improved MuSiQue Recall@5 from 69.7→74.7%
- Vectara chunking benchmark: 1200 tokens is fine for multi-hop (StepChain uses same)
- DIGIMON already has: synonym detection, centrality augmentation, co-occurrence edges, node specificity
- Planning notebook: `notebooks/plan17_thesis_retest.ipynb` (phase contracts, diagnostic protocol, cross-reference framework)
- Pre-analysis of both-fail questions: `investigations/digimon/2026-03-23-both-fail-pre-analysis.md`

---

## Pre-made Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph rebuild dataset | MuSiQue (same corpus as existing graph) | Apples-to-apples comparison |
| Build config | `enable_passage_nodes=True`, `enable_chunk_cooccurrence=True`, `schema_mode=open` | All SOTA innovations, see build config below |
| Post-build enrichment | Synonym edges (threshold=0.85) + centrality | HippoRAG uses both; DIGIMON already has the code |
| Chunk size | Keep 1200 tokens, 100 overlap (current) | StepChain uses same; Vectara says 512 is better for retrieval but 1200 preserves more context per chunk for extraction |
| Extraction model | `gemini/gemini-2.5-flash` | Decision-grade extraction lane per existing policy |
| Routing/answer model | `openrouter/openai/gpt-5.4-mini` | Strong tool calling, 400K context |
| Question selection | Start with the 19q diagnostic set, then expand | Iterate on failures before scaling |
| Primary metric | LLM-judge (not EM) | Brian's explicit preference; EM is too sensitive to formatting |
| Comparison methodology | Focus on "graph wins" — questions where baseline fails but GraphRAG succeeds | Thesis is about where graphs add value, not aggregate average |
| Skip entity deduplication | Yes | Requires onto-canon, too large for this iteration |
| Skip proposition extraction | Yes | Different extraction paradigm, +2% marginal gain for large effort |

---

## Build Configuration

```yaml
# GraphConfig overrides for MuSiQue SOTA-aligned rebuild
graph:
  type: er_graph
  enable_entity_type: true
  enable_entity_description: true
  enable_edge_description: true
  enable_chunk_cooccurrence: true
  enable_passage_nodes: true          # NEW: HippoRAG v2 bipartite graph
  skip_relationship_extraction: false  # Keep relationships (not EcphoryRAG mode)
  schema_mode: open                    # Schema-free extraction

# RetrieverConfig
retriever:
  damping: 0.5                         # HippoRAG PPR damping (was 0.1)
  node_specificity: true               # IDF-weighted PPR seeding
  use_entity_similarity_for_ppr: false # HippoRAG-style (not FastGraphRAG)
  top_k: 10
```

### Post-build enrichment (run after graph build completes):
1. `augment_synonym_edges` — threshold=0.85, adds synonym edges between similar entity names
2. `augment_centrality` — PageRank centrality scores on all nodes

---

## Files Affected

| File | Change |
|------|--------|
| `Option/Config2.yaml` or config override | Set build flags for rebuild |
| `eval/run_agent_benchmark.py` | No changes — uses existing consolidated tools + prompt |
| `results/MuSiQue/er_graph/` | Rebuilt graph artifacts |
| `results/MuSiQue_gpt-5-4-mini_*.json` | New benchmark results |
| `investigations/digimon/2026-03-23-musique-failure-diagnosis.md` | Updated with post-rebuild analysis |

---

## Plan

### Phase 1: Graph Rebuild (~$3-5, ~30-60 min)

1. **Save current graph as backup**
   ```bash
   cp -r results/MuSiQue/er_graph results/MuSiQue/er_graph_pre_sota_backup
   ```

2. **Rebuild with SOTA config**
   - Set `enable_passage_nodes=True`, `enable_chunk_cooccurrence=True` in config
   - Run: `corpus_prepare → graph_build_er` on MuSiQue corpus
   - Verify: node count includes passage nodes, edge count includes co-occurrence + extracted_from edges

3. **Post-build enrichment**
   - Run `augment_synonym_edges` (threshold=0.85)
   - Run `augment_centrality`
   - Verify: synonym edges exist, centrality scores on nodes

4. **Rebuild VDB**
   - Run `entity_vdb_build` on new graph
   - Verify: VDB contains only entity nodes (passage nodes filtered)

5. **Smoke test**: 3q HotpotQAsmallest with rebuilt graph — confirm non-zero accuracy

### Phase 2: Failure-Focused Iteration (~$2-5)

6. **Run baseline on diagnostic question set** (already done: 19q, 21.1% LLM-judge)

7. **Run GraphRAG consolidated on same questions** with rebuilt graph
   - Use `--questions-file eval/fixtures/musique_19q_diagnostic_ids.txt`
   - Compare to pre-rebuild results (52.6% LLM-judge)

8. **Cross-reference**: Identify:
   - **Graph wins**: Baseline fails, GraphRAG succeeds (target: ≥7, ideally more)
   - **Both fail**: Diagnose — is the answer in the graph? Is retrieval finding it?
   - **Regressions**: Investigate — did the rebuild break something?

9. **For each "both fail" question**: Run the `/iterate-failures` diagnostic
   - Is the answer-critical entity in the graph?
   - Does entity_search find it?
   - Does entity_traverse(ppr) reach it?
   - Is the source passage retrievable via chunk_retrieve?
   - Where does the chain break?

10. **Fix systemic issues** found in step 9, re-run only failing questions

### Phase 3: Scale (only if Phase 2 succeeds) (~$10-15)

11. **Expand to 50q MuSiQue** (seed=42, same as March 18 comparison)
    - Run baseline + GraphRAG consolidated
    - Primary comparison: LLM-judge on baseline-failing questions

12. **Document results** in investigation artifact
    - Graph wins count, regression count, failure family taxonomy
    - Comparison to March 18 numbers and to SOTA literature

---

## Error Taxonomy

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| Graph rebuild fails | Config flag not recognized | Verify GraphConfig has `enable_passage_nodes` field |
| Passage nodes break VDB | VDB tries to embed passage node names | Check VDB filter in enhanced_entity_vdb_tools.py |
| PPR returns only passage nodes | Passage edge weight too high (0.3) | Lower passage edge weight or filter passage nodes from PPR output |
| Synonym edges create noise | Threshold too low, false synonyms | Raise threshold from 0.85 to 0.92 |
| Rebuilt graph worse than old | New edges dilute signal | Compare old vs new graph on same questions; may need to tune edge weights |
| Co-occurrence edges dominate | Too many, low quality | Weight co-occurrence edges lower (currently 0.5) |
| Build times out | MuSiQue corpus is large | Use checkpoint resumption (already implemented) |

### Backtracking Ladder

1. If rebuilt graph is worse on 19q: compare graph statistics (node/edge counts, avg degree) to identify what changed
2. If passage nodes hurt: disable them, keep other improvements, test again
3. If synonym edges hurt: raise threshold or disable
4. After 3 failed configurations → escalate with diagnostic data

---

## Acceptance Criteria

- [ ] Graph rebuilt with passage nodes, co-occurrence edges, synonym edges, centrality
- [ ] VDB rebuilt, contains only entity nodes
- [ ] 19q comparison: GraphRAG LLM-judge > baseline LLM-judge (21.1%)
- [ ] ≥5 "graph wins" questions (baseline fails, GraphRAG succeeds)
- [ ] ≤2 regressions (baseline succeeds, GraphRAG fails)
- [ ] Failure diagnosis completed for "both fail" questions
- [ ] Results documented in investigation artifact

---

## Phase 3b: Cross-Benchmark Validation (stretch goal)

Run 20q HotpotQA with the same consolidated tools and prompt to verify
results aren't MuSiQue-specific. The prompt says "most questions here
are 2-4 hops" which is MuSiQue-specific — HotpotQA is 2-hop only.

```bash
make bench DATASET=HotpotQAsmallest NUM=20
```

**Acceptance**: GraphRAG LLM-judge > baseline on HotpotQA too (any margin).
If it regresses on HotpotQA, the prompt needs to be less MuSiQue-specific.

## Gate Criteria (from ROADMAP.md, updated for LLM-judge)

- **H1 (graph value):** GraphRAG LLM-judge > baseline LLM-judge by ≥5% on the diagnostic question set
- **If H1 passes:** Scale to 50q, then iterate on new failures
- **If H1 fails after rebuild:** Graph architecture is the problem. Escalate.

---

## Budget

| Phase | Cost | Notes |
|-------|------|-------|
| Phase 1 (graph rebuild) | ~$3-5 | Extraction LLM calls on MuSiQue corpus |
| Phase 2 (19q iteration) | ~$2-5 | Multiple diagnostic runs on 19q |
| Phase 3 (50q scale) | ~$10-15 | Two 50q runs (baseline + GraphRAG) |
| **Total** | **~$15-25** | |

---

## Open Questions (per Pattern 29: Uncertainty Tracking)

### Q1: Are we testing adaptive routing or a good prompt?
**Status:** ⏸️ Deferred
**Raised:** 2026-03-23
**Context:** The consolidated prompt prescribes a pipeline (decompose → entity_search → PPR → chunk_retrieve). If the agent follows this, it's a fixed pipeline, not adaptive routing.
**Resolution:** Deferred — proving graph value is the first priority. Adaptive vs fixed is a second-order question. If graph value is confirmed, a follow-up test with a minimal prompt (just tool descriptions, no strategy guidance) can test true adaptive routing.
**Risk accepted:** Plan #17 answers "does the graph help?" not "does adaptive routing help?"

### Q2: MuSiQue overfitting risk
**Status:** 🔍 Investigating
**Raised:** 2026-03-23
**Context:** All development (19q diagnostic, prompt tuning, failure analysis) is on MuSiQue. Prompt contains MuSiQue-specific language.
**Mitigation:** After Plan #17, run at least 10q HotpotQA as cross-benchmark validation. Added as Phase 3 stretch goal.

### Q3: Cost asymmetry not tracked
**Status:** ❓ Open
**Raised:** 2026-03-23
**Context:** GraphRAG costs ~50x more per question than baseline. "Graph wins" count doesn't cost-adjust.
**Action needed:** Track cost-per-correct-answer alongside accuracy. Query observability DB before Phase 3.

### Q4: Small sample size (n=19)
**Status:** ⏸️ Deferred
**Raised:** 2026-03-23
**Context:** Single question flip = 5.3 percentage points. No statistical significance at n=19.
**Resolution:** Accept for development iteration. Plan #17 Phase 3 (50q) provides larger n. Phase 4 (200q/1000q) for publishable claims.
**Risk accepted:** Intermediate decisions made on noisy data.

### Q5: Model-dependent results
**Status:** ⏸️ Deferred
**Raised:** 2026-03-23
**Context:** Results depend on gpt-5.4-mini. Different routing models might produce different results.
**Resolution:** Spot-check with one other model after Plan #17. Not blocking.

### Q6: 7 operators not reachable via consolidated surface
**Status:** ⏸️ Deferred
**Raised:** 2026-03-23
**Context:** entity.agent, relationship.agent, subgraph.agent_path, chunk.aggregator, meta.rerank, meta.reason_step, entity.rel_node are excluded. See ADR-014 for rationale.
**Resolution:** Intentional exclusion. chunk.aggregator (HippoRAG score propagation) is the most likely to add value later. Revisit if Phase 2 diagnosis identifies score propagation as a missing capability.

### Q7: No plan beyond Plan #17
**Status:** ❓ Open
**Raised:** 2026-03-23
**Context:** No Plan #19 for 200q/1000q scale. No connection to Brian's broader causal-epistemic reasoning goal documented.
**Action needed:** Write at gate-time per ROADMAP policy. Connection to broader ecosystem should go in CLAUDE.md when pipeline crystallizes.

---

## Notes

**What changed since the placeholder:**
- Plans #14-#16 are complete — all prerequisites met
- Preliminary evidence is strong: 52.6% vs 21.1% LLM-judge (7 graph wins)
- Build configuration finalized based on literature review + DIGIMON capability audit
- Methodology shifted from aggregate comparison to failure-focused iteration
- Primary metric is LLM-judge, not EM

**What we're NOT doing (and why):**
- Entity deduplication (requires onto-canon, separate workstream)
- Proposition-level extraction (different paradigm, marginal +2% gain)
- Late chunking / contextual retrieval (requires re-chunking corpus)
- On-the-fly graph construction (pre-built is cheaper at scale)
- Fixed pipeline comparison (the consolidated prompt already guides decomposition; agent-driven is the thesis)
