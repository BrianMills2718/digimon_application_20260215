# DIGIMON: Composable Graph RAG for Multi-Hop Question Answering

DIGIMON is a knowledge-graph-based retrieval system with 28 typed, composable operators that agents compose into retrieval DAGs at runtime. Built on the [GraphRAG framework](https://github.com/JayLZhou/GraphRAG) by Zhou et al.

## Supported Default Surface

The maintained default path in this repo is the **core thesis lane**:

- graph build and enrichment
- direct benchmark backend
- operator consolidation
- benchmark prompts and manifests
- evaluation on multi-hop QA

That is the surface used to answer the current investment question: does graph-assisted retrieval, and then adaptive routing, beat simpler baselines enough to justify continued investment?

See `docs/REPO_SURFACE.md` for the full `core` / `experimental` / `historical` split.

## Preserved Experimental Capabilities

The repo also preserves older or broader capabilities, including agent-platform work, memory systems, social-media analysis flows, cross-modal tools, and legacy MCP/UI paths.

These capabilities are still in the repository, but they are not the default maintained path and are not the primary source of truth for whether the core thesis lane is healthy.

## What It Does

1. **Build** a knowledge graph from documents (entity-relationship extraction via LLM)
2. **Query** the graph via agent-composed operator chains (not fixed pipelines)
3. **Answer** multi-hop questions grounded in retrieved evidence

The agent decides what operators to call based on the question and intermediate results. There are no fixed pipelines.

## Quick Start

```bash
# Environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: broader test/dev tooling
pip install -r requirements-dev.txt

# Build a graph from documents
# (via MCP server or eval harness — see below)

# Run a benchmark
python eval/run_agent_benchmark.py \
  --dataset HotpotQAsmallest --num 5 \
  --model gemini/gemini-2.5-flash --backend direct
```

Use `DIGIMON_PYTHON=/path/to/python ./eval/run_overnight.sh` only when you need
the overnight harness to use a different interpreter than the active shell.

### Configuration

Copy `Option/Config2.example.yaml` to `Option/Config2.yaml` and set your API keys:
```yaml
llm:
  api_type: litellm
  model: "gemini/gemini-2.5-flash"
  api_key: "YOUR_KEY"
embedding:
  api_type: litellm
  model: "text-embedding-3-small"
```

### Canonical Docs

- `FUNCTIONALITY.md` — supported user workflow and non-goals
- `docs/ACTIVE_DOCS.md` — current doc index and archive policy
- `docs/SYSTEM_OVERVIEW.md` — architecture and benchmark caveats
- `docs/COMPETITIVE_ANALYSIS.md` — evidence, baselines, and open thesis
- `docs/plans/CLAUDE.md` — active implementation-plan index
- `docs/plans/03_prove_adaptive_routing.md` — adaptive-routing closeout record

Historical API/UI/integration docs have been moved under `docs/archive/` and are not supported surfaces.

## Architecture

**28 operators** across 6 categories, all with typed I/O contracts:

| Category | Operators |
|----------|-----------|
| Entity (7) | vdb, ppr, onehop, link, tfidf, agent, rel_node |
| Relationship (4) | onehop, vdb, score_agg, agent |
| Chunk (5) | from_relation, occurrence, aggregator, text_search, vdb |
| Subgraph (3) | khop_paths, steiner_tree, agent_path |
| Community (2) | from_entity, from_level |
| Meta (7) | extract_entities, generate_answer, pcst_optimize, decompose_question, synthesize_answers, reason_step, rerank |

**Key tools for agents:**
- `entity_neighborhood` — full N-hop subgraph in one call (nodes + edges + descriptions)
- `entity_string_search` — exact/substring entity lookup by name
- `list_operators` / `get_compatible_successors` — discover valid operator chains

### Interface

- **MCP server**: `digimon_mcp_stdio_server.py` (50+ tools)
- **Direct Python**: `eval/run_agent_benchmark.py --backend direct` (in-process, no MCP overhead)

The MCP server now exposes a `list_tool_catalog` discovery tool that returns
per-tool `cost_tier` and `reliability_tier` metadata, plus explanatory `notes`.
These are currently dummy planning hints for tool selection and budget
attribution; they are not calibrated runtime telemetry yet. When progressive
disclosure is enabled, `search_available_tools` returns the same metadata for
deferred tools. The live FastMCP registry also stores the same values on each
registered tool's `meta` field so discovery code can inspect them directly for
tool selection and future distributed budget attribution.

### Two-Model Design

- **Build model** (`llm.model`): cheap model for graph extraction (gemini-2.5-flash)
- **Query model** (`agentic_model`): reasoning model for operator selection and answer generation

## Benchmark Results

Results on MuSiQue (2-4 hop multi-hop QA), 50-question subsets:

| Model | EM | LLM_EM | F1 | Cost |
|-------|----|---------|----|------|
| o4-mini (direct) | 52% | 80% | 67.7% | $3.41 |
| deepseek-chat (direct) | 68% | 90% | 82.5% | $0.30 (HotpotQA) |

**Caveat**: These are 50-question subsets, not directly comparable to 1000-question SOTA benchmarks.

## Datasets

- `Data/HotpotQAsmallest/` — 10 questions (dev/testing)
- `Data/HotpotQA/` — 1000 questions, 2-hop
- `Data/MuSiQue/` — 1000 questions, 2-4 hop (hardest)
- `Data/2WikiMultiHopQA/` — 1000 questions

## Project Structure

```
Core/
  Operators/          # 28 typed operators
  Composition/        # ChainValidator, PipelineExecutor, Adapters
  Schema/             # SlotTypes, OperatorDescriptor
  Graph/              # ERGraph, RKGraph, TreeGraph, PassageGraph
  AgentTools/         # MCP tool implementations
  Provider/           # LLM adapters (LiteLLM, llm_client)
eval/
  run_agent_benchmark.py  # Agent benchmark harness
  benchmark.py            # EM/F1/LLM-judge scoring
prompts/                  # YAML/Jinja2 prompt templates
Option/                   # Config files
Data/                     # Test datasets
```

## Citation

Based on the GraphRAG framework:

```bibtex
@article{zhou2025depth,
  title={In-depth Analysis of Graph-based RAG in a Unified Framework},
  author={Zhou, Yingli and Su, Yaodong and Sun, Youran and Wang, Shu and others},
  journal={arXiv preprint arXiv:2503.04338},
  year={2025}
}
```
