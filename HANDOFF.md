# GraphRAG Handoff — 2026-03-28

## Session Focus

Architecture review of the current DIGIMON failure family against:

1. DIGIMON active docs and plans
2. onto-canon6 export/canonicalization surfaces
3. project-meta convergence/vision docs

The main question was whether DIGIMON should rebuild around onto-canon6, and
how to think about build vs projection vs retrieval vs analysis.

## Bottom-Line Conclusions

### 1. The long-term split is right, but the current seam is thinner than it sounds

The strategic direction is sound:

1. `onto-canon6` as governed semantic/canonicalization producer
2. DIGIMON as projection + retrieval system
3. analysis as a distinct concern conceptually

But the current cross-project seam is still too thin and lossy to carry that
architecture cleanly today.

### 2. DIGIMON already has the right projection idea in docs

This was an important correction.

`docs/GRAPH_ATTRIBUTE_MODEL.md` already says:

1. build one truthful maximal entity-graph representation
2. derive narrower projections from it
3. treat passage/tree graphs as separate topologies

So the missing concept is not "discover projection." The missing work is to
actually implement the manifest/projection/tool-gating model DIGIMON already
describes.

### 3. Do not rebuild DIGIMON inside onto-canon6

Recommended boundary:

1. `onto-canon6` owns:
   - governed assertions
   - canonical entities
   - alias memberships / stable identity
   - evidence refs / provenance
   - durable semantic state
2. DIGIMON owns:
   - projection recipes / projection compiler
   - passage graph
   - entity-passage graph
   - retrieval-oriented alias/gloss/co-occurrence projections
   - retrieval operators and routing
3. analysis should be a separate concern conceptually, but should not be split
   into a new repo yet

## Critical Current Seam Limitations

### DIGIMON Import Bridge

`Core/Interop/onto_canon_import.py` is currently much losier than the
architecture discussion assumed:

1. entities are merged by `entity_name` only
2. relationships are merged by **sorted endpoint pair**, so direction is lost
3. merged edges sum weights
4. missing-endpoint relationships are skipped
5. blank fallback nodes may be created during import

This is a retrieval bridge, not a truth-preserving semantic import layer.

### onto-canon6 Digimon Export

`onto-canon6/src/onto_canon6/adapters/digimon_export.py` is also still thin:

1. flat `entities.jsonl` / `relationships.jsonl`
2. no alias membership export
3. no passage artifacts
4. no evidence refs
5. no assertion-to-passage links
6. no full role structure

So the seam is currently not rich enough to justify a wholesale architecture
shift.

### Foundation Export Is Closer To The Desired Interchange

`onto-canon6/src/onto_canon6/adapters/foundation_assertion_export.py` is
closer to the likely long-term interchange direction because it preserves:

1. typed role fillers
2. alias ids
3. qualifiers
4. assertion identity

If a richer DIGIMON/onto-canon6 interchange is built, Foundation-style
assertion artifacts are a stronger starting point than the current flat DIGIMON
JSONL.

## Advice For The Current Failure Family

The São José / Saint Joseph / Nazareth failure family does **not** require an
immediate onto-canon6 rebuild to justify work.

DIGIMON already has local design gaps that directly target this family:

1. `canonical_name` vs `search_keys` split
2. unicode-preserving identity and normalized aliases
3. explicit gloss/name-meaning edges
4. first-class passage nodes
5. entity-passage projections

Those should be treated as legitimate DIGIMON-side fixes, not as proof that
DIGIMON must be replaced.

## Recommended Next Actions

1. Treat any onto-canon6-backed rebuild as an **experimental lane**, not the
   new default path.
2. Write one architecture memo that reconciles:
   - `docs/GRAPH_ATTRIBUTE_MODEL.md`
   - `project-meta/vision/ONTO_CANON6_DIGIMON_CONVERGENCE.md`
   - `project-meta/vision/FRAMEWORK.md`
   - `project-meta/vision/FOUNDATION.md`
3. Define a richer interchange contract before more import/export churn.
4. Run a bounded comparison on a canonicalization-heavy MuSiQue slice:
   - current DIGIMON-native build
   - onto-canon6 semantic bundle + DIGIMON projection build
5. Continue to treat current benchmark-thesis work as core, and architecture
   convergence as experimental until it proves retrieval value.

## Important Constraint

`docs/plans/03_prove_adaptive_routing.md` and `docs/REPO_SURFACE.md` still make
the core maintained path the benchmark/thesis lane. Do not let architecture
convergence silently become the default maintained lane without explicit proof.

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
