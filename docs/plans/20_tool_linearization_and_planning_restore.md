# Plan #20: Tool Result Linearization + Restore Planning Tools

**Status:** Planned
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Plan #17 (thesis test quality)

---

## Gap

**Current:** Consolidated tool results dump raw JSON into agent context (entity records with IDs, types, descriptions, scores, metadata). A single `entity_search` call can return 2000+ chars of JSON that the LLM must parse. Meanwhile, `semantic_plan` and `todo_write` were removed from the tool surface (commit `fc4a165`), leaving the agent with no structured planning or progress tracking.

**Target:** (1) Every consolidated tool linearizes its structured output into a 2-5 line natural language summary before it enters context. Full data written to file for inspection. (2) `semantic_plan` and `todo_write` restored to the consolidated tool surface so the agent can plan and track progress.

**Why:** StructGPT's IRR framework (read → linearize → reason → iterate) demonstrated that linearization dramatically improves LLM reasoning over structured data. Our agent wastes context parsing JSON instead of reasoning. Planning tools prevent the 318-call runaway problem by giving the agent persistent working memory.

---

## References

- StructGPT paper (Jiang et al., 2023): `~/projects/project-meta/research_texts/agent_tools/structgpt_2305.09645v2.pdf`
- StructGPT repo: `~/projects/StructGPT/`
- DIGIMON `semantic_plan` implementation: `digimon_mcp_stdio_server.py:6010-6200`
- DIGIMON `todo_write` implementation: `digimon_mcp_stdio_server.py:6200-6493`
- CLAUDE.md linearization principle: "structured data must be linearized into compact NL summaries before entering LLM context"

---

## Pre-made Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where to linearize | In `tool_consolidation.py`, wrapping each dispatch call | Single point of control; doesn't change underlying operator code |
| Linearization format | 2-5 lines natural language, entity names quoted, counts shown | Matches StructGPT's linearization pattern |
| Full data storage | Write to `results/.last_tool_result.json` (overwritten per call) | Agent can `cat` the file if it needs full detail |
| Planning tool restoration | Re-add `semantic_plan` and `todo_write` to `build_consolidated_tools()` | Was removed in error; analysis showed it wasn't causing regressions |
| Prompt update | Add planning instruction to `agent_benchmark_consolidated.yaml` | Agent needs guidance on when to plan |

---

## Plan

### Step 1: Linearization functions

Create `_linearize_entity_results()`, `_linearize_relationship_results()`, `_linearize_chunk_results()`, `_linearize_reason_results()` in `tool_consolidation.py`.

Each function:
- Takes the raw JSON string from the underlying tool
- Parses it
- Returns a compact natural language summary
- Writes full JSON to `results/.last_tool_result.json`

**Linearization templates:**

```
entity_search → "Found N entities: 'X' (type, score=0.9), 'Y' (type, score=0.8), ..."
entity_traverse → "PPR from ['X']: top entities: 'A' (score=0.4), 'B' (score=0.3), ..."
entity_info(profile) → "'X' is a PERSON. Description: ... Connected to: Y, Z."
entity_info(resolve) → "Resolved 'X' → graph ID 'x_123' (confidence=0.95)"
relationship_search → "Found N relationships: X →[relation]→ Y, X →[relation]→ Z, ..."
chunk_retrieve → "Retrieved N chunks. Top chunk: '...first 200 chars...' (chunk_id=c123)"
reason(decompose) → "Decomposed into N sub-questions: 1) ... 2) ... 3) ..."
reason(answer) → "Answer: ..."
subgraph_extract → "Subgraph: N nodes, M edges connecting: X, Y, Z"
```

**Verification:** Run 3q HotpotQAsmallest, confirm results are non-zero and context is shorter.

### Step 2: Restore semantic_plan and todo_write

In `tool_consolidation.py:build_consolidated_tools()`, re-add:
```python
for maybe_tool in ("semantic_plan", "todo_write", "bridge_disambiguate"):
    if hasattr(dms, maybe_tool):
        tools.append(getattr(dms, maybe_tool))
```

**Verification:** Agent calls semantic_plan on first turn in 3q smoke test.

### Step 3: Update prompt

In `agent_benchmark_consolidated.yaml`:
- Add `semantic_plan` and `todo_write` to tool listing
- Change step 1 from `reason(method="decompose")` to `semantic_plan(question)` as primary, `reason(method="decompose")` as fallback
- Add instruction: "Track progress with `todo_write` — update status as you resolve each atom"

**Verification:** Agent follows plan → search → ground → submit flow in 3q smoke test.

### Step 4: Integration test

Run 19q MuSiQue diagnostic set with all changes. Compare to:
- Baseline: 21.1% LLM-judge
- Pre-fix (prompt v1, PPR=0.15): 52.6%
- Post-fix (prompt v2, PPR=0.5, no linearization): 36.8%

**Acceptance target:** ≥40% LLM-judge, ≤2 regressions vs baseline.

---

## Files Affected

| File | Change |
|------|--------|
| `Core/MCP/tool_consolidation.py` | Add `_linearize_*()` functions, wrap each dispatch call, restore planning tools |
| `prompts/agent_benchmark_consolidated.yaml` | Add semantic_plan/todo_write, update planning instructions |
| `results/.last_tool_result.json` | Created at runtime (gitignored) |

---

## Error Taxonomy

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| Linearization loses critical info | Summary too aggressive | Include entity IDs and scores in summary, not just names |
| Agent ignores linearized summary and asks for full data | Prompt doesn't explain file-based access | Add "Full details in results/.last_tool_result.json" to each summary |
| semantic_plan returns poor decomposition | Model capability issue | Falls back to reason(method="decompose") per prompt instruction |
| todo_write state lost between questions | Global state not reset | Already handled by `_reset_todos()` in MCP server |

---

## Acceptance Criteria

- [ ] Every consolidated tool returns linearized NL summary, not raw JSON
- [ ] Full structured data written to `results/.last_tool_result.json`
- [ ] `semantic_plan` and `todo_write` available in consolidated tool list
- [ ] Prompt instructs planning before retrieval
- [ ] 3q HotpotQAsmallest smoke test passes
- [ ] Context per tool call reduced ≥50% vs raw JSON (measure with tiktoken)
