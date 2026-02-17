#!/usr/bin/env python3
"""Add similarity edges (vector + string) to an existing graph.

Usage:
    python eval/augment_similarity_edges.py HotpotQA_200
    python eval/augment_similarity_edges.py HotpotQA_200 --vector-threshold 0.8 --string-threshold 0.65
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import llm_client  # noqa: F401 — triggers API key auto-load from ~/.secrets/api_keys.env


async def main(dataset: str, vector_threshold: float, string_threshold: float) -> None:
    import digimon_mcp_stdio_server as server

    await server._ensure_initialized()
    print(f"Initialized. LLM model: {server._state['config'].llm.model}")

    # Load existing graph
    graph_path = Path(server._state["config"].working_dir) / dataset / "er_graph" / "nx_data.graphml"
    if not graph_path.exists():
        print(f"No graph found at {graph_path}. Building first...")
        result = await server.graph_build_er(dataset_name=dataset, force_rebuild=False)
        print(f"Graph build: {result[:200]}")

    # Ensure graph is loaded into context
    ctx = server._state["context"]
    graph_key = f"{dataset}_ERGraph"
    if graph_key not in ctx.graphs:
        from Core.Graph.ERGraph import ERGraph
        config = server._state["config"]
        chunk_factory = server._state["chunk_factory"]
        graph = ERGraph(config=config.graph, llm=server._state["llm"], encoder=server._state["encoder"])
        graph.namespace = chunk_factory.get_namespace(dataset)
        loaded = await graph.load_persisted_graph()
        if not loaded:
            raise RuntimeError(f"Failed to load graph from {graph_path}")
        ctx.graphs[graph_key] = graph
        ctx.add_graph_instance(graph_key, graph)
        print(f"Loaded graph: {graph.node_num} nodes, {graph.edge_num} edges")
    else:
        graph = ctx.graphs[graph_key]
        print(f"Graph already in context: {graph.node_num} nodes, {graph.edge_num} edges")

    edges_before = graph.edge_num

    # Step 1: Build entity VDB if needed
    vdb_key = f"{dataset}_entities"
    if vdb_key not in ctx.vdbs:
        print("[1/3] Building entity VDB...")
        t0 = time.time()
        result = await server.entity_vdb_build(
            graph_reference_id=graph_key,
            vdb_collection_name=vdb_key,
            force_rebuild=False,
        )
        print(f"[1/3] Entity VDB done in {time.time() - t0:.0f}s: {result[:200]}")
    else:
        print("[1/3] Entity VDB already in context, skipping.")

    entity_vdb = ctx.vdbs[vdb_key]

    # Step 2: Vector similarity augmentation
    print(f"\n[2/3] Vector similarity augmentation (threshold={vector_threshold})...")
    graph.config.similarity_threshold = vector_threshold
    t0 = time.time()
    await graph.augment_graph_by_similarity_search(entity_vdb)
    elapsed = time.time() - t0
    edges_after_vector = graph.edge_num
    vector_added = edges_after_vector - edges_before
    print(f"[2/3] Vector similarity done in {elapsed:.0f}s: +{vector_added} edges ({edges_before} → {edges_after_vector})")

    # Step 3: String similarity augmentation
    print(f"\n[3/3] String similarity augmentation (threshold={string_threshold})...")
    graph.config.string_similarity_threshold = string_threshold
    t0 = time.time()
    string_added = await graph.augment_graph_by_string_similarity()
    elapsed = time.time() - t0
    edges_final = graph.edge_num
    print(f"[3/3] String similarity done in {elapsed:.0f}s: +{string_added} edges ({edges_after_vector} → {edges_final})")

    # Summary
    total_added = edges_final - edges_before
    print(f"\nDone. Total edges added: {total_added} ({edges_before} → {edges_final})")
    print(f"Graph file: {graph_path}")
    print(f"  Modified: {time.ctime(graph_path.stat().st_mtime)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add similarity edges to existing graph")
    parser.add_argument("dataset", nargs="?", default="HotpotQA_200", help="Dataset name")
    parser.add_argument("--vector-threshold", type=float, default=0.8)
    parser.add_argument("--string-threshold", type=float, default=0.65)
    args = parser.parse_args()
    asyncio.run(main(args.dataset, args.vector_threshold, args.string_threshold))
