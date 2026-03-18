# SOTA Patterns: KG-RAG Technique Survey

**Last Updated**: 2026-02-17

This document maps KG-RAG techniques from published papers to DIGIMON's implementation status.
For benchmark scores, see `COMPETITIVE_ANALYSIS.md`.

## Papers Reviewed

| Paper | Venue | Key Innovation |
|-------|-------|---------------|
| HippoRAG | NeurIPS 2024 | PPR spreading activation with IDF-weighted seeds |
| HippoRAG 2 | arXiv 2502.14802 | Passage nodes + synonym edges + incremental updates |
| EcphoryRAG | arXiv 2510.08958 | Dual chunk retrieval (entity-grounded + direct VDB), co-occurrence graph |
| LightRAG | EMNLP 2025 | Keyword-enriched relationships, relationship VDB |
| Microsoft GraphRAG | arXiv 2404.16130 | Community detection + hierarchical summaries |
| RAPTOR | ICLR 2024 | Recursive tree summarization for multi-granularity retrieval |
| StepChain | arXiv 2510.02827 | Step-by-step KG reasoning chains |
| HopRAG | arXiv 2502.12442 | Logical passage graph with multi-hop traversal |
| G-Retriever | NeurIPS 2024 | GNN-based subgraph retrieval |
| GNN-RAG | arXiv 2405.20139 | GNN node embeddings for dense retrieval |
| KG-Agent | arXiv 2402.11163 | Agent-driven KG exploration |
| KARMA | arXiv 2502.06472 | Multi-agent LLM KG enrichment |
| iText2KG | WISE 2024 | Incremental KG with embedding-based entity dedup |
| LINK-KG | arXiv 2510.26486 | LLM-driven coreference resolution before extraction |
| ArchRAG | arXiv 2502.09891 | Attributed community detection |

## Technique Inventory

### Graph Construction Techniques

| # | Technique | Papers | DIGIMON Status | Operator/Config |
|---|-----------|--------|---------------|-----------------|
| 1 | LLM entity+relation extraction | All | **Done** | `graph_build_er` via `DelimiterExtractionMixin` |
| 2 | Two-step extraction (NER then OpenIE) | GraphRAG | **Done** | `extract_two_step=True` config flag |
| 3 | Multi-pass gleaning | GraphRAG, LightRAG | **Done** | `max_gleaning=2-3` config flag |
| 4 | Keyword-enriched relationships | LightRAG | **Done** | `enable_edge_keywords=True` → RKGraph |
| 5 | Custom ontology-guided extraction | Domain KG papers | **Done** | `auto_generate_ontology` + `custom_ontology_path` |
| 6 | Relationship strength scoring (1-10) | LightRAG, GraphRAG | **Done** | Already in extraction prompt, parsed as `weight` |
| 7 | Coreference resolution | LINK-KG, Graphusion | **Missing** | Would be a pre-extraction NLP pass |
| 8 | Embedding-based entity deduplication | iText2KG | **Missing** | `entity.link` does retrieval-time linking, not build-time merge |
| 9 | Claim/assertion extraction | Microsoft GraphRAG | **Missing** | Would be a new node type alongside entities |
| 10 | Temporal metadata on edges | Zep, GraphRAG | **Missing** | No date fields in extraction prompt or schema |

### Graph Enrichment Techniques (post-build)

