# Graph Attribute Model

This document defines the intended graph-build model for DIGIMON and maps it to the graph taxonomy used in JayLZhou GraphRAG.

The goal is simple:

- build one truthful, maximal raw representation for the entity-graph family
- derive narrower projections from that representation when a method only needs a subset
- treat tree and passage graphs as separate topologies, not as attribute subsets of the entity graph

## Why This Exists

Today the repo has the right ingredients but not a single source of truth:

- `GraphConfig` already exposes build toggles like `enable_entity_type`, `enable_entity_description`, `enable_edge_description`, `enable_edge_name`, `enable_edge_keywords`, `enable_chunk_cooccurrence`, and `use_community`
- the graph builders persist some of those attributes, but not all of them consistently
- tool exposure is only partially aware of what was actually built

Before more graph benchmarking, DIGIMON needs a stable attribute model and a build manifest that says what exists.

This document now also follows ADR-013:

- choose representation by operator utility and benchmark reasoning role
- do not materialize every detailed phrase as a node
- do not leave answer-critical facts only as buried description text when
  direct addressing is required

## JayLZhou Mapping

JayLZhou GraphRAG groups graphs into these families:

| JayLZhou Type | Core Idea | DIGIMON Equivalent |
|---|---|---|
| Chunk Tree | hierarchy over chunk content and summaries | `tree_graph`, `tree_graph_balanced` |
| Passage Graph | passages as nodes, linked by shared entities or relations | `passage_graph` |
| KG | entity/relation graph with names and weights | `er_graph` with minimal attributes |
| TKG | KG plus entity/edge descriptions and types | `er_graph` or `rkg_graph` with rich attributes enabled |
| RKG | TKG plus relation keywords | `er_graph` or `rkg_graph` with keywords enabled |

Important constraint:

- `KG`, `TKG`, and `RKG` are attribute-profile variants of the same entity-graph family
- `tree_graph` and `passage_graph` are different topologies and still need their own builds

## Current Persisted Entity-Graph Surface

The current entity-graph merge/persist path stores these core node and edge fields:

### Nodes

| Field | Current Meaning |
|---|---|
| `entity_name` | current node identity key |
| `entity_type` | optional type string |
| `description` | optional description text |
| `source_id` | chunk provenance, currently stored as merged chunk ids |

### Edges

| Field | Current Meaning |
|---|---|
| `src_id` / `tgt_id` | edge endpoints |
| `relation_name` | optional relation label |
| `description` | optional edge description |
| `keywords` | optional relation keywords |
| `weight` | numeric edge weight |
| `source_id` | chunk provenance, currently merged chunk ids |

This is enough for a first-pass KG/TKG/RKG family, but it is not yet the right canonical schema.

## Canonical Entity-Graph Schema

This is the target raw schema for DIGIMON entity graphs.

### Node Fields

| Field | Required | Why It Exists |
|---|---|---|
| `entity_id` | yes | stable internal node key |
| `canonical_name` | yes | human-readable canonical label |
| `aliases` | yes | alternate names, spelling variants, transliterations |
| `search_keys` | yes | normalized lookup keys used by search and linking |
| `entity_type` | optional | type/category for typed retrieval and filtering |
| `entity_description` | optional | text summary used by TF-IDF, embeddings, and inspection |
| `source_chunk_ids` | yes | chunk-level provenance |
| `source_doc_ids` | preferred | document-level provenance |
| `attributes` | optional | ontology-specific or domain-specific node fields |
| `build_profile` | preferred | which build variant/materialization created this node |

### Edge Fields

| Field | Required | Why It Exists |
|---|---|---|
| `edge_id` | preferred | stable edge identity |
| `src_id` / `tgt_id` | yes | endpoints |
| `relation_name` | optional | terse relation label for KG/RKG style retrieval |
| `relation_description` | optional | richer relation text for TKG/RKG and relation VDB |
| `relation_keywords` | optional | keyword-enriched retrieval signal |
| `weight` | yes | confidence / occurrence / scoring weight |
| `source_chunk_ids` | yes | chunk-level provenance |
| `source_doc_ids` | preferred | document-level provenance |
| `edge_kind` | preferred | `extracted`, `cooccurrence`, `synonym`, `ontology`, etc. |
| `attributes` | optional | ontology-specific or domain-specific edge fields |

### Derived Artifacts

The graph itself is not the full build product. DIGIMON also needs artifact-level metadata for:

- `entity_vdb`
- `relationship_vdb`
- `chunk_vdb`
- sparse matrices for entity→relationship and relationship→chunk propagation
- community reports
- co-occurrence enrichment
- synonym/link edges
- graph-centrality artifacts

## First-Principles Representation Policy

The graph should contain the smallest amount of structure that unlocks the
retrieval/composition behaviors the benchmark actually needs.

### Use a Node When

- the fact/concept can act as a seed, target, or bridge
- it recurs across chunks or documents
- traversal, linking, PPR, or subgraph extraction should operate on it
- evidence about it must be merged from multiple places

### Use an Edge When

- the relation between two addressable nodes is the main retrieval unit
- path composition or relation traversal matters
- relation ranking/aggregation matters more than independent identity

### Use an Attribute When

- the value mainly qualifies a node or edge
- it is mostly used for filtering, sorting, comparison, or rendering
- it usually does not need independent graph navigation

Important DIGIMON constraint:

- an attribute is only a good choice if the operator surface can actually use it

### Use Chunk-Only Evidence When

- the fact is local to one chunk
- graph structure adds little compositional value
- chunk retrieval can recover it reliably
- the fact is mainly support text rather than reusable structure

### Design Test

For any proposed representation, ask:

1. What benchmark reasoning pattern requires this fact?
2. Which operator family must be able to act on it?
3. What is the minimal representation that makes that possible?
4. If left only in descriptions, is there still a reliable path to full evidence
   and answer use?

## Build Profiles

For the entity-graph family, DIGIMON should support these named projections:

| Profile | Required Node Fields | Required Edge Fields |
|---|---|---|
| `KG` | `canonical_name`, `source_chunk_ids` | `relation_name`, `weight`, `source_chunk_ids` |
| `TKG` | `canonical_name`, `entity_type`, `entity_description`, `source_chunk_ids` | `relation_name`, `relation_description`, `weight`, `source_chunk_ids` |
| `RKG` | TKG fields | TKG fields plus `relation_keywords` |

Recommendation:

- build the entity graph once in a maximal raw form
- materialize `KG`, `TKG`, and `RKG` projections from that build
- do not rebuild from scratch just to drop fields unless the extraction prompts themselves differ

## What Can Be Shared vs Rebuilt

### Shared via Projection

These can be derived from one maximal entity-graph build:

- KG view
- TKG view
- RKG view
- method-specific text views used for entity or relation embeddings

### Requires Separate Topology Build

These are not attribute subsets of the entity graph:

- `passage_graph`
- `tree_graph`
- `tree_graph_balanced`

Those need their own build path and their own manifest section.

## Required Build Manifest

Every graph build should persist a machine-readable manifest beside the artifacts.

Important boundary:

- the manifest records what the build produced
- the manifest does not record whether those artifacts are currently loaded in a
  live process
- runtime-loaded resources belong to a separate applicability surface

Suggested fields:

```json
{
  "dataset_name": "MuSiQue",
  "topology_kind": "entity_graph",
  "graph_profile": "RKG",
  "node_fields": ["canonical_name", "entity_type", "entity_description", "source_chunk_ids"],
  "edge_fields": ["relation_name", "relation_description", "relation_keywords", "weight", "source_chunk_ids"],
  "artifacts": {
    "entity_vdb": true,
    "relationship_vdb": true,
    "chunk_vdb": true,
    "sparse_matrices": true,
    "communities": false,
    "cooccurrence_edges": true,
    "centrality_scores": true
  },
  "identity_strategy": {
    "canonical_name_mode": "unicode_preserving",
    "search_key_mode": "normalized_plus_ascii_alias"
  }
}
```

The manifest is the source of truth for the **build side** of tool gating and
benchmark-mode tool exposure. Runtime availability must be evaluated
separately.

## Current Gaps

These are known current-state gaps, not theoretical issues:

- node identity still over-relies on cleaned strings instead of a canonical-name plus search-key split
- build outputs are not described by a persisted manifest
- capability flags are partially inferred and not yet fully truthful
- description-related capabilities are currently overstated for some builds
- the repo does not yet provide first-class projection/materialization of `KG` / `TKG` / `RKG` views

## Design Rules Going Forward

1. The entity graph should have one canonical raw schema.
2. `KG`, `TKG`, and `RKG` are projections, not separate conceptual systems.
3. Tree and passage graphs are separate topologies.
4. Tool exposure must be driven by the persisted build manifest, not guesses.
5. A benchmark run must record which graph profile and artifacts were actually available.
