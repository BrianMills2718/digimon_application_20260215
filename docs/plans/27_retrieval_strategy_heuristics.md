# Plan #27: Retrieval Strategy Heuristics

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** None

---

## Gap

**Current:** The agent makes systematic retrieval strategy errors that cause failures across a broad class of questions. These errors stem from two wrong mental models in the current prompt:

1. `entity_info` is labelled "for navigation, not answers" — this causes agents to skip entity profiles and jump straight to graph traversal. In reality, entity descriptions ARE an answer surface containing attribute facts (counts, dates, characteristics, qualifications). The Venice "22 plague outbreaks" fact lives in the Venice entity description AND in a direct graph edge. The agent never checks it.

2. There is no metacognitive check during atom completion. When an intermediate entity is resolved, the agent accepts it without verifying that its semantic type satisfies the question's constraint. This causes Intermediate Entity Errors (IEE) where the agent resolves to an entity one level too abstract: "holy family" (a group) when the question says "the person who," or "Middle East" (a macro-region) when the question needs a specific named sub-region.

Both errors compound: wrong entity → wrong traversal target → wrong answer or stagnation.

**Target:**

1. Prompt correctly distinguishes `entity_info(profile)` from `entity_traverse`: profile is for attributes OF the entity, traversal is for NEIGHBORS OF the entity.

2. When marking an atom done via `todo_write`, the agent records a `doubt` field: "what could make this intermediate resolution wrong?" This is non-blocking but forces a semantic self-check at the moment of commitment.

3. Before calling `submit_answer`, the agent checks whether the answer type is responsive to the final question type. "How" → method/process, not entity. "How many times" → number, not entity. "What company succeeded X" → successor, not X itself.

**Why:** All 6 consistently-failing questions in the 19q diagnostic set have answers in the graph. The failures are not data gaps — they are strategy failures. Investigation confirmed:
- 820301 (22 plagues, Venice): Venice entity description says "22 plague outbreaks between 1361 and 1528." Direct edge `venice → plague in venice 1361 1528` with description "22 occurrences." Agent never checked entity_info.
- 136129 (Mantua Cathedral): Corpus chunk says "dedicated to Saint Peter." Entity_info on "mantua cathedral" would return this. Agent used entity_search (wrong surface for specific textual facts).
- 199513 (São José/Nazareth): Agent resolved a1 to "holy family" (group) instead of "Saint Joseph" (person). No metacognitive check caught the type mismatch.
- 354635 (Time Warner Cable): Correct a1 found (Adelphia), but agent submitted a1 as final answer instead of resolving a2.
- 71753 (1930): a1 resolved too broadly ("Middle East" vs specific named region).
- 754156 (dynasty/Portuguese): Submitted a1 intermediate answer ("Laos") for a question asking "how."

---

## References Reviewed

- `prompts/agent_benchmark_consolidated.yaml` — current prompt with wrong entity_info guidance
- `results/MuSiQue/er_graph/nx_data.graphml` — live graph; Venice node has "22 plague outbreaks" in description; edge `venice → plague in venice 1361 1528` with "22 occurrences" description
- `results/MuSiQue/corpus/Corpus.json` — chunk 267: "Plague occurred in Venice 22 times between 1361 and 1528"
- Conversation traces for all 6 failing questions (T003635Z) — agent never calls entity_info(profile) on resolved entities; no metacognitive check at atom completion
- `Core/MCP/tool_consolidation.py` — todo_write implementation; `answer` field currently optional string
- `digimon_mcp_stdio_server.py:2005` — `_validate_manual_todo_completion`; already validates evidence but can be extended to require doubt field metadata

---

## Files Affected

- `prompts/agent_benchmark_consolidated.yaml` (modify — three targeted changes to existing sections)
- No harness changes for Phase 1; Phase 2 adds `doubt` field support to todo_write schema

---

## Root Cause Analysis: The Graph Ontology

