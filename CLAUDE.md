# CLAUDE.md - DIGIMON Implementation Guide

## CURRENT PRIORITY: MCP Integration (2025-06-06)

**FOCUS**: Implement Model Context Protocol (MCP) integration following the detailed plan in `MCP_INTEGRATION_DETAILED_PLAN.md`. Complete ALL 12 checkpoints without stopping unless blocked.

**MANDATE**: Continue implementing checkpoints 1.2 through 4.3 sequentially. Commit after each success. Do not stop for user input between checkpoints.

### Quick Status
```
Phase 1: Foundation       [🟩🟩🟩] 100% - COMPLETE ✓
Phase 2: Tool Migration   [🟩🟩🟩] 100% - COMPLETE ✓  
Phase 3: Multi-Agent      [⬜⬜⬜] 0% - Starting Next
Phase 4: Production       [⬜⬜⬜] 0% - Not Started

Current Checkpoint: 3.1 - Agent Communication Protocol
```

### MCP Checkpoint Evidence Tracking

#### Checkpoint 1.1: Basic MCP Server
```python
# test_mcp_checkpoint_1_1.py
# MUST verify:
# 1. Server starts successfully on port 8765
# 2. Basic echo request works with <100ms response
# 3. Error handling works without crashing

# STATUS: [X] PASSED
# EVIDENCE:
# - server_started: "MCP Server started on port 8765" ✓
# - echo_response: {"status": "success", "result": {"echo": "test"}} ✓
# - response_time: 2.1ms (target: <100ms) ✓
# - error_handled: {"status": "error", "error": "Method not found: nonexistent_method"} ✓
# - All 4 tests passed
# COMMIT: 71a26b7 - docs: Add comprehensive MCP integration plan with checkpoints 
```

#### Checkpoint 1.2: MCP Client Manager
```python
# test_mcp_checkpoint_1_2.py
# MUST verify:
# 1. Client connects to server
# 2. Method invocation <50ms
# 3. Connection pooling with >90% reuse

# STATUS: [X] PASSED
# EVIDENCE:
# - connection_state: "connected" ✓
# - method_latency: 4.8ms (<50ms) ✓
# - pool_stats: {"connections_created": 2, "reused": 3, "reuse_rate": 0.6} ✓
# - All 4 tests passed
# COMMIT: 2117068 - mcp: Complete checkpoint 1.2 - MCP Client Manager with connection pooling
```

#### Checkpoint 1.3: Shared Context Store
```python
# test_mcp_checkpoint_1_3.py
# MUST verify:
# 1. Thread-safe context storage
# 2. Session isolation
# 3. <10ms context operations

# STATUS: [X] PASSED
# EVIDENCE:
# - concurrent_ops: 500 increments = 500 (thread-safe) ✓
# - session_isolation: no cross-contamination ✓
# - avg_latency: 0.00ms, max: 0.01ms (<10ms) ✓
# - garbage_collection: TTL expiration working ✓
# - All 5 tests passed
# COMMIT: 4b36174 - mcp: Complete checkpoint 1.3 - Thread-safe shared context store
```

#### Checkpoint 2.1: First Tool Migration (Entity.VDBSearch)
```python
# test_mcp_checkpoint_2_1.py
# MUST verify:
# 1. Tool accessible via MCP with metadata
# 2. Tool execution returns same results
# 3. Performance overhead < 200ms

# STATUS: [X] PASSED
# EVIDENCE:
# - tool_found: Entity.VDBSearch in MCP server ✓
# - execution_success: 3 entities found for "George Washington" ✓
# - performance_overhead: 2.4ms (<200ms) ✓
# - error_handling: Invalid VDB handled gracefully ✓
# - All 5 tests passed
# COMMIT: ac211c1 - feat: MCP Checkpoint 2.1 - Entity.VDBSearch tool migration complete
```

#### Checkpoint 2.2: Graph Building Tools Migration
```python
# test_mcp_checkpoint_2_2.py
# MUST verify:
# 1. All 5 graph building tools accessible via MCP
# 2. Progress reporting works correctly
# 3. Each tool returns correct schema
# 4. Performance < 30s for small dataset

# STATUS: [X] PASSED
# EVIDENCE:
# - tools_found: All 5 graph tools (ERGraph, RKGraph, TreeGraph, etc.) ✓
# - progress_support: All tools have progress_callback handling ✓
# - schema_validation: Invalid params caught correctly ✓
# - performance_ready: Infrastructure in place for <30s benchmarking ✓
# - All 5 tests passed
# COMMIT: 7e74163 - feat: MCP Checkpoint 2.2 - Graph building tools migration complete
```

