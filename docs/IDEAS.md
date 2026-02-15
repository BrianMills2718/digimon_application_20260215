# DIGIMON Ideas & Dead Code Inventory

## Ideas Extracted from Unused Code

### 1. Execution Memory Feedback Loop
**Source**: `Core/Memory/memory_system.py` (PatternMemory class)
**Idea**: After each `execute_method`/`auto_compose`, log `{query, method_chosen, quality_score, latency_ms}` to a JSONL file. Feed recent history as few-shot examples into `auto_compose`'s prompt so it learns which methods work for which query types. EMA smoothing on quality scores per method to handle drift. ~30 lines bolted onto existing auto_compose flow, no new module needed.

### 2. Episodic→Semantic Consolidation
**Source**: `Core/Memory/memory_architecture.py` (MemoryConsolidation class)
**Idea**: Periodically scan recent execution episodes, count recurring entities/patterns, promote frequent ones to "semantic facts" with confidence = frequency/total. Example: "entity X appears in 5/20 episodes → create semantic entry with 0.25 confidence." Could apply to DIGIMON by consolidating frequently-retrieved entities across queries into a "hot entities" cache.

### 3. Adaptive Timeout
**Source**: `Core/AgentOrchestrator/enhanced_orchestrator.py` (AdaptiveTimeout)
**Idea**: Estimate operation timeout based on type (VDB build=5000 tokens, graph build=10000, default=1000), then adjust based on observed performance. Uses `asyncio.wait_for()` with the adaptive estimate. Good for production MCP server where different operations have wildly different latencies.

### 4. Step-Level Parallelism via Topological Sort
**Source**: `Core/AgentOrchestrator/parallel_orchestrator.py`
**Idea**: Analyze `ToolInputSource` references in an ExecutionPlan to build a dependency DAG between steps. Topological sort with level grouping — steps at the same level have no interdependencies and can run via `asyncio.gather()`. Falls back to sequential on circular deps. Measures speedup (wall-clock vs sum of step times). Applicable to the operator pipeline if we ever want to parallelize independent operator chains within a single query.

### 5. Streaming Progress Protocol
**Source**: `Core/AgentOrchestrator/async_streaming_orchestrator.py`
**Idea**: `UpdateType` enum (PLAN_START/STEP_START/TOOL_START/TOOL_COMPLETE/STEP_COMPLETE/PLAN_COMPLETE) + `StreamingUpdate` dataclass yielded via `AsyncGenerator`. Clean pattern for real-time progress reporting during long-running pipeline executions. Includes async generator merging via `asyncio.wait(FIRST_COMPLETED)` for interleaving updates from parallel tools.

### 6. Structured Error Recovery
**Source**: `Core/AgentOrchestrator/enhanced_orchestrator.py` (StructuredError)
**Idea**: Errors carry a `recovery_strategies` list — each entry has a strategy type (retry/wait/skip/fallback) and params. Orchestrator tries strategies in order. Example: rate limit → wait 60s → retry with exponential backoff. Timeout → retry with 2x timeout → skip. Good for production reliability.

### 7. Multi-Dataset Composition
**Idea**: `OperatorContext` is monolithic — all operators share one graph, one VDB set. This blocks cross-dataset queries ("compare entities in dataset A vs B"), graph merging, and federation. Needs either per-step context overrides in `ExecutionPlan`, or a multi-context executor that can bind different graphs to different steps.

### 8. Sequence Pattern Mining
**Source**: `Core/Memory/pattern_learning.py` (SequencePatternRecognizer)
**Idea**: Sliding window over event sequences, count frequent subsequences. Similarity via LCS (longest common subsequence) + Jaccard on element sets. Could apply to operator call sequences — "users who start with entity.vdb_search usually follow with entity.ppr" — to power auto-complete or suggestions in an agent UI.

---

## Dead Code Inventory (candidates for future deletion)

These modules are **not imported by any production code** (MCP server, GraphRAG.py, operators). They're only referenced by their own tests, scripts/demos, and each other. Kept for now as reference for the ideas above.

### Core/Memory/ (3 files, ~2,100 lines)
- `memory_system.py` — LRU memory stores, PatternMemory with EMA, keyword query classification, pickle persistence
- `memory_architecture.py` — Episodic/semantic/working memory, consolidation, decay, association graph, relevance scoring
- `pattern_learning.py` — Sequence and structural pattern recognition, pattern store with indices, feedback loop

### Core/AgentOrchestrator/ variants (4 files, ~1,650 lines)
- `async_streaming_orchestrator.py` — AsyncGenerator-based streaming with tool categorization
- `async_streaming_orchestrator_v2.py` — Same but uses dynamic tool registry
- `enhanced_orchestrator.py` — PerformanceMonitor + AdaptiveTimeout + StructuredError recovery
- `memory_enhanced_orchestrator.py` — Combines streaming v2 + memory system
- `parallel_orchestrator.py` — Topological sort for step-level parallelism

### Dead test files (test the above)
- `tests/unit/test_async_streaming_orchestrator.py` — 7 failures (ExecutionPlan schema mismatch)
- `tests/unit/test_memory_system.py` — 3 failures (float comparison, index OOB, assertion)
- `tests/unit/test_dynamic_tool_registry.py` — 1 failure (tag naming)
- `tests/unit/test_pattern_learning.py`
- `tests/integration/test_async_streaming_integration.py`
- `tests/integration/test_memory_enhanced_orchestrator.py`
- `tests/integration/test_orchestrator_with_registry.py`

### Note
The live orchestrator is `Core/AgentOrchestrator/orchestrator.py` — it handles all current production execution.