DIGIMON's ER graph (open-type extraction) contains:
- **Nodes**: Named entities with `entity_name`, `entity_type`, `description`. Descriptions are synthesized from multiple source chunks and CONTAIN attribute facts: counts, dates, qualifying characteristics.
- **Edges**: Typed relationships between entity pairs with `relation_name` and `description`. Edge descriptions encode relationship facts ("venice experienced 22 plague occurrences between 1361 and 1528").
- **NOT in the graph as directly addressable**: The numerical counts, date ranges, and descriptive phrases exist ONLY in entity/edge descriptions, not as separate addressable nodes. There is no node for "22" — the value lives in the description of the Venice→plague edge.

This means:
- Questions about ATTRIBUTES of an entity → check entity_info(profile) first, then traverse to named neighbors
- Questions about RELATIONSHIPS between entities → entity_traverse, relationship_search
- Questions about specific textual facts (dedicated to X, born in Y) → chunk_retrieve(text) is the reliable fallback when entity_info doesn't have it

The current prompt's guidance "entity_info is for navigation, not answers" is directly wrong for attribute questions. It should be "entity_info profile is your first check for facts about the entity itself; entity_traverse is for finding the entity's neighbors."

---

## Failure Family Taxonomy (general, not question-specific)

| Family | Pattern | Root cause | Fix |
|--------|---------|-----------|-----|
| ATTR_TRAVERSE | Agent traverses entity to find attribute value (count, date, characteristic) | Prompt says entity_info is for navigation only | Fix prompt: profile first for attribute questions |
| IEE_TYPE | Intermediate entity resolved to wrong semantic category (group vs person, macro-region vs specific region) | No self-check at atom completion | Add doubt field requirement |
| IEE_SCOPE | Intermediate entity resolved to correct category but too broad/narrow | Same | Same |
| PREMATURE_SUBMIT | Agent submits intermediate atom's answer as final answer | No answer type gate before submit | Add answer type self-check |
| TEXT_ENTITY_SEARCH | Agent uses entity_search for specific textual fact (e.g., "what is X dedicated to") | No guidance on when to prefer chunk_retrieve | Fix prompt: chunk_retrieve for textual descriptions |

---

## Implementation

### Phase 1: Prompt changes (no harness changes)

Three targeted changes to `prompts/agent_benchmark_consolidated.yaml`:

