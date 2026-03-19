# DIGIMON: Composable Graph RAG for Multi-Hop Question Answering

## What It Is

DIGIMON is a knowledge-graph-based retrieval-augmented generation system with 28 typed operators that can be freely composed into retrieval pipelines. Unlike fixed-pipeline GraphRAG systems (HippoRAG, LightRAG, GraphRAG), DIGIMON adapts its retrieval strategy per question.

## Architecture

```
Documents ──► Graph Build ──► Knowledge Graph + VDBs ──► Agent-Composed Retrieval ──► Answer
              (cheap LLM)     (entities, relations,      (reasoning LLM picks        (grounded
               gemini-2.5      chunks, embeddings)        operators per query)         in context)
               -flash
```

**Two-model design.** A cheap model (gemini-2.5-flash, ~$0.15/M tokens) builds the graph. A reasoning model (configurable per deployment) handles query-time operator selection and answer generation. Build cost and query cost scale independently.

**Graph construction.** Documents are chunked, then entity-relationship triples are extracted with descriptions and types. The graph is stored as NetworkX + GraphML with FAISS vector indexes for entity, relationship, and chunk embeddings. Optional post-build enrichment adds co-occurrence edges, PageRank centrality, and synonym links.

## The 28 Operators

Operators are typed functions with machine-readable I/O contracts. Any operator whose output type matches another's input type can be chained.

| Category | Operators | What They Do |
|----------|-----------|-------------|
| **Entity** (7) | vdb_search, ppr, onehop, link, tfidf, agent, rel_node | Find relevant entities via embedding similarity, PageRank propagation, graph traversal, or TF-IDF |
| **Relationship** (4) | onehop, vdb_search, score_agg, agent | Retrieve and rank relationships connecting entities |
| **Chunk** (5) | from_relation, occurrence, aggregator, text_search, vdb_search | Map graph elements back to source text passages |
| **Subgraph** (3) | khop_paths, steiner_tree, agent_path | Extract reasoning-relevant subgraph structures |
| **Community** (2) | from_entity, from_level | Leverage detected community structure |
| **Meta** (7) | extract_entities, generate_answer, pcst_optimize, decompose_question, synthesize_answers, rerank, reason_step | LLM reasoning steps: entity extraction, question decomposition, answer synthesis |

## How It Works: Agent-Driven Operator Composition

An external agent (Claude, Codex, any LLM with tool calling) calls operators directly via MCP or Python function calling. The agent sees intermediate results and adapts: if VDB search returns low-confidence matches, it switches to TF-IDF or PPR. There are no fixed pipelines — the agent composes operators into DAGs per question.

### Typical flow

```
Question: "Who founded the company that employed Jane Doe?"

1. entity_vdb_search("Jane Doe")           → finds entity node "Jane Doe"
2. relationship_onehop("Jane Doe")          → finds "employed_by → Acme Corp"
3. entity_vdb_search("Acme Corp")           → confirms entity exists
4. relationship_onehop("Acme Corp")         → finds "founded_by → John Smith"
5. chunk_occurrence(["Jane Doe","Acme Corp","John Smith"]) → retrieves source passages
6. Agent synthesizes answer from passages   → "John Smith"
```

The agent decides the chain at runtime. A comparison question might skip multi-hop traversal; a 4-hop question might iterate deeper. No hardcoded pipeline.

## Key Differentiators

**Adaptive per-question composition.** Every competitor runs the same pipeline for every question. DIGIMON's agent sees the question type and intermediate results, then picks operators accordingly. On heterogeneous benchmarks (MuSiQue has 2/3/4-hop questions mixed), this matters.

**Multiple graph types on one corpus.** ER, keyword-enriched, tree, and passage graphs can coexist. Different questions can query different representations.

**Post-build graph enrichment.** Co-occurrence edges (entities sharing a chunk get implicit links), PageRank centrality (node importance scoring), and synonym edges (embedding-based near-duplicate linking). No LLM cost, minutes to run, measurably improves retrieval.

**28 composable operators with typed contracts.** Research velocity: new retrieval strategies are tested in minutes by composing existing operators, not by building new systems.

## Benchmark Results

> **Caveat**: DIGIMON scores below are on 50-question subsets. SOTA scores (Youtu-GraphRAG, HippoRAG2) are on full 1000-question benchmarks. These are not directly comparable — 50q results have wider confidence intervals and may not generalize. 1000-question runs are pending.

| Dataset | Metric | DIGIMON (N) | Youtu-GraphRAG (N) | HippoRAG2 (N) |
|---------|--------|-------------|---------------------|----------------|
| MuSiQue (2-4 hop) | LLM-judge accuracy | 80.0% (50q) | 53.6% (1000q) | 50.8% (1000q) |
| MuSiQue | EM | 52.0% (50q) | — | — |
| MuSiQue | F1 | 67.7% (50q) | — | 48.6% (1000q) |
| HotpotQA (2-hop) | LLM-judge accuracy | 90.0% (50q) | 86.5% (1000q) | 81.8% (1000q) |
| HotpotQA | EM | 68.0% (50q) | — | — |
| HotpotQA | F1 | 82.5% (50q) | — | 75.5% (1000q) |

MuSiQue LLM-judge score (80%) is statistically significant vs SOTA (53.6%) at p<0.001 even with conservative adjustments. Audit of all 14 LLM-judge upgrades: 12 are formatting/detail differences (gold contained in prediction), 1 is a valid alternate answer, 1 is borderline.

**Current development status (March 18, 2026).** A later 50-question balanced MuSiQue comparison using `gemini-2.5-flash` for answering did **not** support the adaptive-routing thesis:

| Mode | EM | LLM-judge | Run Cost | Notes |
|------|----|-----------|----------|-------|
| Baseline | 34.0% | 60.0% | $2.03 | non-graph chunk retrieval |
| Fixed Graph | 32.0% | 54.0% | $1.85 | deterministic graph chain |
| Hybrid | 32.0% | 44.0% | $5.50 | adaptive mode underperformed and cost more |

Treat that run as development evidence, not decision-grade proof.

## Cost Profile

**MuSiQue (11,656 documents, 82,526-node graph):**

| Phase | Tokens | Cost | Time |
|-------|--------|------|------|
| Graph construction (extraction) | 145.8M | $32.41 | ~6 hours |
| Embedding (entity + chunk VDBs) | 7.4M | $0.15 | ~5 min |
| Graph enrichment (co-occurrence + centrality) | 0 | $0.00 | ~2 min |
| 50-question benchmark (o4-mini agent) | 5.1M input, 0.3M output | $3.41 | 65 min |
| LLM judge (50 questions) | 0.2M | $0.13 | ~30s |

Graph build cost is dominated by extraction (LLM calls per chunk with gleaning). Enrichment (693,263 co-occurrence edges + PageRank/degree centrality on all 82,526 nodes) is free — pure graph computation.

Per-query cost: **$0.068/query** at benchmark. Production with cheaper models (deepseek-chat): ~$0.006/query.

## Tech Stack

- **Graph storage**: NetworkX + GraphML (persistent, 82MB for MuSiQue)
- **Vector indexes**: FAISS with OpenAI text-embedding-3-small (1024d)
- **LLM routing**: llm_client library (litellm backend, automatic retry + fallback chains, cost tracking)
- **Interface**: MCP server (50+ tools) or direct Python function calling
- **Evaluation**: EM, F1, LLM-as-judge, per-hop-complexity breakdown
- **Observability**: All LLM/embedding calls logged to SQLite with trace_id correlation
