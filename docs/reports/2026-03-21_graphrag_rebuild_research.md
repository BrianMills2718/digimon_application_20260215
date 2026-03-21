# GraphRAG Rebuild Research

**Date:** 2026-03-21
**Purpose:** Inform the DIGIMON graph-build rearchitecture with current GraphRAG methods, codebases, and benchmarks.

## DIGIMON Goal, In Plain Language

DIGIMON should be a controlled GraphRAG laboratory.

That means one system should be able to reproduce the build profiles, retrieval operators, and analysis methods used by other GraphRAG systems, but in a way that is explicit, configurable, and agent-composable. We are not trying to build one opaque monolith that happens to answer questions. We are trying to build a workbench where:

- graph construction choices are explicit
- retrieval operators are explicit
- tool availability follows what was actually built
- different GraphRAG methods can be reproduced, compared, and agentically composed under one roof

## Sources Reviewed

### Core Methods and Official Code

- Microsoft GraphRAG docs and repo
  - https://github.com/microsoft/graphrag
  - https://microsoft.github.io/graphrag/
- JayLZhou unified framework and repo
  - https://arxiv.org/abs/2503.04338
  - https://github.com/JayLZhou/GraphRAG
- HippoRAG 2 paper and repo
  - https://arxiv.org/abs/2502.14802
  - https://github.com/OSU-NLP-Group/HippoRAG
- LightRAG paper and repo
  - https://arxiv.org/abs/2410.05779
  - https://github.com/HKUDS/LightRAG
- HopRAG paper and repo
  - https://arxiv.org/abs/2502.12442
  - https://github.com/LIU-Hao-2002/HopRAG
- Youtu-GraphRAG paper and repo
  - https://arxiv.org/abs/2508.19855
  - https://github.com/TencentCloudADP/youtu-graphrag
- Deep GraphRAG paper
  - https://arxiv.org/abs/2601.11144
- AWS GraphRAG Toolkit and HLG paper
  - https://github.com/awslabs/graphrag-toolkit
  - https://arxiv.org/abs/2506.08074
- Neo4j GraphRAG for Python
  - https://github.com/neo4j/neo4j-graphrag-python
- GraphRAG-Bench repo and paper
  - https://github.com/GraphRAG-Bench/GraphRAG-Benchmark
  - https://arxiv.org/abs/2506.05690

## High-Level Findings

### 1. The field is converging on configurable graph views, not one universal raw graph alone

JayLZhou's unified framework is important because it reduces many systems into graph types plus retrieval operators, rather than treating each system as a completely different architecture. That framing matches DIGIMON's ambition well. The field still repeatedly distinguishes:

- chunk trees
- passage graphs
- KG-style entity-relation graphs
- TKG/RKG-style richer entity-relation graphs

This supports DIGIMON's move toward:

- separate **topology**
- separate **attribute profile**
- separate **retrieval operator availability**

### 2. Strong systems increasingly use schema guidance, not unconstrained extraction

Youtu-GraphRAG is the clearest current signal here. Its core construction idea is a **seed graph schema** with targeted entity types, relations, and attributes, plus controlled schema expansion for unseen domains. This is directly relevant to DIGIMON. It argues against leaving extraction entirely open-ended and then hoping retrieval can clean things up later.

### 3. Retrieval quality increasingly depends on passage integration, not graph traversal alone

HippoRAG 2 is explicit that it keeps Personalized PageRank but improves results through **deeper passage integration** and more effective online LLM usage. HopRAG similarly builds a graph over text chunks and treats retrieval as multi-hop reasoning over passages, not just entities. This matters because DIGIMON's current weak point is not only graph quality; it is also how graph signals turn back into grounded text evidence.

### 4. Hybrid retrieval is the norm, not the exception

LightRAG exposes multiple query modes such as `local`, `global`, `hybrid`, `mix`, and `naive`, and explicitly supports incremental insertion and deletion. Microsoft GraphRAG also separates `Global Search`, `Local Search`, `DRIFT Search`, and `Basic Search`. The consistent lesson is:

- graph retrieval should not replace lexical/vector retrieval
- graph retrieval should orchestrate and refine it

### 5. Community hierarchies matter, but only if they are actually used

Microsoft GraphRAG's most distinctive move is the community hierarchy plus summary pipeline for global reasoning. Youtu-GraphRAG pushes further with schema-guided hierarchical trees and community detection that blends structure with semantics. Deep GraphRAG also emphasizes hierarchical global-to-local retrieval plus multi-stage reranking. DIGIMON should keep communities, but only if they are integrated into retrieval policies and measured.

