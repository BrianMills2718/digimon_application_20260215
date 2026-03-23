# Plan #16: HippoRAG-Aligned Build Attributes

**Status:** Planned
**Type:** implementation
**Priority:** High
**Blocked By:** None (can proceed in parallel with Plan #14-#15, but verification needs Plan #14)
**Blocks:** Plan #17

---

## Gap

**Current:** DIGIMON's ERGraph is entity-only (like HippoRAG v1). Missing: passage-level nodes (HippoRAG v2), tunable PPR damping (default unknown), IDF-weighted entity scoring (operator exists but not integrated), question decomposition in benchmark pipeline (operators exist but not wired).

**Target:** Four SOTA-aligned innovations as configurable build/retrieval attributes. Build agent selects per task; not hardcoded.

**Why:** Literature review shows these are the innovations separating SOTA (58% EM) from basic graph approaches. DIGIMON has the operator primitives but hasn't connected them. This is about configuration and wiring, not new algorithms.

---

## References Reviewed

- Literature review (`investigations/digimon/2026-03-23-graphrag-sota-review.md`)
- HippoRAG 1: PPR damping = 0.5, entity-only graph, PPR is most critical component
- HippoRAG 2: Added passage nodes (bipartite), MuSiQue Recall@5: 69.7→74.7
- PropRAG: PPR damping = 0.75, proposition-level graph, LLM-free beam search
- StepChain: Question decomposition alone = +15 EM (ablation)
- EcphoryRAG: Co-occurrence edges only, no relationship extraction, 72.2% EM on HotpotQA
- `Core/Graph/ERGraph.py` — current graph building
- `Config/GraphConfig.py` — current config options
- `Core/Operators/entity/ppr.py` — current PPR implementation
- `Core/Operators/meta/decompose_question.py`, `synthesize_answers.py` — exist but not in benchmark pipeline
- `prompts/agent_benchmark_hybrid.yaml` — current benchmark prompt

---

## Files Affected

- `Config/GraphConfig.py` (modify — add new config flags)
- `Core/Graph/ERGraph.py` (modify — passage node support)
- `Core/Operators/entity/ppr.py` (modify — configurable damping factor)
- `prompts/agent_benchmark_hybrid.yaml` (modify — integrate decomposition)
- `eval/run_agent_benchmark.py` (modify — decomposition pipeline option)
- `tests/test_build_attributes.py` (create)

---

## Plan

### Pre-made decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Passage nodes implementation | Add passage node type to ERGraph alongside entity nodes; link entities to source passages via co-occurrence | Matches HippoRAG v2; reuses existing chunk tracking |
| PPR damping default | 0.5 (HippoRAG default) | Conservative; tunable at runtime |
| Decomposition integration | Add `--decompose` flag to benchmark runner | Opt-in; doesn't change existing benchmark behavior |
| Co-occurrence-only mode | Add `skip_relationship_extraction` config flag | Tests EcphoryRAG hypothesis: are relationships even necessary? |

### Steps (ordered by independence, not priority)

**Step 1: PPR damping factor** (smallest, most isolated)
1. Add `ppr_damping_factor: float = 0.5` to GraphConfig
2. Pass through to `entity.ppr` operator
3. Verify current NetworkX PPR call accepts damping parameter
4. Test: build graph, run PPR with 0.5 and 0.85, confirm different ranking

**Step 2: Question decomposition in benchmark pipeline**
1. Add `--decompose` flag to `eval/run_agent_benchmark.py`
2. When enabled: decompose question → run sub-questions independently → synthesize
3. Uses existing `meta.decompose_question` + `meta.synthesize_answers` operators
4. Test: run HotpotQAsmallest 3q with/without decomposition, compare EM

**Step 3: Passage-level nodes** (largest change)
1. Add `enable_passage_nodes: bool = False` to GraphConfig
2. When enabled during graph build: create a node for each chunk/passage
3. Add edges from entities to the passages they were extracted from
4. Ensure entity.ppr spreads activation through passage nodes (bipartite PPR)
5. Test: build small graph with passage nodes, verify node count includes passages, verify PPR returns passage-connected entities

**Step 4: Co-occurrence-only build mode**
1. Add `skip_relationship_extraction: bool = False` to GraphConfig
2. When enabled: extract entities only (NER), skip OpenIE/relationship extraction
3. Build graph with entities + `augment_chunk_cooccurrence` edges only
4. Test: build graph, verify no relationship edges, verify entity retrieval still works

### Error taxonomy

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| PPR damping has no effect | NetworkX API may use different parameter name | Check `nx.pagerank` docs for `alpha` parameter |
| Passage nodes break VDB indexing | VDB expects entity nodes only | Filter node types when building entity VDB |
| Decomposition produces garbage sub-questions | LLM prompt for decomposition is weak | Improve decompose_question prompt (existing prompt, not new) |
| Co-occurrence-only graph has zero edges | `augment_chunk_cooccurrence` not running | Verify enrichment step runs after entity extraction |

### Backtracking ladder

1. Each step is independent — if one fails, others can proceed
2. If passage nodes break graph structure: revert to entity-only, investigate separately
3. If decomposition hurts performance: make it conditional on question hop-count (2-hop skip, 4-hop use)
4. After 3 attempts on any step → escalate with specific error

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/test_build_attributes.py` | `test_ppr_damping_configurable` | PPR with 0.5 vs 0.85 produces different rankings |
| `tests/test_build_attributes.py` | `test_passage_nodes_created` | Graph with `enable_passage_nodes=True` has passage-type nodes |
| `tests/test_build_attributes.py` | `test_passage_nodes_ppr_spread` | PPR spreads through passage nodes to reach non-adjacent entities |
| `tests/test_build_attributes.py` | `test_cooccurrence_only_build` | `skip_relationship_extraction=True` produces entity+cooccurrence graph |
| `tests/test_build_attributes.py` | `test_decompose_synthesize_pipeline` | Decomposition produces sub-questions; synthesis combines sub-answers |

---

## Acceptance Criteria

- [ ] `ppr_damping_factor` configurable in GraphConfig, passed to PPR operator
- [ ] `--decompose` flag in benchmark runner wires decompose→sub-retrieve→synthesize
- [ ] `enable_passage_nodes` adds passage nodes and entity-passage edges to graph
- [ ] `skip_relationship_extraction` builds entity+cooccurrence graph without relationship LLM calls
- [ ] All new config flags default to current behavior (backward compatible)
- [ ] Each attribute independently testable with unit tests

---

## Budget

- Step 1 (PPR tuning): $0 (no LLM calls)
- Step 2 (decomposition): ~$0.50 (3q test with decomposition)
- Step 3 (passage nodes): ~$3-5 (one small graph rebuild)
- Step 4 (co-occurrence only): ~$1-2 (entity-only extraction, cheaper than full build)
- **Total: ~$5-8**

---

## Notes

All attributes are CONFIGURABLE, not hardcoded. The build agent selects per task:
- Multi-hop QA benchmark → passage nodes ON, PPR damping 0.5, decomposition ON
- Discourse analysis → passage nodes OFF, relationships ON, decomposition OFF
- Budget-constrained → co-occurrence only, skip relationship extraction