**Change 1: Fix entity_info guidance (## Key principles section)**

Current:
> `entity_info is for navigation, not answers. It returns summaries that may be incomplete.`

Replace with:
> `entity_info profile is for ATTRIBUTES OF the entity (counts, dates, descriptions, characteristics). Check it first when your question asks about a property of a known entity. entity_traverse is for NEIGHBORS — entities related to this one. Don't skip entity_info; descriptions often contain the answer directly.`

**Change 2: Add attribute-question routing step to the per-atom procedure (step 3)**

After step 3e (check edge_count), add:
> `e2. For attribute questions ("how many times", "when was", "what is X dedicated to", "what characteristic"): call entity_info(method="profile") on the resolved entity BEFORE traversal. The description often contains counts, dates, and qualifiers directly. Traversal finds neighbors, not attribute values.`

**Change 3: Add doubt field to atom completion + answer type check before submit**

Add to todo_write instructions:
> `When marking an atom status="done", add a "doubt" field: one sentence stating what could make this resolution wrong. Example: {"id": "a1", "status": "done", "answer": "holy family", "doubt": "holy family is a group; question says 'the person' — may need to narrow to Saint Joseph"}. This forces a semantic self-check before committing to an intermediate entity.`

Add to step 6 (verify before submitting):
> `d. Answer type matches final question type. If question asks "how" → answer is a method or process, not an entity. If question asks "what company succeeded X" → answer is X's successor, not X. If your answer is the same as an intermediate atom's answer, you likely stalled mid-chain.`

### Phase 2: todo_write schema extension (optional, if Phase 1 insufficient)

Add `doubt` as a first-class optional field to the todo_write schema in `Core/MCP/tool_consolidation.py`. Store it alongside `answer` in the todo state. Surface it in the linearized summary so the agent can see its own prior doubts when building on previous atoms.

---

## Acceptance Criteria

- [ ] Phase 1 prompt changes committed with `[Plan #27]` prefix
- [ ] 19q diagnostic rerun after Phase 1; ≥2 of {820301, 136129, 199513, 354635} improve without regression on stably-passing questions
- [ ] Improvement sustained across ≥2 runs (not single-run stochastic flip)
- [ ] Fix affects general failure family, not just the specific question: any question asking about an entity's attribute should benefit from the entity_info-first heuristic

---

## Open Questions

**Q1: Will entity_info(profile) actually return the full description or a truncated summary?**
Current linearization in tool_consolidation.py may truncate descriptions. CLAUDE.md prohibits truncation of evidence text. Verify that entity_info profile includes the full entity description, not a summary. If truncated, that's a separate bug (fix the linearizer, not the prompt).

**Q2: Is the doubt field better as prompt-only or harness-enforced?**
Prompt-only is cheaper and reversible. Harness enforcement (requiring doubt in todo_write schema) is stronger but may cause the agent to write boilerplate doubts. Start with prompt-only; promote to harness if the agent ignores the guidance.

**Q3: Does STAG_TURNS=6 give enough room for entity_info before traversal?**
Adding one more tool call (entity_info before traverse) increases call count per atom. At 20-call budget and STAG_TURNS=6, this should be fine, but verify that stagnation detection doesn't penalize entity_info calls as "no new evidence."

---

## Run History

| Date | Prompt version | LLM_EM | Notes |
|------|---------------|--------|-------|
| 2026-04-02 | Baseline (pre-Plan #27) | 57.9% (11/19) | Best prior run |
| 2026-04-03 | Plan #27 Phase 1 (entity_info-first + doubt field) | 42.1% (8/19) | REGRESSION — synthetic-summary trap: agent accepted "52" (total episodes) instead of season 5 count, "not stated" from entity_info instead of chunk_retrieve for Nazareth |
| 2026-04-03 | Plan #27 reverted (entity_info orientation-only, no doubt field) | pending | Verification run in progress |

## Latency Findings (2026-04-03, measured)

Added timing instrumentation to all 28 operator dispatches (`_timed_call` in
`tool_consolidation.py`). Results from 2 sentinel questions:

- **Operators**: 6–7 calls/question, 6–7s total
  - entity_search(string): ~2.5s avg (slowest)
  - chunk_retrieve(text): ~1.7s avg
  - entity_info/relationship_search: <1ms
- **LLM turns**: 47–48 per 2-hop question, 1.2–1.7s avg
- **LLM total per question**: 58–82s sequential

The "52s unaccounted gap" was LLM inference. Operators are ~20% of wall time.
Primary latency driver = LLM turn count, not operator speed.

Use `make timing` to inspect after any benchmark run.

## Notes

- All fixes are general improvements to retrieval strategy, not patches for specific questions.
- The entity ontology context (what the graph contains vs doesn't) should ideally be surfaced by the `resources()` tool or in the graph schema. Future work: expose node_fields and edge_fields from the graph build manifest as part of the resources() response.
- The `_validate_manual_todo_completion` validator (line 2005, digimon_mcp_stdio_server.py) is left untouched in this plan. It already does evidence-based validation. The doubt field is additive, not a replacement.
- **entity_info-first is architecturally correct** but needs more nuance: the entity description IS an answer surface, but it's a SYNTHESIZED aggregate — "52 total episodes" ≠ "12 season 5 episodes." The prompt must communicate this distinction before reintroducing entity_info as a primary answer surface. The current revert to "orientation only" is safe. Future version: "check entity_info for orientation, then use chunk_retrieve to get the specific value."