### 6. Evaluation is shifting from “can GraphRAG ever help?” to “when should graphs be used?”

GraphRAG-Bench is the clearest signal here. Its premise is that GraphRAG often underperforms vanilla RAG, so the right question is not whether graphs are universally better, but which tasks, corpora, and reasoning regimes justify graph cost. That is exactly the right framing for DIGIMON's rebuild.

## What DIGIMON Should Copy or Adapt

## A. Build Architecture

### Copy: JayLZhou's separation of graph type and operator family

This should remain a foundational design principle. DIGIMON should keep:

- graph families as explicit build profiles
- retrieval operators as explicit reusable units
- method reproduction as compositions of those units

### Copy: Youtu's schema-guided extraction

DIGIMON should add:

- a seed schema for entity types, relation types, and attribute types
- explicit schema expansion rules for unseen domains
- build-time records of which schema version/profile was used

This is more important than adding more operator variety right now.

### Adapt: LightRAG's incremental update and deletion model

DIGIMON should not just rebuild from scratch forever. The LightRAG repo shows ongoing support for:

- incremental insertion
- cleanup/deletion
- rebuilding affected descriptions instead of full destruction

That is worth copying after the first clean rebuild, not before.

### Copy: AWS HLG-style provenance discipline

The Hierarchical Lexical Graph work is valuable because it traces atomic propositions back to sources. DIGIMON should adopt that principle even if it does not adopt AWS's full lexical graph design. In practice this means:

- explicit `source_chunk_ids`
- later, explicit proposition/statement units if needed
- no retrieval operator that depends on provenance should be exposed when provenance is absent

## B. Retrieval and Analysis

### Copy: HippoRAG/HippoRAG 2 PPR plus stronger passage integration

DIGIMON should keep PPR, but it should stop treating PPR as sufficient on its own. The rebuild should make it easier to experiment with:

- seed entities
- PPR over entity graph
- relationship scoring
- passage/chunk aggregation
- grounded text reranking

### Copy: Microsoft GraphRAG's query modes

DIGIMON should formalize named retrieval modes comparable to:

- `basic`
- `local`
- `global`
- `drift`
- `hybrid`

These should be manifest- and topology-aware, not prompt-only conventions.

### Adapt: HopRAG's passage-graph reasoning

HopRAG's strongest idea is not Neo4j itself. It is the decision to treat chunks as graph nodes for multi-hop logic-aware retrieval. DIGIMON should not fold this into the first entity-graph rebuild, but it should preserve a path to:

- passage-graph builds
- chunk-level hop exploration
- on-the-fly or prebuilt passage traversal

### Copy carefully: Youtu's schema-aware decomposition and reflection

This aligns with DIGIMON's agentic goal, but it should come **after** the clean rebuild. First make the graph and capability model truthful; then use agentic decomposition over that stable surface.

## C. Evaluation and Experiment Design

### Copy: GraphRAG-Bench framing

The right benchmark question is:

- when do graphs help enough to justify their cost?

DIGIMON should evaluate the rebuild with that framing, not by assuming graph complexity is inherently superior.

### Copy: Microsoft GraphRAG prompt-tuning discipline

Microsoft explicitly recommends prompt tuning rather than assuming defaults are enough. DIGIMON should treat build prompt tuning as a first-class experimental variable:

- extraction prompt
- schema prompt
- summary/community prompt
- retrieval reasoning prompt

## What DIGIMON Should Not Copy Blindly

### 1. Do not copy a full storage/backend migration into the first rebuild

Neo4j GraphRAG, FalkorDB GraphRAG-SDK, and AWS Neptune tooling are useful reference systems, but they should not force the first rebuild to become a database migration project.

Recommendation:

- keep the first rebuild storage-simple
- rebuild the schema, manifest, and operator surface first
- migrate storage later if the entity-graph architecture proves itself

### 2. Do not copy Microsoft's full hierarchy-first system as the default answer to every problem

Microsoft GraphRAG is strongest for global/holistic reasoning. DIGIMON's immediate need is to rebuild a trustworthy entity-graph family for reproducible method comparison. Community hierarchies belong in the design, but not as the only path.

### 3. Do not copy open-ended agentic retrieval before the build contract is clean

