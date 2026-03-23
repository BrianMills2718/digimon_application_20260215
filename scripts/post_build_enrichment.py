#!/usr/bin/env python3
"""Post-build graph enrichment: synonym edges + centrality.

Run after graph_build_er completes to add HippoRAG-aligned enrichments.
No LLM calls — uses embedding similarity and graph algorithms only.

Usage:
    python scripts/post_build_enrichment.py --dataset MuSiQue
    python scripts/post_build_enrichment.py --dataset MuSiQue --synonym-threshold 0.85
    python scripts/post_build_enrichment.py --dataset MuSiQue --skip-synonyms  # centrality only
"""

import argparse
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_enrichment(
    dataset_name: str,
    synonym_threshold: float = 0.85,
    skip_synonyms: bool = False,
    skip_centrality: bool = False,
) -> dict:
    """Run post-build enrichment on an existing graph.

    Returns dict with enrichment statistics.
    """
    os.environ["DIGIMON_BENCHMARK_MODE"] = "0"
    os.environ["DIGIMON_PRELOAD_DATASET"] = dataset_name

    import digimon_mcp_stdio_server as dms
    await dms._ensure_initialized()

    stats = {"dataset": dataset_name}

    # Get graph instance
    ctx = dms._state.get("context")
    if not ctx:
        raise RuntimeError("No GraphRAG context initialized")

    graph_id = f"{dataset_name}_ERGraph"
    graph_instance = ctx.get_graph_instance(graph_id)
    if not graph_instance:
        raise RuntimeError(f"Graph '{graph_id}' not found. Run graph_build_er first.")

    print(f"Graph loaded: {graph_id}")
    print(f"  Nodes: {graph_instance.node_num}")
    print(f"  Edges: {graph_instance.edge_num}")

    # 1. Synonym edge detection
    if not skip_synonyms:
        vdb_id = f"{dataset_name}_entities"
        entity_vdb = ctx.get_vdb_instance(vdb_id)
        if entity_vdb:
            print(f"\nRunning synonym detection (threshold={synonym_threshold})...")
            synonym_count = await graph_instance.augment_graph_by_synonym_detection(
                entity_vdb=entity_vdb,
                threshold=synonym_threshold,
            )
            stats["synonym_edges_added"] = synonym_count
            print(f"  Added {synonym_count} synonym edges")
        else:
            print(f"\nSkipping synonyms: entity VDB '{vdb_id}' not found. Build VDB first.")
            stats["synonym_edges_added"] = 0
    else:
        print("\nSkipping synonym detection (--skip-synonyms)")
        stats["synonym_edges_added"] = "skipped"

    # 2. Centrality augmentation
    if not skip_centrality:
        print("\nRunning centrality augmentation...")
        centrality_stats = await graph_instance.augment_graph_by_centrality()
        stats["centrality"] = centrality_stats
        print(f"  Centrality stats: {centrality_stats}")
    else:
        print("\nSkipping centrality (--skip-centrality)")
        stats["centrality"] = "skipped"

    # Save updated graph
    print("\nPersisting enriched graph...")
    await graph_instance._graph.save_graph()
    print("Done.")

    # Final stats
    print(f"\nFinal graph: {graph_instance.node_num} nodes, {graph_instance.edge_num} edges")
    stats["final_nodes"] = graph_instance.node_num
    stats["final_edges"] = graph_instance.edge_num

    return stats


def main():
    parser = argparse.ArgumentParser(description="Post-build graph enrichment")
    parser.add_argument("--dataset", required=True, help="Dataset name (e.g., MuSiQue)")
    parser.add_argument("--synonym-threshold", type=float, default=0.85,
                        help="Cosine similarity threshold for synonym detection (default: 0.85)")
    parser.add_argument("--skip-synonyms", action="store_true",
                        help="Skip synonym edge detection")
    parser.add_argument("--skip-centrality", action="store_true",
                        help="Skip centrality augmentation")
    args = parser.parse_args()

    stats = asyncio.run(run_enrichment(
        dataset_name=args.dataset,
        synonym_threshold=args.synonym_threshold,
        skip_synonyms=args.skip_synonyms,
        skip_centrality=args.skip_centrality,
    ))

    import json
    print(f"\n=== Enrichment Summary ===")
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
