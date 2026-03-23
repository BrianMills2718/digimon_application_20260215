# Plan #15: Operator Consolidation (28 → 8-10 Tools)

**Status:** Planned
**Type:** implementation
**Priority:** High (highest-leverage context management intervention)
**Blocked By:** Plan #14 (need working benchmark to verify no regression)
**Blocks:** Plan #17

---

## Gap

**Current:** 28 operators exposed as 50+ individual MCP tools. Agent context filled with tool descriptions before it can reason about the question. Latest benchmark: adaptive mode (32% EM, $5.50) underperforms baseline (34% EM, $2.03). The Codex agent's PTC work confirmed that even when given the choice, agents prefer sequential tool calls — the problem is tool *count*, not tool *interface*.

**Target:** 8-10 consolidated tools that cover all current functionality via method/mode arguments. ≥40% reduction in tool description tokens. No lost functionality.

**Why:** Context is a depletable resource. Fewer tools = more context for reasoning = better routing decisions. This is the most direct intervention for the agent drowning problem identified in the strategic review.

---

## References Reviewed

- Strategic review (2026-03-23): identified 50-tool surface as primary cause of agent routing failures
- Literature review (`investigations/digimon/2026-03-23-graphrag-sota-review.md`): every competitive system uses a fixed pipeline with <10 retrieval steps
- PTC assessment (Codex agent, 2026-03-22): agents always choose sequential over PTC; problem is tool count
- `Core/Schema/OperatorDescriptor.py` — operator metadata and slot contracts
- `digimon_mcp_stdio_server.py` — current tool definitions
- `eval/experiment_log.jsonl` — which operators appear in successful benchmark runs
- Tool design principles in `~/projects/.claude/CLAUDE.md` — "Task-oriented, not REST wrappers — one research_topic() beats five get_X() calls"

---

## Files Affected

- `digimon_mcp_stdio_server.py` (modify — consolidated tool definitions)
- `Core/MCP/tool_consolidation.py` (create — dispatcher that routes consolidated tool calls to existing operator implementations)
- `prompts/agent_benchmark_hybrid.yaml` (modify — update tool references)
- `prompts/agent_benchmark_fixed_graph.yaml` (modify — update tool references)
- `eval/run_agent_benchmark.py` (modify — update `_BENCHMARK_TOOL_CONTRACTS`)
- `tests/test_tool_consolidation.py` (create — verify dispatch + no lost functionality)

---

## Plan

### Pre-made decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Consolidation strategy | Merge by category with method argument | Preserves operator semantics; agents learn one tool per category |
| Keep individual operators in Core/ | Yes — consolidated tools dispatch to them | No refactor of operator implementations; thin adapter layer |
| Keep legacy tool names | No — clean break, update prompts | Legacy aliases create confusion; rip off the bandaid |
| Progressive disclosure interaction | Consolidation replaces disclosure for benchmark mode | With 8-10 tools, disclosure is unnecessary |
| Benchmark mode tools | All consolidated tools visible in mode 1 | Small enough surface to always show |

### Consolidated tool mapping

| Consolidated Tool | Methods | Underlying Operators |
|---|---|---|
| `entity_search` | `semantic`, `string`, `tfidf` | entity.vdb, entity_string_search, entity.tfidf |
| `entity_traverse` | `onehop`, `ppr`, `link` | entity.onehop, entity.ppr, entity.link |
| `relationship_search` | `graph`, `semantic`, `score` | relationship.onehop, relationship.vdb, relationship.score_agg |
| `chunk_retrieve` | `relationships`, `cooccurrence`, `text`, `semantic` | chunk.from_relation, chunk.occurrence, chunk.text_search, chunk.vdb |
| `subgraph_extract` | `khop`, `steiner`, `agent` | subgraph.khop_paths, subgraph.steiner_tree, subgraph.agent_path |
| `community_search` | `from_entity`, `from_level` | community.from_entity, community.from_level |
| `reason` | `decompose`, `synthesize`, `answer`, `extract_entities` | meta.decompose_question, meta.synthesize_answers, meta.generate_answer, meta.extract_entities |
| `submit_answer` | — | submit_answer (unchanged) |
| `plan` | — | semantic_plan (unchanged) |
| `resources` | — | list_available_resources (unchanged) |