Youtu's agentic retrieval is attractive, but agentic composition over a dirty graph just amplifies ambiguity. Rebuild first; then let agents exploit the clearer surface.

## Concrete Recommendations for the Rebuild

## Phase 1: Canonical Entity Graph

Rebuild only the entity-graph family with:

- canonical name vs search key split
- aliases
- typed provenance
- explicit relation text fields
- explicit graph profile: `KG`, `TKG`, `RKG`
- persisted manifest as source of truth

## Phase 2: Retrieval-Critical Derived Artifacts

Add or standardize:

- entity search/index text
- relationship search/index text
- chunk provenance mappings
- sparse matrices for propagation
- optional community summaries

## Phase 3: Named Query Modes

Implement reproducible modes inspired by Microsoft GraphRAG and LightRAG:

- `basic`
- `local`
- `global`
- `hybrid`

`drift` can wait until the core modes are stable.

## Phase 4: Reproduction Packs

Create named reproducible packs for major systems:

- `ms_graphrag_local`
- `ms_graphrag_global`
- `hipporag_style`
- `lightrag_local`
- `lightrag_hybrid`
- `youtu_schema_guided`

Each pack should declare:

- build profile
- required artifacts
- retrieval operator chain
- optional agentic control points

## Experiments Worth Running

These are the highest-value rebuild experiments after the first clean entity graph exists.

### Build Experiments

1. Open extraction vs schema-guided extraction
2. `KG` vs `TKG` vs `RKG`
3. With vs without entity descriptions
4. With vs without relation keywords
5. With vs without canonical alias/search-key layer

### Retrieval Experiments

1. chunk-text baseline vs graph local
2. entity-search + one-hop vs PPR + chunk aggregation
3. local vs global vs hybrid
4. graph retrieval with and without final reranking
5. graph-only vs graph-plus-text hybrid

### Cost/Latency Experiments

1. build cost by graph profile
2. incremental update cost vs full rebuild
3. per-query cost for `basic` / `local` / `global` / `hybrid`

## Main Uncertainties

These questions still need local implementation evidence rather than literature alone:

1. Whether schema-guided extraction improves MuSiQue enough to justify the added build complexity.
2. Whether DIGIMON's entity-graph family should keep one maximal raw extraction path or support multiple extraction prompts per profile.
3. How far manifest-driven capability gating should go for MCP exposure in the first slice versus only benchmark/direct mode.
4. Whether the current NetworkX/GraphML substrate is sufficient for the first clean rebuild or becomes the next bottleneck immediately after schema cleanup.

## Recommended First Implementation Sequence

1. Rebuild the entity-graph schema around canonical names, aliases/search keys, provenance, and relation text fields.
2. Add schema-guided extraction inputs and explicit `KG` / `TKG` / `RKG` profile declarations.
3. Extend the manifest so it can truthfully drive query-mode and tool applicability.
4. Rebuild MuSiQue from that path.
5. Re-test a fixed-graph slice before doing more adaptive-routing work.

## Off-the-Shelf Code Worth Borrowing

### Borrow now

- Microsoft GraphRAG ideas for global/local/DRIFT query separation and prompt tuning workflow
- JayLZhou operator taxonomy and unified comparison framing
- HippoRAG/HippoRAG 2 passage-aware PPR design
- LightRAG incremental update and query-mode ergonomics
- Youtu schema-guided construction ideas
- GraphRAG-Bench evaluation framing and datasets

### Borrow later

- Neo4j GraphRAG `Pipeline` / `SimpleKGPipeline` patterns if DIGIMON later moves to a graph DB
- AWS lexical graph ideas if DIGIMON later adds proposition-level retrieval
- FalkorDB/GraphRAG-SDK if a low-latency graph DB backend becomes strategically necessary

### Avoid for now

- full database migration
- tree/passage rebuild in the first slice
- agentic retrieval redesign before the graph contract is clean

## Bottom Line

The literature and codebases support the rebuild direction.

The strongest signals are:

- use **schema-guided** extraction
- treat `KG` / `TKG` / `RKG` as explicit profiles
- make **manifest truth** drive tool availability
- keep **hybrid retrieval** central
- invest heavily in **passage integration**, not just graph traversal
- evaluate based on **when graphs help**, not on ideological preference for graphs

DIGIMON's rebuild should therefore aim to become the most explicit, configurable, and agent-composable reproduction framework for GraphRAG methods, not merely another custom graph QA system.
