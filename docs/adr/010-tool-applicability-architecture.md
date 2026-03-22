# ADR-010: Separate Build Capabilities, Runtime Resources, and Operator Requirements for Tool Applicability

**Status**: Accepted
**Date**: 2026-03-22

## Context

Plan #4 has already established two important directions:

- DIGIMON should treat the graph build manifest as the source of truth for what
  a graph artifact actually contains
- DIGIMON should expose retrieval tools truthfully instead of guessing from
  filenames, legacy flags, or whichever resources happened to be loaded

But the current applicability model is still underspecified. In practice, three
different concerns are being conflated:

1. **Build truth**
   - what topology, fields, provenance, and derived artifacts were produced by a
     graph build
2. **Runtime truth**
   - what graph objects, VDBs, chunk stores, sparse matrices, and community
     data are actually loaded and available in the current process
3. **Operator semantics**
   - what a tool fundamentally requires in order to be valid, and what only
     improves result quality

This ambiguity is already causing design drift:

- `relationship_vdb_search` depends on both a built relationship VDB and a
  loaded relationship VDB
- `entity_profile` can still be useful without descriptions, so descriptions are
  not a hard applicability requirement
- `chunk_text_search` is corpus-backed retrieval and should not be hidden just
  because an entity graph is minimal
- some existing capability docs overstate requirements, for example treating
  direct graph PPR as if it required sparse propagation artifacts

If DIGIMON keeps adding ad hoc manifest checks without resolving these
boundaries first, it will encode incidental implementation details instead of a
clean reproducible contract.

## Decision

Tool applicability in DIGIMON is a three-plane decision:

1. **Build capabilities**
   - Persisted in the graph build manifest
   - Describe what the artifact contains
   - Examples: topology kind, node fields, edge fields, provenance flags,
     built VDB artifacts, sparse matrices, community reports
2. **Runtime resources**
   - Exposed by runtime context or loader state
   - Describe what is available now
   - Examples: graph loaded, doc chunks loaded, entity VDB loaded,
     relationship VDB loaded, sparse matrices loaded
3. **Operator requirement contract**
   - Declared by the tool/operator definition itself
   - Split into:
     - hard requirements
     - soft quality preferences

Applicability is determined by evaluating all three planes together.

### Applicability Statuses

DIGIMON will use three applicability outcomes:

- **`available`**
  - all hard requirements are satisfied
- **`degraded`**
  - all hard requirements are satisfied, but one or more soft preferences are
    missing
- **`unavailable`**
  - one or more hard requirements are missing

### Hard vs Soft Rules

Hard requirements are conditions without which the tool is not truthful to run.
Examples:

- wrong topology family
- missing required provenance
- required VDB artifact not built
- required runtime resource not loaded

Soft preferences affect quality, ranking strength, or preview richness but do
not invalidate the tool. Examples:

- `entity_profile` having descriptions instead of only names/types
- `relationship_vdb_search` having rich relation descriptions and keywords
  rather than only terse relation names
- `entity.link` having high-quality aliases/search keys rather than only exact
  names

### Manifest Boundary

The build manifest is authoritative for **build truth only**.

It must describe:

- topology
- graph profile
- node and edge fields
- schema contract
- derived artifacts that were produced
- provenance and enrichment flags

It must **not** claim:

- whether a resource is currently loaded in memory
- whether a runtime preload step succeeded
- whether a particular process chose to expose a tool

### Runtime Boundary

Runtime state is separate from the manifest.

Runtime capability checks should answer questions such as:

- is the graph loaded?
- are doc chunks available for chunk recovery?
- is the entity/relationship/chunk VDB loaded?
- are sparse matrices loaded?

Loader failures or missing preload steps are runtime issues. They do not change
what the build produced.

### Operator Contract Boundary

Each operator or MCP tool should own a typed applicability contract that can
express:

- required topology families
- required manifest fields
- required manifest artifacts
- required runtime resources
- soft quality preferences

Benchmark harnesses and MCP exposure must consume that same contract rather
than maintaining independent hand-written rule sets.

### Policy Separation

Applicability evaluation and exposure policy are separate concerns.

The shared evaluator returns:

- status: `available` | `degraded` | `unavailable`
- missing hard requirements
- missing soft preferences
- human-readable reasons

Callers then decide what to do:

- benchmark filtering should hide `unavailable` tools
- MCP discovery should hide `unavailable` tools and may expose `degraded` tools
  with an explicit warning/reason surface
- named benchmark modes or method packs may impose stricter policies on top of
  the shared evaluator

## Consequences

### Positive

- DIGIMON can gate tools truthfully without flattening build truth and runtime
  state into one ambiguous notion of "capability."
- Tool exposure becomes auditable and explainable.
- The same operator can stay available on a minimal graph while clearly
  reporting degraded quality when richer attributes are absent.
- Benchmark filtering and MCP exposure can share one evaluator instead of
  drifting apart.

### Negative

- DIGIMON needs one more typed layer before more gating code should be added.
- Some existing docs and assumptions must be corrected because they currently
  overstate or misclassify operator requirements.

### Constraints

- Do not encode runtime-loaded state into the persisted build manifest.
- Do not hide a tool just because a preferred field is missing if the tool is
  still semantically valid.
- Do not let benchmark filtering and MCP exposure invent separate applicability
  rules.
- Do not treat composition/input-slot validity as the same thing as
  build/runtime applicability; those are separate checks.