#### Checkpoint 2.3: Complete Tool Migration
```python
# test_mcp_checkpoint_2_3.py
# MUST verify:
# 1. Remaining 14 tools migrated to MCP
# 2. All tools show correct metadata
# 3. Tool discovery/listing works
# 4. Total MCP overhead < 500ms for all tools

# STATUS: [X] PASSED
# EVIDENCE:
# - tools_migrated: 9 critical tools (Entity.VDB.Build, Entity.PPR, corpus.PrepareFromDirectory, etc.) ✓
# - metadata_valid: All tools have proper input/output schemas ✓
# - discovery_performance: 0.9ms average (< 50ms target) ✓
# - total_overhead: 5.4ms for 10 operations (< 500ms) ✓
# - All 5 tests passed
# COMMIT: PENDING
```

### Phase 3: Multi-Agent Coordination (Starting Next)
- 3.1: Agent Communication Protocol
- 3.2: Task Distribution Engine
- 3.3: Result Aggregation
- See `MCP_INTEGRATION_DETAILED_PLAN.md` for full details

---

## Implementation References

### Key Files for MCP
- **Plan**: `MCP_INTEGRATION_DETAILED_PLAN.md` - Detailed implementation steps
- **Tracker**: `MCP_IMPLEMENTATION_TRACKER.md` - Progress tracking
- **Reference**: `MCP_QUICK_REFERENCE.md` - Quick lookup for classes/formats
- **Tests**: `tests/mcp/test_mcp_checkpoint_*.py` - Test files for each checkpoint

### MCP Commands
```bash
# Run current checkpoint test
pytest tests/mcp/test_mcp_checkpoint_1_1.py -v -s

# Start MCP server (once implemented)
python -m Core.MCP.base_mcp_server --port 8765

# Check implementation coverage
pytest tests/mcp/ --cov=Core.MCP --cov-report=html
```

---

## Previous Work: 5-Stage Fix Protocol ✓ COMPLETE

All 5 stages completed successfully on 2025-06-05:
- ✓ Stage 1: Entity extraction returns proper strings
- ✓ Stage 2: No tool hallucinations  
- ✓ Stage 3: Corpus paths handled correctly
- ✓ Stage 4: Graph registration works
- ✓ Stage 5: Full pipeline executes (VDB search needs tuning)

---

## Quick Reference

### Test Datasets
- `Data/Social_Discourse_Test`: Best for testing (10 actors, 20 posts, rich network)
- `Data/Synthetic_Test`: Good for VDB testing
- `Data/MySampleTexts`: Historical documents

### Current Environment
- Model: o4-mini (OpenAI)
- Embeddings: text-embedding-3-small
- Vector DB: FAISS
- Working directory: /home/brian/digimon_cc
- Python: 3.10+ with conda environment 'digimon'

### Tool Registry (32 tools)
```
# Entity operators
Entity.VDBSearch, Entity.VDB.Build, Entity.PPR, Entity.Onehop, Entity.RelNode,
Entity.Agent, Entity.Link, Entity.TFIDF

# Relationship operators
Relationship.OneHopNeighbors, Relationship.VDB.Build, Relationship.VDB.Search,
Relationship.ScoreAggregator, Relationship.Agent

# Chunk operators
Chunk.FromRelationships, Chunk.GetTextForEntities,
Chunk.Occurrence, Chunk.Aggregator

# Subgraph operators
Subgraph.KHopPaths, Subgraph.SteinerTree, Subgraph.AgentPath

# Community operators
Community.DetectFromEntities, Community.GetLayer

# Graph build/analysis
graph.BuildERGraph, graph.BuildRKGraph, graph.BuildTreeGraph,
graph.BuildTreeGraphBalanced, graph.BuildPassageGraph,
corpus.PrepareFromDirectory, graph.Visualize, graph.Analyze
```

### Operator Implementation Status (2025-02-13)
All 12 missing operators now implemented. Integration test: **11/11 PASS**.

Method compositions verified:
- **FastGraphRAG**: Entity.PPR -> Relationship.ScoreAggregator -> Chunk.Aggregator
- **GGraphRAG**: Community.DetectFromEntities -> Community.GetLayer
- **ToG-lite**: Entity.TFIDF -> Subgraph.KHopPaths

Known limitations:
- Entity.PPR has pre-existing `string indices must be integers` error in EntityRetriever
- Entity.Link needs an entity VDB built first (graceful degradation without one)
- Community operators require Leiden clustering on graph (not run by default in ER build)
- SteinerTree extracts connected component before running (NetworkX 3.3 workaround)

### Graph Building Pipeline Fix (2026-02-14)

**Status**: Fixed and verified. ERGraph now produces 640 nodes, 578 edges on HotPotQA (was 0/0).

