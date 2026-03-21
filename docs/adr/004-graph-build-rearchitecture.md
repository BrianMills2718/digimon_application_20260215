# ADR-004: Rebuild DIGIMON Around a Canonical Entity-Graph Architecture

**Status**: Proposed
**Date**: 2026-03-21

## Context

DIGIMON currently has enough graph-building capability to run experiments, but not enough architectural clarity to support repeatable GraphRAG reproduction.

The actual product goal is broader than "build one good graph." In plain language:

DIGIMON should be a controlled GraphRAG laboratory. It should be able to reproduce other systems' graph-build profiles, retrieval operators, and analysis methods as configurable components, while still making those components explicit enough that an agent can compose, compare, and critique them.

Three architecture problems currently block that goal:

1. The entity-graph family is not modeled as one canonical schema with explicit `KG` / `TKG` / `RKG` projections.
2. Tool availability and benchmark behavior have historically depended on partial guesses rather than a persisted build contract.
3. Legacy graph state and string-normalization shortcuts have contaminated build quality and evaluation truthfulness.

## Decision

Rebuild the graph-build subsystem around a canonical entity-graph architecture instead of adding more compatibility layers to the legacy build path.

This decision has five parts:

1. **Canonical entity graph first**
   - Treat the entity graph as the primary rebuild target.
   - Represent `KG`, `TKG`, and `RKG` as named profiles over that family.
   - Support schema-guided extraction so profile richness is a build contract, not just a post-hoc interpretation of open-ended extraction.

2. **Topology separated from profile**
   - `tree_graph` and `passage_graph` remain separate topologies.
   - They are not treated as simple attribute subsets of the entity graph.

3. **Manifest as source of truth**
   - Every graph build must emit a persisted build manifest.
   - Tool exposure and benchmark gating must consume that manifest instead of re-inferring capabilities from scattered config flags and filenames.
   - Later named method packs and query modes must declare their required manifest capabilities explicitly.

4. **Thin vertical rebuild**
   - Rebuild one corpus end-to-end, starting with MuSiQue.
   - Do not combine the first slice with a storage-backend migration or a tree/passage redesign.

5. **No legacy compatibility work by default**
   - Do not spend time on legacy manifest backfill or broader migration support unless explicitly approved later.
   - Existing undocumented graph artifacts are treated as legacy state, not as architecture to preserve.

## Consequences

### Positive

- DIGIMON becomes a more truthful platform for reproducing and comparing GraphRAG methods.
- Retrieval/tool exposure becomes auditable from persisted build artifacts.
- Benchmark results become easier to interpret because graph richness is explicit.
- Schema work, entity hygiene, and retrieval gating all align under one contract.

### Negative

- Existing legacy graphs may need to be rebuilt before they can participate in the new benchmark path.
- The first rebuild will take time before it improves benchmark results.
- Tree and passage graph work is intentionally deferred, which narrows short-term scope.

### Constraints

- The first rebuild slice should not include a database/storage migration.
- The first rebuild slice should not include new adaptive-routing features.
- The first rebuild slice should stay focused on the entity-graph family, manifest truth, and fixed-graph retrieval quality.
