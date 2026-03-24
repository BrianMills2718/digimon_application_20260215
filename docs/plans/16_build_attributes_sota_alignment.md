# Plan #16: HippoRAG-Aligned Build Attributes

**Status:** Complete (all 4 steps implemented)
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Plan #17

---

## Gap

**Current:** DIGIMON's ERGraph is entity-only (like HippoRAG v1). Missing: passage-level nodes (HippoRAG v2), IDF-weighted entity scoring, co-occurrence-only build mode. PPR damping fixed (Step 1). Decomposition available via consolidated prompt (Step 2).

**Target:** SOTA-aligned innovations as configurable build/retrieval attributes. Build agent selects per task; not hardcoded.

**Why:** Literature review shows these innovations separate SOTA (58% EM) from basic graph approaches. DIGIMON has operator primitives but hasn't connected them.

---

## References Reviewed

- Literature review (`~/projects/investigations/digimon/2026-03-23-graphrag-sota-review.md`)
- HippoRAG 1: PPR damping = 0.5, entity-only graph, PPR is most critical component
- HippoRAG 2: Added passage nodes (bipartite), MuSiQue Recall@5: 69.7→74.7
- PropRAG: PPR damping = 0.75, proposition-level graph, LLM-free beam search
- StepChain: Question decomposition alone = +15 EM (ablation)
- EcphoryRAG: Co-occurrence edges only, no relationship extraction, 72.2% EM on HotpotQA
- Code exploration (2026-03-23): ERGraph build flow, BaseGraph node model, chunk tracking, VDB indexing

---

## Status of Steps

### Step 1: PPR damping factor — COMPLETE ✅

**What was done:**
- `Config/RetrieverConfig.py:11` — `damping: float = 0.5` (was 0.1, also fixed duplicate fields)
- `Core/Operators/entity/ppr.py:63` — reads damping from config: `getattr(ctx.config, "damping", 0.5)`
- `Core/Graph/BaseGraph.py:843` — `personalized_pagerank` accepts `damping` parameter
- Committed: `cae4696`

**Deviation from plan:** Plan said add `ppr_damping_factor` to `GraphConfig`. Actually added as `damping` in `RetrieverConfig` (where it already existed at 0.1). RetrieverConfig is the correct location — it controls retrieval behavior, not graph structure.

### Step 2: Question decomposition — RESOLVED DIFFERENTLY ✅

**What was done:** Instead of adding a `--decompose` flag to the benchmark runner, decomposition is now available via the consolidated tool surface. The consolidated prompt (`prompts/agent_benchmark_consolidated.yaml`) explicitly instructs: "For multi-hop questions, call `reason(method='decompose')` FIRST."

**Evidence it works:** 5q diagnostic on previously-failing questions showed 3/5 pass (60% LLM-judge, up from 0%). All 5 questions used `reason` as their first tool call.

**Deviation from plan:** Plan said add `--decompose` flag for pipeline-level decomposition. The agent-driven approach (consolidated prompt guides decomposition) is more aligned with the adaptive-routing thesis — the agent decides when to decompose, not the pipeline.

### Step 3: Passage-level nodes — COMPLETE ✅

**What was done:**
- `Config/GraphConfig.py` — added `enable_passage_nodes: bool = False`
- `Core/Graph/BaseGraph.py` — passage node creation in `__graph__` after entity upsert; `GraphCapability.HAS_PASSAGES` flag
- `Core/AgentTools/enhanced_entity_vdb_tools.py` — filters `node_type="passage"` from VDB indexing
- Committed: `dede57d`

**Design:** Passage nodes named `passage_{chunk_key}`, linked to entities via `relation_name="extracted_from"` edges (weight=0.3). PPR spreads through passage nodes naturally (bipartite graph). VDB indexes entities only.

### Step 4: Co-occurrence-only build mode — COMPLETE ✅

**What was done:**
- `Config/GraphConfig.py` — added `skip_relationship_extraction: bool = False`
- `Core/Graph/ERGraph.py` — skips OpenIE when flag is True (two-step: triples=[]; single-step: filters relationship records)
- `Core/Graph/BaseGraph.py` — auto-enables co-occurrence edges when `skip_relationship_extraction=True`
- Committed: `32a9293`

---

## Plan for Step 3: Passage-Level Nodes

### Requirements

- When `enable_passage_nodes=True` in GraphConfig, the graph build adds a node for each source chunk/passage alongside entity nodes
- Entities link to their source passages via edges (entity → passage)
- PPR can spread activation through passage nodes (bipartite graph)
- Entity VDB indexes only entity nodes, not passage nodes
- Backward compatible: `enable_passage_nodes=False` (default) produces current behavior

### Contracts

**Input:** GraphConfig with `enable_passage_nodes: bool = False`
**Output:** Graph where:
- Entity nodes have `node_type="entity"` (or no node_type, for backward compat)
- Passage nodes have `node_type="passage"`, `chunk_id`, `text_preview`
- Edges: entity→passage where entity was extracted from that passage
- `GraphCapability.HAS_PASSAGES` set in capabilities