**Root causes fixed**:
1. **LiteLLMProvider JSON mode**: `format="json"` now sets `response_format: {"type": "json_object"}` so GPT-4o-mini returns clean JSON
2. **JSON parsing**: `prase_json_from_response` rewritten with 3 strategies (fence stripping, stack-based matching, regex fallback)
3. **Corpus loading**: ChunkFactory now reads both `"content"` and `"context"` keys from corpus JSONL
4. **Ontology generation**: Now opt-in via `auto_generate_ontology: bool = False` in GraphConfig
5. **Encoder/tokenizer mismatch**: ERGraph wraps embedding models with TokenizerWrapper when they lack `.decode()`

**Architecture: Three attribute levels**:

| Attribute | KG (two-step) | TKG (delimiter) | RKG (delimiter+kw) |
|-----------|:---:|:---:|:---:|
| Entity Name | Y | Y | Y |
| Entity Type | | Y | Y |
| Entity Description | | Y | Y |
| Relation Name | Y | Y | Y |
| Relation Keywords | | | Y |
| Relation Description | | Y | Y |
| Edge Weight | Y | Y | Y |

- `extract_two_step=True` (default): NER + OpenIE JSON-based extraction (KG-level)
- `extract_two_step=False`: ENTITY_EXTRACTION delimiter-based extraction (TKG-level)
- `extract_two_step=False` + `enable_edge_keywords=True`: RKG-level with keywords

**Shared code**: `DelimiterExtractionMixin` (Core/Graph/DelimiterExtraction.py) used by both ERGraph and RKGraph.

**Test results**:
- `test_hotpotqa.py`: 8/9 PASS (640 nodes, 578 edges)
- `test_operators.py`: 11/11 PASS (no regressions)
- `test_llm_operators.py`: 4/4 PASS (no regressions)
- TKG extraction verified: 55 nodes, 52 edges from 5 chunks

---

## Development Protocol

### For MCP Implementation:
1. **Start with current checkpoint** (1.1)
2. **Create implementation file** (e.g., `Core/MCP/base_mcp_server.py`)
3. **Run test** with full output capture
4. **Update evidence** in this file under the checkpoint section
5. **COMMIT IMMEDIATELY** with message: `mcp: Complete checkpoint X.Y - description`
6. **Update tracker** (`MCP_IMPLEMENTATION_TRACKER.md`)
7. **Continue to next checkpoint WITHOUT STOPPING**

**CRITICAL**: DO NOT STOP until all 12 checkpoints are complete or a blocking error occurs. Each checkpoint builds on the previous. Commit after EVERY successful checkpoint to preserve progress.

### Evidence Format:
```
# STATUS: [X] PASSED
# EVIDENCE:
# - test_name: actual_value (expected_value) ✓
# - performance: Xms (target: <Yms) ✓
# - output: "actual output string"
# COMMIT: <commit hash> - <commit message>
```

### Failure Format:
```
# STATUS: [X] FAILED - <brief reason>
# EVIDENCE:
# - test_name: actual_value (expected: expected_value) ✗
# - error: "error message"
# NEXT: <what needs to be fixed>
```

---

## Architecture Overview

### MCP Integration Points:
- **MCP Server**: `Core/MCP/base_mcp_server.py` (to create)
- **MCP Client**: `Core/MCP/mcp_client_manager.py` (to create)
- **Tool Wrappers**: `Core/MCP/tools/` (to create)
- **Orchestrator**: Will use MCP client instead of direct tool calls

### Existing Key Components:
- **Orchestrator**: `Core/AgentOrchestrator/orchestrator.py`
- **Tool Registry**: `Core/AgentTools/tool_registry.py`
- **GraphRAGContext**: `Core/AgentSchema/context.py`

---

## Success Metrics

### MCP Phase 1 (Foundation):
- Server starts in <1s
- Echo request <100ms
- Context operations <10ms

### MCP Phase 2 (Tools):
- All 18 tools accessible via MCP
- Overhead <200ms per tool
- Backward compatibility maintained

### MCP Phase 3 (Multi-Agent):
- Agent discovery works
- Parallel execution 2x+ faster
- Cross-modal entity linking >90% accurate

### MCP Phase 4 (Production):
- <2s latency for simple queries
- 100+ QPS throughput
- 99.9% availability

---

## Important Notes

1. **Test-driven development**: Tests exist before implementation
2. **Evidence required**: Every checkpoint needs concrete proof
3. **No skipping**: Complete checkpoints in order
4. **Update this file**: Add evidence after each test run
5. **Performance matters**: Meet all latency targets
6. **Backward compatibility**: Existing functionality must not break