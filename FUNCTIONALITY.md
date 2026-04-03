# DIGIMON: Supported Functionality

## One-Liner

DIGIMON builds document knowledge graphs and exposes graph-retrieval tools so an external agent can answer multi-hop questions with grounded evidence.

## What Is Supported Today

### 1. Graph Build

- Build ER, RK, Tree, Tree-Balanced, and Passage graphs from a DIGIMON dataset.
- Use a cheaper build-time model for extraction and embeddings.
- Persist graph artifacts and indexes under `results/`.

### 2. Agent-Driven Retrieval

- Expose 28 typed operators through the MCP server and the direct benchmark harness.
- Let an external agent choose retrieval chains at query time.
- Support non-graph, fixed-graph, and adaptive benchmark modes in `eval/run_agent_benchmark.py`.

### 3. Grounded QA

- Retrieve entities, relationships, chunks, and subgraphs.
- Synthesize answers from retrieved evidence.
- Score runs with EM, F1, and LLM-as-judge.

## Supported Interfaces

- `digimon_mcp_stdio_server.py`
  Primary tool surface for Claude Code, Codex, and other MCP-capable agents.
- `eval/run_agent_benchmark.py --backend direct`
  In-process benchmark path with no MCP subprocess overhead.

## Typical Workflow

1. Prepare a dataset under `Data/<dataset_name>/`.
2. Build an ER graph and any needed indexes.
3. Query via `baseline`, `fixed_graph`, or `hybrid` benchmark mode.
4. Inspect scored results and tool traces.

Representative tool flow:

```text
graph_build_er
  -> entity_vdb_build
  -> entity_string_search / entity_neighborhood / chunk_text_search
  -> submit_answer
```

The exact chain depends on mode and question.

## What Is Not a Supported Surface

- No maintained REST API.
- No maintained Streamlit frontend.
- No maintained social-media UI workflow.
- No claim that DIGIMON is already a polished end-user document-chat product.

Those older materials are historical only and belong in `docs/archive/`.

## Current Value Proposition

The repo is strongest as a research system for testing graph-assisted
retrieval on heterogeneous multi-hop QA, with adaptive operator routing as a
follow-on thesis rather than a proven default.

Current evidence supports graph value on the maintained benchmark lane, but it
does not yet prove that adaptive routing beats the best fixed pipeline. See
`docs/COMPETITIVE_ANALYSIS.md` and `docs/plans/03_prove_adaptive_routing.md`.