**Total: 10 tools** (7 consolidated + 3 control)

### Steps

1. **Audit**: Parse `eval/experiment_log.jsonl` to identify which operators appear in successful (EM=1) benchmark runs. Confirm all are covered by the consolidated mapping.
2. **Implement dispatcher**: Create `Core/MCP/tool_consolidation.py` — thin dispatcher that takes consolidated tool name + method argument, validates, and calls the underlying operator implementation.
3. **Wire into MCP server**: Add consolidated tool definitions to `digimon_mcp_stdio_server.py`. Each tool has a clear description explaining all methods and when to use each.
4. **Update benchmark contracts**: Modify `_BENCHMARK_TOOL_CONTRACTS` in `eval/run_agent_benchmark.py` to use consolidated tool names.
5. **Update prompt templates**: Modify `prompts/agent_benchmark_hybrid.yaml` and `agent_benchmark_fixed_graph.yaml` to reference consolidated tools.
6. **Measure token reduction**: Compare tool description token count before/after.
7. **Smoke test**: Run `HotpotQAsmallest` 3q with consolidated tools, verify non-zero accuracy.
8. **Regression test**: Run `HotpotQAsmallest` 10q, compare to last known 10q result.

### Error taxonomy

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| Operator dispatch fails | Method name mismatch or missing parameter mapping | Fix dispatcher routing table |
| Slot type mismatch | Consolidated tool returns wrong SlotKind | Verify dispatcher preserves original operator I/O |
| Agent calls non-existent method | Prompt doesn't explain available methods clearly | Improve tool description; add `valid_methods` in schema |
| Regression on smoke test | Consolidation changed behavior, not just interface | Diff consolidated vs individual tool outputs on same input |

### Backtracking ladder

1. If consolidation breaks a specific operator: test that operator individually, fix dispatcher
2. If agent can't navigate consolidated tools: improve tool descriptions (not add more tools)
3. If regression >5% EM on 10q: revert and investigate which consolidation caused the drop
4. After 3 failed approaches → escalate; the consolidation mapping may need rethinking

---

## Required Tests

### New Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/test_tool_consolidation.py` | `test_entity_search_semantic` | entity_search(method="semantic") dispatches to entity.vdb |
| `tests/test_tool_consolidation.py` | `test_entity_search_string` | entity_search(method="string") dispatches to entity_string_search |
| `tests/test_tool_consolidation.py` | `test_entity_traverse_ppr` | entity_traverse(method="ppr") dispatches to entity.ppr |
| `tests/test_tool_consolidation.py` | `test_chunk_retrieve_all_methods` | All 4 chunk_retrieve methods dispatch correctly |
| `tests/test_tool_consolidation.py` | `test_reason_all_methods` | All 4 reason methods dispatch correctly |
| `tests/test_tool_consolidation.py` | `test_invalid_method_fails_loud` | Unknown method raises clear error |
| `tests/test_tool_consolidation.py` | `test_token_reduction` | Tool descriptions use ≥40% fewer tokens than individual tools |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/test_operators*.py` | Underlying operators unchanged |
| `eval/run_agent_benchmark.py --num 3` | End-to-end still works |

---

## Acceptance Criteria

- [ ] All 28 operator capabilities reachable via 10 consolidated tools
- [ ] Tool description token count reduced ≥40% vs current 50+ tools
- [ ] HotpotQAsmallest 3q smoke test passes with non-zero accuracy
- [ ] HotpotQAsmallest 10q regression test within 5% of previous best
- [ ] No changes to Core/Operators/ (operators untouched; only the MCP surface changes)
- [ ] Invalid method arguments fail loud with clear error messages

---

## Budget

~$1-2 for smoke and regression tests. No LLM calls for the implementation itself.
