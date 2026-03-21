# Plan #4: Graph Build Rearchitecture

**Status:** Planned
**Type:** design
**Priority:** High
**Blocked By:** None
**Blocks:** Clean graph rebuild, benchmark reruns, manifest-driven tool gating

---

## Gap

**Current:** DIGIMON can build several graph types, but the entity-graph family is not modeled as one canonical schema with explicit projections. Tool applicability is only partially truth-driven, and old graph state has leaked into benchmark behavior.

**Target:** Rebuild the graph-build subsystem around a canonical entity-graph schema, explicit `KG` / `TKG` / `RKG` profiles, persisted build manifests, and manifest-driven retrieval/tool gating.

**Why:** DIGIMON is meant to be a controlled GraphRAG workbench: one system that can reproduce other GraphRAG build profiles, retrieval operators, and analysis methods as configurable components, while still letting an agent compose and compare those methods explicitly.

---

## References Reviewed

- `docs/GRAPH_ATTRIBUTE_MODEL.md` - canonical schema and JayLZhou mapping
- `docs/TOOL_CAPABILITY_MATRIX.md` - tool/build applicability contract
- `Core/Schema/GraphBuildManifest.py` - persisted build contract
- `Core/AgentTools/graph_construction_tools.py` - current build entrypoints
- `eval/graph_manifest.py` - benchmark gating from manifest truth
- `docs/adr/002-universal-graph-schema-and-extraction.md` - earlier schema direction

---

## Files Affected

> Initial design target. The eventual implementation should stay within this boundary unless a follow-up plan expands it.

- `docs/adr/004-graph-build-rearchitecture.md` (create)
- `docs/reports/2026-03-21_graphrag_rebuild_research.md` (create)
- `Config/GraphConfig.py` (modify)
- `Core/Schema/GraphBuildManifest.py` (modify)
- `Core/Graph/BaseGraph.py` (modify)
- `Core/Graph/ERGraph.py` (modify)
- `Core/Graph/RKGraph.py` (modify)
- `Core/Common/entity_name_hygiene.py` (modify)
- `Core/AgentTools/graph_construction_tools.py` (modify)
- `eval/graph_manifest.py` (modify)
- tests for schema/build/gating/rebuild verification (create/modify)

---

## Plan

### Phase 0: SOTA Grounding

1. Review current GraphRAG methods, codebases, and benchmark evidence.
2. Identify specific build/retrieval ideas worth copying, adapting, or rejecting.
3. Record findings in a dated research memo before implementation.

### Phase 1: Canonical Entity-Graph Schema

1. Split canonical identity from search normalization.
2. Add schema-guided extraction inputs so the build can run in open, guided, or stricter profile-driven modes instead of relying on unconstrained extraction alone.
3. Add first-class node fields for `canonical_name`, aliases, search keys, type, description, and provenance.
4. Add first-class edge fields for relation name, relation description, relation keywords, provenance, weight, and edge kind.
5. Keep tree and passage graphs out of this slice.

### Phase 2: Configurable Graph Profiles

1. Define explicit entity-graph profiles: `KG`, `TKG`, `RKG`.
2. Make profile selection config-driven.
3. Ensure a maximal raw build can materialize narrower projections without a second extraction pass when possible.
4. Preserve enough manifest/config detail that later method packs can declare which profile and schema mode they require.

### Phase 3: Build Manifest as Source of Truth

1. Extend the manifest so it is rich enough to drive all retrieval gating needed for the entity-graph family.
2. Make every entity-graph build emit a manifest that is benchmark- and MCP-consumable.
3. Keep fail-loud behavior when a build is incomplete or undocumented.

### Phase 4: Retrieval/Tool Capability Gating

1. Finish manifest-driven benchmark filtering.
2. Apply the same logic to MCP tool exposure once the existing dirty MCP worktree conflict is resolved.
3. Remove remaining ad hoc capability guesses.
4. Make query-mode exposure truthful to the built artifacts so named modes such as `basic`, `local`, `global`, and `hybrid` can be defined on top of actual capabilities rather than prompt convention alone.

### Phase 5: Thin Vertical Rebuild

1. Rebuild one target corpus, starting with MuSiQue.
2. Validate schema quality on known-bad entities and relations.
3. Run a small fixed-graph sanity batch.
4. Only after that, resume adaptive-vs-baseline evaluation.

---

## Required Tests

### New Tests (TDD)

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_graph_build_manifest.py` | `test_*` | schema/profile/manifest correctness |
| `tests/unit/test_eval_graph_manifest.py` | `test_*` | benchmark gating from manifest truth |
| `tests/unit/test_entity_name_hygiene.py` | existing + new cases | canonical-name/search-key behavior |
| `tests/unit/test_graph_projection.py` | `test_*` | profile materialization from canonical raw graph |

### Existing Tests (Must Pass)

| Test Pattern | Why |
|--------------|-----|
| `tests/unit/test_graph_capabilities.py` | config/capability drift remains blocked |
| `tests/unit/test_graph_node_validation.py` | invalid entity IDs remain rejected |
| `tests/unit/test_entity_string_search.py` | entity search quality remains protected |

---

## Acceptance Criteria

- [ ] DIGIMON can describe the entity graph as one canonical schema plus named profiles
- [ ] entity-graph extraction can run with explicit schema guidance instead of only open-ended extraction
- [ ] `KG`, `TKG`, and `RKG` are config-driven and machine-readable
- [ ] build manifests truthfully drive benchmark gating
- [ ] MuSiQue can be rebuilt from the new entity-graph path
- [ ] known entity-hygiene regressions stay fixed
- [ ] fixed-graph sanity batch uses only manifest-applicable tools
- [ ] the rebuild leaves a truthful contract for later named method packs and query modes
- [ ] docs and ADRs are updated to match the rebuilt architecture

---

## Notes

- Do not combine this with a storage-backend migration in the first slice.
- Do not rebuild tree or passage graphs in the first slice.
- Do not spend time on legacy manifest backfill unless a specific no-rebuild migration is later approved.
