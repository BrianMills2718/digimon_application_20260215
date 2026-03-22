# Tool Capability Matrix

This document defines when a retrieval operator or MCP tool is applicable for a
given DIGIMON build.

The important design correction is this:

- tool applicability is not just "what the build manifest says"
- tool applicability is the combination of:
  - what the build produced
  - what the runtime loaded
  - what the operator fundamentally requires

This contract should drive both:

- MCP tool exposure
- benchmark-mode tool filtering

## Applicability Model

### Plane 1: Build Capabilities

Build capabilities come from the persisted graph build manifest.

They answer questions such as:

- what topology was built?
- which node and edge fields exist?
- is entity or relationship provenance present?
- were entity/relationship/chunk VDB artifacts built?
- were sparse matrices built?
- were communities built?

The manifest is authoritative for what was produced, not for what is currently
loaded.

### Plane 2: Runtime Resources

Runtime resources come from live context and loader state.

They answer questions such as:

- is the graph loaded?
- are doc chunks available?
- is the entity VDB loaded?
- is the relationship VDB loaded?
- is the chunk VDB loaded?
- are sparse matrices loaded?

Runtime failures must not be encoded back into the manifest.

### Plane 3: Operator Requirement Contract

Each operator/tool should declare:

- hard build requirements
- hard runtime requirements
- soft quality preferences

Soft preferences improve result quality or preview richness, but do not make
the tool invalid.

## Applicability Outcomes

Applicability evaluation should return one of:

- **`available`**
  - all hard requirements are met
- **`degraded`**
  - all hard requirements are met, but one or more soft preferences are absent
- **`unavailable`**
  - one or more hard requirements are missing

The evaluator should also return explicit reasons, not just a boolean.

## Operator-Level Matrix

| Operator / Tool Family | Hard Build Requirements | Hard Runtime Requirements | Soft Quality Preferences | Notes |
|---|---|---|---|---|
| `entity_string_search` / `entity_profile` / `entity_neighborhood` | entity graph topology | graph loaded | entity descriptions, aliases/search keys | `entity_profile` remains valid without descriptions; richer fields improve previews |
| `entity.vdb` / `entity_vdb_search` | entity graph topology; `entity_vdb` artifact built | entity VDB loaded | descriptions, aliases/search keys, richer entity text | hide if the index was never built or is not loaded |
| `entity.link` | entity graph topology; `entity_vdb` artifact built | entity VDB loaded | aliases/search keys, canonical-name quality | valid with exact-name matching only, but quality degrades sharply |
| `entity.ppr` | entity graph topology | graph loaded | none | current operator uses direct graph PPR; sparse matrices are not a hard requirement |
| `entity.tfidf` | entity graph topology | graph loaded or entity text index loaded | entity descriptions or equivalent searchable entity text | should not be advertised as strong on builds with empty entity text |
| `relationship.onehop` | entity graph topology | graph loaded | relation names or descriptions | remains valid on minimal edge payloads |
| `relationship.vdb` / `relationship_vdb_search` | entity graph topology; `relationship_vdb` artifact built | relationship VDB loaded | relation descriptions, keywords, non-empty relation text | rich relation text improves semantic retrieval, but the hard requirement is the built/loaded index |
| `relationship.score_agg` | entity graph topology; sparse propagation artifact built | sparse matrices loaded; graph loaded | none | this is the real sparse-matrix-dependent relationship tool |
| `chunk.from_relation` | entity graph topology; relationship chunk provenance built | graph loaded; chunk/doc store available | relation names or descriptions for better ranking | hide if relationship provenance is absent |
| `chunk.occurrence` | entity graph topology; entity chunk provenance built | graph loaded; chunk/doc store available | none | hide if entity provenance is absent |
| `chunk.aggregator` | entity graph topology; sparse propagation artifact built | sparse matrices loaded; graph loaded | none | requires entity->relationship and relationship->chunk propagation surfaces |
| `chunk.text_search` | corpus-backed build or dataset prepared for chunk retrieval | chunk/doc store available | dedicated lexical index | this is corpus retrieval, not graph-richness retrieval |
| `chunk.vdb` / `chunk_vdb_search` | `chunk_vdb` artifact built | chunk VDB loaded | richer chunk text, titles, doc metadata | independent of entity-graph richness |
| `subgraph.khop_paths` / `subgraph.steiner_tree` | entity graph topology | graph loaded | well-connected graph, informative relation payloads | not applicable to passage-only or tree-only builds unless separately redefined |
| `subgraph.agent_path` | entity graph topology | graph loaded; LLM available | same preferences as other subgraph tools | should inherit availability from the subgraph extraction surface |
| `community.from_entity` / `community.from_level` | entity graph topology; `communities` artifact built | communities loaded | richer community summaries | hide if community detection was never run |
| `meta.pcst_optimize` | none beyond upstream entity/relationship artifacts already produced in the current run | none beyond normal operator execution | informative scores on upstream entities/relationships | this is a composition-stage optimizer, not a build-capability-gated retrieval surface |
| tree-specific layer/summarization tools | tree topology | tree graph loaded | summary text, layer metadata | tree-only |
| passage-specific traversal tools | passage topology | passage graph loaded | passage relation text, passage metadata | passage-only |

## Benchmark Implications

Benchmark filtering should use a shared applicability evaluator and then apply a
policy:

- hide `unavailable` tools
- keep `degraded` tools unless the benchmark mode explicitly demands a stricter
  policy
- continue to apply mode-level subsets such as `baseline` and `fixed_graph`

The benchmark harness should stop maintaining a separate hand-written notion of
"capability" once the shared evaluator exists.

## MCP Exposure Implications

MCP discovery should consume the same evaluator, but with a user-facing policy:

- hide `unavailable` tools
- expose `degraded` tools with explicit reasons when possible
- avoid pretending that a preferred field is a hard requirement if the tool can
  still run truthfully

## Current Gaps

Current implementation does not yet fully satisfy this contract:

- `OperatorDescriptor` does not yet model a full applicability contract
- benchmark filtering is split between manifest checks and runtime ad hoc checks
- MCP exposure does not yet consume the same applicability decision surface
- some existing docs overstate hard requirements instead of distinguishing hard
  requirements from soft quality preferences

## Required Next Step

Implement one shared applicability evaluator with typed inputs for:

- build manifest capabilities
- runtime-loaded resources
- operator requirement contract

That evaluator should return:

- `available` / `degraded` / `unavailable`
- missing hard requirements
- missing soft preferences
- human-readable reasons

Without that layer, DIGIMON will keep adding partial gating logic instead of a
clean architecture.
