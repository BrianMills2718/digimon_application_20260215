# Tool Capability Matrix

This document defines when a retrieval operator or MCP tool is applicable for a given graph build.

The rule is strict:

- if a build does not provide the required topology, attributes, or derived artifacts, the corresponding tool should not be exposed

This is the contract that should drive both:

- MCP tool exposure
- benchmark-mode tool filtering

## Capability Model

Tool applicability depends on three different things:

1. **Topology**
- entity graph
- passage graph
- tree graph

2. **Attributes**
- entity types
- entity descriptions
- relation names
- relation descriptions
- relation keywords
- chunk provenance

3. **Derived Artifacts**
- entity VDB
- relationship VDB
- chunk VDB
- sparse propagation matrices
- community reports

The current code only gates some of these. The target behavior is to gate all of them from the persisted build manifest.

## Operator-Level Matrix

| Operator / Tool Family | Requires Topology | Requires Attributes | Requires Derived Artifacts | Notes |
|---|---|---|---|---|
| `entity_string_search` / `entity_profile` / `entity_neighborhood` | entity graph | `canonical_name` at minimum; `entity_description` improves previews | none | core local graph tools |
| `entity.vdb` / `entity_vdb_search` | entity graph | searchable entity text fields | `entity_vdb` | hide if entity VDB not built |
| `entity.link` | entity graph | `canonical_name`, aliases/search keys | `entity_vdb` | quality depends on alias/search-key quality |
| `entity.ppr` | entity graph | none beyond graph connectivity | sparse matrices or equivalent PPR artifact | do not expose on tree/passage builds unless separately implemented |
| `entity.tfidf` | entity graph | `entity_description` or equivalent searchable entity text | TF-IDF index or build-time text matrix | weak without descriptions |
| `relationship.onehop` | entity graph | none beyond connected edges | none | requires entity graph edges |
| `relationship.vdb` / `relationship_vdb_search` | entity graph | relation text fields, ideally `relation_description` or `relation_keywords` | `relationship_vdb` | not useful if edges only have empty relation text |
| `relationship.score_agg` | entity graph | relation provenance structure | sparse matrices | used after `entity.ppr` |
| `chunk.from_relation` | entity graph | edge `source_chunk_ids` provenance | none | hide if relationship→chunk provenance is missing |
| `chunk.occurrence` | entity graph | node `source_chunk_ids` provenance | none | hide if entity provenance is missing |
| `chunk.aggregator` | entity graph | relationship and chunk linkage | sparse matrices | requires entity→relationship and relationship→chunk matrices |
| `chunk.text_search` | any corpus-backed build | chunk text | text-search index | this is corpus retrieval, not graph-specific |
| `chunk.vdb` / `chunk_vdb_search` | any corpus-backed build | chunk text | `chunk_vdb` | independent of graph richness |
| `subgraph.khop_paths` / `subgraph.steiner_tree` | entity graph | connected entity graph | none or graph algorithm support | not applicable to tree-only or passage-only builds unless redefined |
| `subgraph.agent_path` | entity graph | same as subgraph extraction | LLM plus subgraph extraction support | only expose if subgraph tools are available |
| `community.from_entity` / `community.from_level` | entity graph | cluster/community memberships or reports | `communities` | hide if community detection was not run |
| tree summarization / layer tools | tree graph | tree nodes and levels | tree artifacts | tree-only |
| passage traversal / passage-neighborhood tools | passage graph | passage nodes and links | passage graph artifacts | passage-only |

## Benchmark Tooling Implications

The benchmark harness currently does some gating for:

- missing entity/relationship/chunk VDBs
- missing sparse matrices
- explicit `baseline` and `fixed_graph` mode tool subsets

That is a start, but it is incomplete.

The benchmark harness should also gate on:

- missing entity provenance for `chunk.occurrence`
- missing relationship provenance for `chunk.from_relation`
- missing relation text for relationship-search tools
- missing communities for community tools
- graph topology mismatch for tree/passage-only tools

## MCP Exposure Rules

These are the recommended exposure rules for user-facing tools.

### Always Safe

These can be shown whenever their backing artifact exists:

- `chunk_text_search`
- `chunk_vdb_search`
- `chunk_get_text_by_chunk_ids`
- `submit_answer`

### Entity-Graph Core

Show only for entity-graph builds:

- `entity_string_search`
- `entity_profile`
- `entity_neighborhood`
- `entity_onehop`
- `relationship_onehop`

### Rich-Relation Tools

Show only when the build has usable relationship text or keywords plus the relevant artifact:

- `relationship_vdb_search`
- `chunk_from_relationships`
- any relation-keyword-driven tool

### Propagation / Graph-Scoring Tools

Show only when sparse propagation artifacts exist:

- `entity_ppr`
- `relationship_score_aggregator`
- `chunk_aggregator`

### Community Tools

Show only when community reports exist:

- `community_from_entity`
- `community_from_level`

## Current Gaps

Current implementation does not yet fully satisfy this contract:

- `OperatorDescriptor` only models a few coarse requirements
- `list_operators` exposes those coarse flags but not build-manifest truth
- `BaseGraph.capabilities` still overstates some capabilities, especially description-related ones
- benchmark-mode filtering does not yet use a persisted build manifest

## Required Next Step

Introduce a `GraphBuildManifest` and make both MCP tool registration and benchmark tool filtering depend on it.

Suggested manifest sections:

- `topology_kind`
- `graph_profile`
- `node_fields`
- `edge_fields`
- `artifacts`
- `provenance`
- `enrichments`

Without that manifest, tool exposure remains partially guess-based.
