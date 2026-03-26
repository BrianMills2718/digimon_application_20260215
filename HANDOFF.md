# GraphRAG Handoff — 2026-03-26

## Session Results

**50q MuSiQue**: Baseline 20.0% → GraphRAG 42.0% LLM-judge (2.1x). 15 graph wins.
**With iteration gains**: 9/25 both-fail flipped → projected ~60%+ (3x baseline).

## What Was Built This Session

### Code Changes (all committed + pushed to `trip-backup-20260224_145348`)
1. **Tool result linearization** — `Core/MCP/tool_consolidation.py` wraps every tool result in `_linearize()`. NO truncation of evidence text (critical fix — was hiding answers at 150 chars).
2. **Passage nodes** — `scripts/add_passage_nodes.py` adds HippoRAG v2 bipartite graph to existing graph without rebuild ($0, 2 min). 11,655 passage nodes + 128K edges added to MuSiQue.
3. **Plan-completion enforcement** — `submit_answer` checks `dms._todos` for pending atoms and rejects early submission.
4. **Entity profile connectivity** — `entity_profile` now returns `edge_count`, `relationship_types`, `connected_entities` so agent knows whether to use graph traversal or text search.
5. **Prompt v3.4** — planning-first flow, retrieval strategy heuristics (use graph if edges exist, text if not), multi-hop chain following.
6. **4 operators restored** to consolidated surface: entity_search(agent), relationship_search(agent), chunk_retrieve(ppr_weighted), subgraph_extract(agent).
7. **AgentErrorBudget** in llm_client — max_agent_turns, max_consecutive_errors_per_model, max_total_errors.
8. **Makefile targets** — `make bench-musique`, `make diagnose`, `make add-passages`, `make cost-by-task`, `make check-rules`, `make linearization-check`.
9. **`scripts/diagnose_question.py`** — per-question trace analysis showing plan, tool calls, results, verdict.
10. **`scripts/check-rules.sh`** — scans for CLAUDE.md rule violations (json_object, hardcoded paths, except:pass).

### Documentation
- `CURRENT_STATUS.md` — single source of truth for benchmark numbers
- ADR-014 updated (operators restored, semantic_plan/todo_write restored)
- ROADMAP Gate D→E marked PASSED
- Plans #17 (In Progress), #20 (Complete) status corrected
- `eval/fixtures/README.md` — manifest for 14 fixture files
- No-truncation rule added to CLAUDE.md
- Composable graph attributes principle added to CLAUDE.md
- Available Skills table added to `~/projects/.claude/CLAUDE.md`
- `/plan` command rewritten to match CLAUDE.md steps 1-10
- Context7 MCP installed

### llm_client Changes
- Plan #18: AgentErrorBudget implemented
- Plan #19: PlanningConfig + auto-inject context (done by other agent)
- `mcp_agent` module re-exported for backward compat
- Cost tracking Makefile targets

## What the 16 Remaining Failures Need

### Root Cause (empirically verified)
The agent defaults to `entity_search` + `chunk_retrieve` (text retrieval). It barely uses graph traversal (`entity_traverse`: 0-4 calls across 16 questions). Even gpt-5.4 (full, not mini) shows the same pattern — 65 chunk_retrieve vs 1 entity_traverse.

**This is NOT a model capability issue.** It's a strategy/tooling issue. The agent doesn't know WHEN graph traversal helps because it couldn't see edge counts until we just added that. But even with edge counts, it still defaults to text search.

### The Key Insight (Brian's)
The Atom of Thought (semantic_plan) decomposition should connect to what's initially retrieved. When the agent decomposes "What is the birthplace of the person São José dos Campos was named after?" into atoms:
- A1: Who is the person? → finds "Saint Joseph" via chunk text
- A2: What is their birthplace? → should search for "Saint Joseph birthplace" 

But the agent stops after A1 and submits "Saint Joseph" as the answer instead of searching for A2. Plan enforcement helps some cases, but the agent still picks the wrong fact from retrieved evidence.

### What to Try Next
1. **Experimental tool chain discovery** — manually walk through 3-4 failing questions, call tools yourself, find what combination actually produces the right answer. Encode those patterns as heuristics.
2. **Semantic plan → retrieval strategy mapping** — each atom type (lookup, relation, compose) should map to specific tool sequences. A "relation" atom (birthplace, founded_by) should trigger `relationship_search` if edges exist, or `chunk_retrieve("X birthplace")` if not.
3. **Graph rebuild for zero-edge entities** — Lady Godiva has 0 edges, São José has 0 edges. The extraction didn't create relationships for them. Either fix extraction or add co-occurrence edges (which passage nodes partially address).

## Blocked Items
- **llm_client missing 6 post-eval exports** — use `--post-det-checks none --post-gate-policy none` to bypass
- **Graph rebuild** stalled at 45% from API quota. `scripts/add_passage_nodes.py` is the $0 alternative for passage enrichment.

## Key Files
| File | Purpose |
|------|---------|
| `CURRENT_STATUS.md` | Single source of truth for numbers |
| `Core/MCP/tool_consolidation.py` | Consolidated tools + linearization + plan enforcement |
| `prompts/agent_benchmark_consolidated.yaml` | Prompt v3.4 |
| `scripts/diagnose_question.py` | Per-question trace analysis |
| `scripts/add_passage_nodes.py` | Add passage nodes without rebuild |
| `eval/fixtures/musique_remaining_failures.txt` | 16 questions still failing |
| `eval/fixtures/README.md` | Fixture manifest |
| `Makefile` | All make targets |

## Commands
```bash
make bench-musique                    # Run 19q MuSiQue diagnostic
make diagnose FILE=results/X.json QID=Y  # Diagnose specific question
make cost-by-task DAYS=1              # Check LLM spend
make add-passages DATASET=MuSiQue    # Add passage nodes ($0)
make check-rules                     # Scan for CLAUDE.md violations
make linearization-check             # Check for data loss in linearization
```
