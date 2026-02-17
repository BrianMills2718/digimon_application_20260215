# Graph Enrichment: Edge Types & Build-Time Attributes

## LLM-Extracted Attributes (during graph building)

Controlled by extraction mode and `GraphConfig` flags.

| Attribute | KG (`two_step`) | TKG (default) | RKG (`edge_keywords`) |
|-----------|:---:|:---:|:---:|
| Entity Name | Y | Y | Y |
| Entity Type | | Y | Y |
| Entity Description | | Y | Y |
| Relation Name | Y | Y | Y |
| Relation Description | | Y | Y |
| Relation Keywords | | | Y |
| Edge Weight (merge count) | Y | Y | Y |

**Config flags**: `extract_two_step`, `enable_entity_type`, `enable_entity_description`,
`enable_edge_name`, `enable_edge_description`, `enable_edge_keywords`, `max_gleaning`.

## Post-Extraction Edge Enrichment

Four edge types exist beyond LLM-extracted relations. All can be added to existing
graphs without rebuilding.

| Edge Type | Build-time Flag | Post-hoc Method | MCP Tool | `relation_name` | Cost |
|-----------|:-:|:-:|:-:|:-:|:-:|
| LLM-extracted | always | — | `graph_build_*` | (varies) | LLM |
| Chunk co-occurrence | `enable_chunk_cooccurrence` | `augment_graph_by_chunk_cooccurrence()` | `augment_chunk_cooccurrence` | `chunk_cooccurrence` | Free |
| Vector similarity | — | `augment_graph_by_similarity_search()` | — | `similarity` | Embedding |
| String/name similarity | — | `augment_graph_by_string_similarity()` | — | `name_similarity` | Free |

### Chunk Co-occurrence
Entities sharing a source chunk get implicit edges if they lack an explicit extracted relationship.
Weight defaults to 0.5. Inspired by EcphoryRAG's co-occurrence graph.
- Build-time: `config_overrides={"enable_chunk_cooccurrence": true}` on `graph_build_er`/`graph_build_rk`
- Post-hoc: `augment_chunk_cooccurrence(dataset_name, weight=0.5)` MCP tool

### Vector Similarity
Adds edges between entities whose description embeddings have cosine similarity above threshold.
Requires an entity VDB to be built first.
- Config: `similarity_threshold` (default 0.8), `similarity_top_k` (default 10)
- Code only: `BaseGraph.augment_graph_by_similarity_search(entity_vdb)`

### String/Name Similarity
Adds edges between entities with similar names via `SequenceMatcher`.
- Config: `string_similarity_threshold` (default 0.65), `string_similarity_min_name_length` (default 4)
- Code only: `BaseGraph.augment_graph_by_string_similarity()`

## Where Config Lives

- **GraphConfig**: `Config/GraphConfig.py` — all enrichment flags and thresholds
- **Config2.yaml**: `Option/Config2.yaml` — runtime defaults (add `enable_chunk_cooccurrence: true` under `graph:`)
- **Config overrides**: `Core/AgentSchema/graph_construction_tool_contracts.py` — Pydantic models for MCP tool validation
- **BaseGraph methods**: `Core/Graph/BaseGraph.py` — `augment_graph_by_*` implementations

## Not Yet Implemented (Literature Survey)

Techniques from the KG-RAG literature that could be added as enrichment steps:

**Quick wins (prompt/config changes):**
- Relationship strength scoring (LLM-rated 1-10 per edge) — LightRAG
- Entity importance scoring (LLM-rated 1-10 per entity) — EcphoryRAG
- Synonym edges (high-similarity pairs labeled SYNONYM) — HippoRAG 2
- Pre-computed centrality (PageRank/degree stored as node attrs) — HippoRAG

**Medium effort:**
- Coreference resolution ("the company" → "OpenAI") — LINK-KG, Graphusion
- Semantic entity dedup (embed-based merge of near-duplicates) — iText2KG
- Passage nodes in ERGraph (chunks as first-class graph members) — HippoRAG 2
- Confidence scores per edge — KARMA
- Claim/assertion extraction as node type — Microsoft GraphRAG
- Temporal metadata on edges (start/end dates) — Zep, Microsoft GraphRAG

See `docs/COMPETITIVE_ANALYSIS.md` for SOTA comparison and benchmark strategy.
