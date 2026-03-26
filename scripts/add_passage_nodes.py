#!/usr/bin/env python3
"""Add passage nodes to an existing graph without rebuilding.

Creates passage nodes (one per chunk) and entity→passage edges using
the source_id already stored on each entity node. Zero LLM calls, $0 cost.

Usage:
    python scripts/add_passage_nodes.py --dataset MuSiQue
    python scripts/add_passage_nodes.py --dataset MuSiQue --dry-run
"""

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def add_passage_nodes(dataset_name: str, dry_run: bool = False) -> dict:
    """Add passage nodes to existing graph from entity source_ids."""
    os.environ["DIGIMON_BENCHMARK_MODE"] = "0"
    os.environ["DIGIMON_PRELOAD_DATASET"] = dataset_name

    import digimon_mcp_stdio_server as dms
    await dms._ensure_initialized()

    ctx = dms._state.get("context")
    graph_id = f"{dataset_name}_ERGraph"
    graph_instance = ctx.get_graph_instance(graph_id)
    if not graph_instance:
        raise RuntimeError(f"Graph '{graph_id}' not found")

    print(f"Graph loaded: {graph_instance.node_num} nodes, {graph_instance.edge_num} edges")

    # Check if passage nodes already exist
    all_nodes = await graph_instance._graph.get_nodes_data()
    existing_passages = [n for n in all_nodes if n.get("node_type") == "passage"]
    if existing_passages:
        print(f"Graph already has {len(existing_passages)} passage nodes. Skipping.")
        return {"status": "already_has_passages", "count": len(existing_passages)}

    # Build chunk→entity mapping from source_ids
    GRAPH_FIELD_SEP = "<SEP>"
    chunk_to_entities: dict[str, list[str]] = defaultdict(list)
    entity_count = 0

    for node_data in all_nodes:
        entity_name = node_data.get("entity_name", "")
        source_id = node_data.get("source_id", "")
        if not source_id or not entity_name:
            continue
        entity_count += 1
        for chunk_id in source_id.split(GRAPH_FIELD_SEP):
            chunk_id = chunk_id.strip()
            if chunk_id:
                chunk_to_entities[chunk_id].append(entity_name)

    print(f"Found {entity_count} entities across {len(chunk_to_entities)} chunks")

    if dry_run:
        print(f"DRY RUN: Would create {len(chunk_to_entities)} passage nodes")
        sample = list(chunk_to_entities.items())[:5]
        for chunk_id, entities in sample:
            print(f"  passage_{chunk_id} → {len(entities)} entities: {entities[:3]}...")
        return {"status": "dry_run", "passage_nodes": len(chunk_to_entities)}

    # Create passage nodes and edges
    from Core.Schema.EntityRelation import Relationship
    passage_count = 0
    edge_count = 0

    for chunk_id, entity_names in chunk_to_entities.items():
        passage_node_id = f"passage_{chunk_id}"

        # Create passage node
        await graph_instance._graph.upsert_node(
            passage_node_id,
            node_data={
                "entity_name": passage_node_id,
                "node_type": "passage",
                "source_id": chunk_id,
                "entity_type": "passage",
                "description": f"Source passage {chunk_id}",
            },
        )
        passage_count += 1

        # Create entity→passage edges
        unique_entities = list(set(entity_names))
        for ent_name in unique_entities:
            await graph_instance._graph.upsert_edge(
                ent_name,
                passage_node_id,
                edge_data={
                    "source_id": chunk_id,
                    "relation_name": "extracted_from",
                    "weight": 0.3,
                    "description": "",
                },
            )
            edge_count += 1

        if passage_count % 500 == 0:
            print(f"  Created {passage_count} passage nodes, {edge_count} edges...")

    # Save
    print(f"\nSaving graph...")
    await graph_instance._graph.persist(force=True)

    print(f"\nDone:")
    print(f"  Passage nodes created: {passage_count}")
    print(f"  Entity→passage edges: {edge_count}")
    print(f"  Total nodes now: {graph_instance.node_num}")
    print(f"  Total edges now: {graph_instance.edge_num}")

    return {
        "status": "success",
        "passage_nodes": passage_count,
        "passage_edges": edge_count,
        "total_nodes": graph_instance.node_num,
        "total_edges": graph_instance.edge_num,
    }


def main():
    parser = argparse.ArgumentParser(description="Add passage nodes to existing graph")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(add_passage_nodes(args.dataset, args.dry_run))
    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()
