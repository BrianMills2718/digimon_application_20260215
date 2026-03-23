# Plan #13: Evidence-Backed Benchmark Anchor Resolution

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Trustworthy multi-hop anchor selection on audited MuSiQue cases

---

## Gap

**Current:** The live benchmark surface already has `entity_select_candidate`,
`entity_profile`, and `search_then_expand_onehop`, but the selector only fails
on coarse-type mismatches. It does not have an explicit contract for
“multiple plausible anchors remain; do not commit yet.” Meanwhile the current
benchmark prompt does not clearly define when an anchor atom is resolved.

**Target:** Add an explicit ambiguity-safe anchor-selection path that can return
`needs_revision` for unresolved anchor choices, thread it through the composite
search helper, and update the benchmark prompt contract so long-chain anchor
atoms are not treated as solved until the canonical entity is selected and
profiled.

**Why:** Plan #12 shows that at least one hard MuSiQue miss is caused by weak
anchor commitment before the chain begins. Fixing that with a truthful selector
contract is simpler and more general than adding more ontology.

---

## References Reviewed

- `docs/plans/12_musique_representation_audit.md` - benchmark-grounded audit plan
- `~/projects/investigations/Digimon_for_KG_application/2026-03-22-musique-representation-audit-slice-01.md` - first audited MuSiQue slice
- `digimon_mcp_stdio_server.py:3003-3270` - current `entity_select_candidate`
- `digimon_mcp_stdio_server.py:4305-4450` - current `search_then_expand_onehop`
- `digimon_mcp_stdio_server.py:6366-6420` - current `todo_write` benchmark control contract
- `prompts/agent_benchmark_hybrid.yaml` - live benchmark prompt
- `prompts/agent_benchmark_codex_compact.yaml` - compact benchmark prompt
- `eval/run_agent_benchmark.py:213-379` - live benchmark tool surface and contracts
- `specs/agent_spec.benchmark.yaml` - stale benchmark spec surface (not authoritative for this slice, but relevant drift)

---

## Files Affected

- `docs/plans/13_benchmark_anchor_resolution.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `digimon_mcp_stdio_server.py` (modify)
- `prompts/agent_benchmark_hybrid.yaml` (modify)
- `prompts/agent_benchmark_codex_compact.yaml` (modify)
- `tests/unit/test_entity_select_candidate.py` (create)
- `tests/unit/test_representation_policy_prompt_contracts.py` (modify)

---

## Plan

## Progress

- 2026-03-22: Plan #12 identified the first implementation lane: audited
  failures point to premature anchor commitment rather than missing ontology.
- 2026-03-22: Code review confirmed the live benchmark surface already contains
  the right primitives (`entity_select_candidate`, `entity_profile`,
  `search_then_expand_onehop`), but their contract is too weak for long-chain
  anchor resolution.
- 2026-03-22: The thin implementation slice is in place: `entity_select_candidate`
  now supports an explicit ambiguity-safe mode, `search_then_expand_onehop` can
  pass that stricter selection contract through, and the benchmark prompts now
  define when an anchor atom is actually resolved.
- 2026-03-22: Deterministic verification passed for the static slice:
  `py_compile` succeeded and the unit regression slice
  (`test_entity_select_candidate.py`,
  `test_representation_policy_prompt_contracts.py`,
  `test_benchmark_tool_modes.py`) passed `10/10`.
- 2026-03-22: The planned one-question benchmark smoke is currently blocked by
  environment, not by selector logic. Running
  `eval/run_agent_benchmark.py --backend direct` on the audited anchor-failure
  ID fails during DIGIMON tool import with `ModuleNotFoundError: faiss` in the
  project venv, so no agent-loop evidence was produced yet.

### Steps

1. Add an explicit ambiguity-safe selector mode.
   - Extend `entity_select_candidate` with an opt-in contract for
     unambiguous anchor resolution.
   - When enabled, return `status="needs_revision"` instead of silently picking
     a winner if multiple plausible top candidates remain too close.

2. Thread the stricter mode through the composite helper.
   - Allow `search_then_expand_onehop` to pass atom/task context and the new
     ambiguity-safe parameters to `entity_select_candidate`.
   - Keep the default behavior backward-compatible for non-benchmark callers.

3. Tighten the benchmark prompt contract.
   - Define that an anchor atom is not resolved until the agent has:
     - one canonical entity ID
     - profile/evidence confirming it fits the atom
   - Tell the agent to use `entity_select_candidate` or
     `search_then_expand_onehop` before chaining from descriptive anchors.

4. Lock the contract with deterministic tests.
   - Unit-test ambiguous candidate rejection and non-ambiguous selection.
   - Add prompt-contract tests for the new benchmark guidance.

5. Prove on the smallest benchmark-facing slice.
   - After unit tests pass, run a one-question smoke on an audited anchor-failure
     case if the changed prompt/tool contract is still the likely bottleneck.

---

## Required Tests

### New Tests (TDD)

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_entity_select_candidate.py` | `test_entity_select_candidate_requires_disambiguation_for_close_anchor_candidates` | ambiguity-safe mode returns `needs_revision` instead of silently picking a weak anchor |
| `tests/unit/test_entity_select_candidate.py` | `test_entity_select_candidate_allows_clear_anchor_winner` | ambiguity-safe mode still selects a clear winner |
| `tests/unit/test_representation_policy_prompt_contracts.py` | `test_hybrid_benchmark_prompt_requires_canonical_anchor_resolution` | hybrid prompt defines when an anchor is actually resolved |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_representation_policy_prompt_contracts.py` | prior representation-policy prompt guarantees must remain intact |
| `tests/unit/test_benchmark_tool_modes.py` | benchmark tool-surface expectations must remain stable |

---

## Acceptance Criteria

- [ ] `entity_select_candidate` has an explicit ambiguity-safe mode for anchor resolution
- [ ] ambiguity-safe mode returns `needs_revision` on close plausible anchor candidates instead of silently selecting one
- [ ] `search_then_expand_onehop` can use the stricter selection path
- [ ] benchmark prompts state that anchor atoms are not resolved until canonical selection is verified
- [ ] deterministic unit tests pass for both selector behavior and prompt contract
- [ ] if the one-question smoke is run, its outcome is recorded honestly as evidence, not assumed progress

---

## Notes

- Prefer strengthening existing tools over adding a new benchmark-only anchor tool.
- `specs/agent_spec.benchmark.yaml` is currently stale (`todo_update`/`todo_create`
  era). That drift is real, but syncing the spec is follow-up work unless it
  becomes necessary for this slice.