| # | Technique | Papers | DIGIMON Status | Method/Tool |
|---|-----------|--------|---------------|-------------|
| 11 | Chunk co-occurrence edges | EcphoryRAG, HippoRAG | **Done** | `enable_chunk_cooccurrence` flag, `augment_chunk_cooccurrence` MCP tool |
| 12 | Vector similarity edges | Various | **Done** | `augment_graph_by_similarity_search()` (code only) |
| 13 | String/name similarity edges | Various | **Done** | `augment_graph_by_string_similarity()` (code only) |
| 14 | Synonym edge detection | HippoRAG 2 | **Done** | `augment_graph_by_synonym_detection()` (code only, needs entity VDB) |
| 15 | Pre-computed centrality | HippoRAG, various | **Done** | `augment_graph_with_centrality()`, `augment_centrality` MCP tool |
| 16 | Community detection + summaries | GraphRAG | **Done** | `build_communities` MCP tool, Leiden algorithm |
| 17 | Entity importance scoring | EcphoryRAG | **Partial** | Post-hoc via centrality (#15); not in extraction prompt |
| 18 | Passage nodes in entity graph | HippoRAG 2, EcphoryRAG | **Missing** | PassageGraph exists as separate type, not integrated into ERGraph |
| 19 | Type hierarchy inference | KARMA | **Missing** | Entity types extracted but no IS_A hierarchy |
| 20 | GNN structural embeddings | GNN-RAG, G-Retriever | **Missing** | Requires PyG/DGL integration |
| 21 | Confidence/uncertainty scores | KARMA | **Missing** | Edge weight is merge count, not confidence |

### Query-Time Retrieval Techniques

| # | Technique | Papers | DIGIMON Status | Operator |
|---|-----------|--------|---------------|----------|
| 22 | Entity VDB search | All | **Done** | `entity.vdb_search` |
| 23 | Relationship VDB search | LightRAG | **Done** | `relationship.vdb_search` |
| 24 | PPR spreading activation | HippoRAG | **Done** | `entity.ppr` with IDF weighting |
| 25 | IDF-weighted entity scoring | HippoRAG | **Done** | `entity.tfidf` |
| 26 | Entity linking (query→graph) | HippoRAG, DALK | **Done** | `meta.extract_entities` → `entity.link` |
| 27 | Multi-hop graph traversal | HopRAG, DALK, ToG | **Done** | `entity.onehop`, `subgraph.khop_paths` |
| 28 | Iterative agent reasoning | ToG, KGP | **Done** | Loop operators + `entity.agent`, `relationship.agent` |
| 29 | Question decomposition | StepChain | **Done** | `meta.decompose_question` + `meta.synthesize_answers` |
| 30 | Subgraph optimization (PCST) | G-Retriever | **Done** | `meta.pcst_optimize` |
| 31 | LLM-based reranking | EcphoryRAG | **Done** | `meta.rerank` |
| 32 | Chunk text search (BM25/TF-IDF) | Various | **Done** | `chunk.text_search` |
| 33 | Chunk VDB search (embedding) | EcphoryRAG | **Done** | `chunk.vdb` operator + `chunk_vdb_build` / `chunk_vdb_search` MCP tools |
| 34 | Weighted centroid expansion | EcphoryRAG | **Missing** | Would be a new param on `entity.vdb_search` |
| 35 | Per-question adaptive operator composition | DIGIMON only | **Done** | Agent composes operators per-question via `list_operators` + `get_compatible_successors` — unique to us, no competitor has this |
| 36 | Multi-pipeline ensemble | DIGIMON only | **Possible** | Can run multiple methods and synthesize — untested |

### Architecture-Level Techniques

| # | Technique | Papers | DIGIMON Status | Notes |
|---|-----------|--------|---------------|-------|
| 37 | Composable typed operators | DIGIMON only | **Done** | 27 operators, 6 categories, machine-readable contracts |
| 38 | Multiple graph types on same corpus | DIGIMON only | **Done** | ER, RK, Tree, Passage, TreeBalanced |
| 39 | Incremental graph construction | iText2KG, HippoRAG 2 | **Partial** | Checkpoint/resume exists, but no "add documents" API |
| 40 | Recursive reasoning trace | DIGIMON design | **Design** | Phase 16 — reasoning traces as ER graphs |

## HippoRAG Deep Dive

### What HippoRAG Does (paper)

1. **Offline (build)**:
   - Standard NER extraction (OpenAI NER model)
   - Co-occurrence edges (entities in same passage get edges)
   - Synonym edges via embedding similarity
   - Store passages as graph nodes (bipartite entity-passage graph)

2. **Online (query)**:
   - NER on query → extract entities
   - Entity linking → map to KG nodes (embedding similarity + exact match)
   - **IDF-weighted PPR**: Rare entities (low IDF) get higher PersonalizedPageRank reset probability. This biases PPR toward informative entities rather than common ones.
   - Retrieve passages via PPR-ranked entities

### Our Implementation

**Pipeline**: `hipporag`-style operator chain
```
meta.extract_entities → entity.link → entity.ppr → chunk.aggregator
```

| HippoRAG Feature | DIGIMON Status | Gap |
|-------------------|---------------|-----|
| NER on query | `meta.extract_entities` | Done |
| Entity linking | `entity.link` (VDB similarity) | Done |
| IDF-weighted PPR | `entity.ppr` + `entity.tfidf` for weighting | Done |
| Co-occurrence edges | `enable_chunk_cooccurrence` (just added) | Done |
| Synonym edges | `augment_graph_by_synonym_detection()` (just added) | Done (code), not run on HotpotQA yet |
| Passage nodes in graph | Not integrated into ERGraph | Missing — PassageGraph is separate type |
| Sparse matrix chunk propagation | `chunk.aggregator` with `build_sparse_matrices` | Done |

### What We Haven't Done

- **Never benchmarked** the `hipporag` fixed pipeline on HotpotQA (agent freestyle only)
- **Passage nodes** not in ERGraph (HippoRAG's bipartite graph is different from our PassageGraph)
- **Synonym edges** not run on HotpotQA graph yet

## EcphoryRAG Deep Dive

### What EcphoryRAG Does

1. **Co-occurrence graph** (no LLM relation extraction — just shared-chunk edges)
2. **Dual chunk retrieval**: entity-grounded (via graph) + direct chunk VDB (embedding search)
3. **Weighted centroid expansion**: Instead of graph traversal, expand entity set via weighted average of entity embeddings
4. **Entity embeddings**: Encode `name + description` (we encode description alone, falling back to name)
5. **Post-retrieval reranking**: Cosine similarity against original query embedding

### DIGIMON Status vs EcphoryRAG

| Feature | DIGIMON | Gap |
|---------|---------|-----|
| Co-occurrence graph | `enable_chunk_cooccurrence` | Done |
| Chunk VDB (embedding) | `chunk.vdb` operator + `chunk_vdb_search` MCP tool | **Done** — dual retrieval ready |
| Weighted centroid expansion | Not implemented | **Missing** — would be new operator |
| Entity embeddings (name+desc) | Embed description or name | **Minor gap** — easy prompt change |
| Cosine reranking | `meta.rerank` (LLM-based, heavier) | Different approach, ours is more expensive but smarter |

## Quick Wins Remaining

Techniques that could improve benchmark scores with minimal effort:

1. **Run `hipporag` fixed pipeline** on HotpotQA — compare against agent freestyle
2. ~~**Add chunk VDB**~~ — **Done**. `chunk.vdb` operator + `chunk_vdb_build` / `chunk_vdb_search` MCP tools
3. **Build chunk VDB on HotpotQA** and benchmark with dual retrieval (text_search + vdb_search)
4. **Run synonym detection** on HotpotQA graph — needs entity VDB, already have the code
5. **Entity embedding enrichment** — concatenate name+description for entity VDB build
6. **Benchmark on 2WikiMultiHopQA** — our 200q HotpotQA isn't directly comparable to most papers

## References

See `COMPETITIVE_ANALYSIS.md` for benchmark scores and `GRAPH_ENRICHMENT.md` for edge type details.