### Pre-made decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Node type field | Add `node_type` to node metadata dict, not Entity dataclass | Minimal change to existing code; Entity dataclass is used everywhere |
| Passage node naming | `passage_{chunk_key}` | Unique, distinguishable from entity names |
| Edge type | `relation_name="extracted_from"` | Semantic; distinguishes from co-occurrence edges |
| VDB filtering | Filter `node_type != "passage"` during VDB build | VDB indexes entities only; passage nodes are traversal targets |
| PPR behavior | No PPR code change needed | PPR spreads through all connected nodes naturally; seeds are still entity-only |
| Passage node content | `chunk_id` + first 200 chars of text as `description` | Enough for agent to see what the passage contains |

### Files Affected

| File | Change | Lines |
|------|--------|-------|
| `Config/GraphConfig.py` | Add `enable_passage_nodes: bool = False` | Near line 124 |
| `Core/Graph/BaseGraph.py` | Add passage node creation in `__graph__` method after entity upsert | After line 652 |
| `Core/Graph/BaseGraph.py` | Set `HAS_PASSAGES` capability flag | Lines 52-76 |
| `Core/Storage/NetworkXStorage.py` | No change — node_type stored as metadata naturally | — |
| Entity VDB build tool | Filter out `node_type="passage"` nodes | TBD (search for VDB node collection) |

### Error taxonomy

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| PPR indices misaligned | Passage nodes change total node count | PPR uses `ctx.graph.node_num` which auto-includes all nodes — should work |
| VDB indexes passage nodes | VDB build doesn't filter | Add `node_type != "passage"` filter in VDB build loop |
| Passage nodes bloat graph | Too many passages relative to entities | Cap passage nodes or only create for passages with ≥2 entities |
| Entity→passage edges dominate PPR | PPR weight too high on passage edges | Set passage edge weight lower (0.5 vs 1.0 for regular edges) |
| Existing tests fail | Entity count assertions change | Add `node_type` filter to test assertions |

### Verification

| Test | What It Verifies |
|------|-----------------|
| Build small graph with `enable_passage_nodes=True`, count nodes | Passage nodes exist alongside entity nodes |
| Check node metadata for passage nodes | `node_type="passage"`, `chunk_id` present |
| Run PPR from entity seed on bipartite graph | PPR returns entity results (passage nodes are traversal intermediaries) |
| Build entity VDB from bipartite graph | VDB contains only entity nodes, not passages |
| Build with `enable_passage_nodes=False` (default) | Same behavior as current code |

---

## Plan for Step 4: Co-occurrence-only Build Mode

### Requirements

- When `skip_relationship_extraction=True` in GraphConfig, the graph build extracts entities only (NER) and skips OpenIE/relationship extraction
- Graph is entity nodes + chunk co-occurrence edges only
- Significantly cheaper build (no relationship extraction LLM calls)
- Tests EcphoryRAG hypothesis: are explicit relationships necessary?

### Contracts

**Input:** GraphConfig with `skip_relationship_extraction: bool = False`
**Output:** Graph where:
- Entity nodes present (from NER extraction)
- No relationship edges from OpenIE
- Co-occurrence edges present (from `augment_chunk_cooccurrence`)
- Build cost ~50% lower (skip relationship extraction LLM calls)

### Pre-made decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where to gate | In ERGraph extraction loop — skip relationship extraction calls | Simplest; NER is already a separate step in two-pass extraction |
| Co-occurrence auto-enable | When `skip_relationship_extraction=True`, auto-enable `enable_chunk_cooccurrence=True` | Otherwise the graph has no edges |
| Config location | GraphConfig (build-time decision) | Affects graph structure, not retrieval |

### Files Affected

| File | Change |
|------|--------|
| `Config/GraphConfig.py` | Add `skip_relationship_extraction: bool = False` |
| `Core/Graph/ERGraph.py` | Skip OpenIE/relationship extraction when flag is True |
| `Core/Graph/BaseGraph.py` | Auto-enable co-occurrence when `skip_relationship_extraction=True` |

### Verification

| Test | What It Verifies |
|------|-----------------|
| Build with `skip_relationship_extraction=True` | Graph has entity nodes, no relationship edges |
| Co-occurrence edges auto-created | Graph has co-occurrence edges between entities sharing chunks |
| Entity VDB works | VDB search returns entities from co-occurrence-only graph |
| Build cost comparison | Relationship extraction LLM calls = 0 |

---

## Acceptance Criteria

- [x] PPR damping configurable in RetrieverConfig (`damping`), passed to PPR operator (Step 1)
- [x] Decomposition available via consolidated prompt `reason(method="decompose")` (Step 2)
- [x] `enable_passage_nodes` adds passage nodes and entity→passage edges to graph (Step 3, commit dede57d)
- [x] Entity VDB filtered to exclude passage nodes (Step 3, enhanced_entity_vdb_tools.py)
- [x] `skip_relationship_extraction` builds entity+cooccurrence graph without relationship LLM calls (Step 4, commit 32a9293)
- [x] All new config flags default to current behavior (backward compatible)
- [ ] Each attribute verified with test graph build (pending — needs graph rebuild with new flags)

---

## Budget

- Step 1 (PPR tuning): ✅ $0
- Step 2 (decomposition): ✅ $0
- Step 3 (passage nodes): ~$3-5 (one small graph rebuild with passage nodes)
- Step 4 (co-occurrence only): ~$1-2 (entity-only extraction build)
- **Remaining: ~$4-7**

---

## Execution Order

Step 3 (passage nodes) first — highest impact per literature review. Step 4 (co-occurrence only) second — independent, cheaper.
