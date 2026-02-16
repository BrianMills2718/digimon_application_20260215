#!/usr/bin/env python3
"""Pre-build graph + VDBs for a dataset before running agent benchmark.

Usage:
    python eval/prebuild_graph.py HotpotQA_200
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import llm_client  # noqa: F401 — triggers API key auto-load from ~/.secrets/api_keys.env


async def main(dataset: str) -> None:
    # Import the MCP server module — it initializes everything
    import digimon_mcp_stdio_server as server

    # Initialize state (config, LLM, encoder, etc.)
    await server._ensure_initialized()
    print(f"Initialized. LLM model: {server._state['config'].llm.model}")

    # Step 1: Build ER graph
    graph_path = Path(server._state["config"].working_dir) / dataset / "er_graph" / "nx_data.graphml"
    if graph_path.exists():
        print(f"[1/3] Graph already exists at {graph_path}, skipping.")
    else:
        print(f"[1/3] Building ER graph for {dataset}...")
        t0 = time.time()
        result = await server.graph_build_er(dataset_name=dataset, force_rebuild=False)
        elapsed = time.time() - t0
        print(f"[1/3] Graph build done in {elapsed:.0f}s: {result[:200]}")

    # Step 2: Build entity VDB
    print(f"[2/3] Building entity VDB...")
    t0 = time.time()
    result = await server.entity_vdb_build(
        graph_reference_id=f"{dataset}_ERGraph",
        vdb_collection_name=f"{dataset}_entities",
        force_rebuild=False,
    )
    elapsed = time.time() - t0
    print(f"[2/3] Entity VDB done in {elapsed:.0f}s: {result[:200]}")

    # Step 3: Build relationship VDB
    print(f"[3/3] Building relationship VDB...")
    t0 = time.time()
    result = await server.relationship_vdb_build(
        graph_reference_id=f"{dataset}_ERGraph",
        vdb_collection_name=f"{dataset}_relationships_vdb_relationships",
        force_rebuild=False,
    )
    elapsed = time.time() - t0
    print(f"[3/3] Relationship VDB done in {elapsed:.0f}s: {result[:200]}")

    print(f"\nAll prerequisites built for {dataset}.")


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "HotpotQA_200"
    asyncio.run(main(dataset))
