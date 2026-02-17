#!/usr/bin/env python3
"""Post-hoc graph enrichment: co-occurrence edges, centrality metrics.

Operates directly on the NetworkX graphml file — no DIGIMON server needed.

Usage:
    python eval/enrich_graph.py --dataset HotpotQA_200
"""
import asyncio
import argparse
import os
import sys
from collections import defaultdict
from itertools import combinations

import networkx as nx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Core.Common.Constants import GRAPH_FIELD_SEP


def find_graphml(dataset: str, working_dir: str = "./results") -> str:
    """Find the graphml file for a dataset."""
    path = os.path.join(working_dir, dataset, "er_graph", "nx_data.graphml")
    if os.path.exists(path):
        return path
    raise FileNotFoundError(f"No graphml found at {path}")


def add_cooccurrence_edges(G: nx.Graph, weight: float = 0.5) -> int:
    """Add chunk_cooccurrence edges between entities sharing a source chunk."""
    chunk_to_entities: dict[str, list[str]] = defaultdict(list)
    for node_id, data in G.nodes(data=True):
        source_id = data.get("source_id", "")
        for chunk_id in source_id.split(GRAPH_FIELD_SEP):
            if chunk_id:
                chunk_to_entities[chunk_id].append(node_id)

    added = 0
    for chunk_id, entities in chunk_to_entities.items():
        unique = list(set(entities))
        for a, b in combinations(unique, 2):
            if not G.has_edge(a, b) and not G.has_edge(b, a):
                G.add_edge(a, b,
                    weight=weight,
                    source_id=chunk_id,
                    relation_name="chunk_cooccurrence",
                    keywords="",
                    description="",
                    src_id=a,
                    tgt_id=b,
                )
                added += 1
    return added


def add_centrality_metrics(G: nx.Graph) -> dict:
    """Compute and store centrality metrics as node attributes."""
    if len(G) == 0:
        return {"nodes": 0}

    pagerank = nx.pagerank(G, weight="weight")
    degree_cent = nx.degree_centrality(G)

    # Skip betweenness — O(VE), very expensive
    betweenness = {}

    for node_id in G.nodes():
        G.nodes[node_id]["pagerank"] = pagerank.get(node_id, 0.0)
        G.nodes[node_id]["degree_centrality"] = degree_cent.get(node_id, 0.0)
        if betweenness:
            G.nodes[node_id]["betweenness"] = betweenness.get(node_id, 0.0)

    return {
        "nodes_updated": len(G),
        "pagerank_max": max(pagerank.values()) if pagerank else 0,
        "degree_centrality_max": max(degree_cent.values()) if degree_cent else 0,
        "betweenness_max": max(betweenness.values()) if betweenness else None,
    }


def add_string_similarity_edges(G: nx.Graph, threshold: float = 0.65, min_len: int = 4) -> int:
    """Add name_similarity edges between entities with similar names."""
    from difflib import SequenceMatcher
    nodes = [n for n in G.nodes() if len(n) >= min_len]
    added = 0
    seen = set()

    for i, a in enumerate(nodes):
        for b in nodes[i+1:]:
            pair = tuple(sorted((a, b)))
            if pair in seen:
                continue
            seen.add(pair)
            if G.has_edge(a, b) or G.has_edge(b, a):
                continue
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if ratio >= threshold:
                G.add_edge(a, b,
                    weight=ratio,
                    source_id="",
                    relation_name="name_similarity",
                    keywords="",
                    description=f"Name similarity {ratio:.3f}",
                    src_id=a,
                    tgt_id=b,
                )
                added += 1
    return added


def main():
    parser = argparse.ArgumentParser(description="Enrich an existing DIGIMON graph")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--working-dir", default="./results")
    parser.add_argument("--skip-cooccurrence", action="store_true")
    parser.add_argument("--skip-centrality", action="store_true")
    parser.add_argument("--skip-string-similarity", action="store_true")
    parser.add_argument("--cooccurrence-weight", type=float, default=0.5)
    parser.add_argument("--similarity-threshold", type=float, default=0.65)
    args = parser.parse_args()

    graphml_path = find_graphml(args.dataset, args.working_dir)
    print(f"Loading {graphml_path}...")
    G = nx.read_graphml(graphml_path)
    n_nodes = len(G.nodes())
    n_edges_before = len(G.edges())
    print(f"Loaded: {n_nodes} nodes, {n_edges_before} edges")

    # 1. Co-occurrence edges
    if not args.skip_cooccurrence:
        print("\n=== Step 1: Chunk co-occurrence edges ===")
        count = add_cooccurrence_edges(G, weight=args.cooccurrence_weight)
        print(f"  Added {count} co-occurrence edges")

    # 2. Centrality metrics
    if not args.skip_centrality:
        print("\n=== Step 2: Centrality metrics ===")
        stats = add_centrality_metrics(G)
        print(f"  {stats}")

    # 3. String similarity edges
    if not args.skip_string_similarity:
        print("\n=== Step 3: String similarity edges ===")
        count = add_string_similarity_edges(G, threshold=args.similarity_threshold)
        print(f"  Added {count} string similarity edges")

    # Save
    n_edges_after = len(G.edges())
    print(f"\n{'='*50}")
    print(f"Before: {n_nodes} nodes, {n_edges_before} edges")
    print(f"After:  {n_nodes} nodes, {n_edges_after} edges (+{n_edges_after - n_edges_before})")

    # Back up original
    backup_path = graphml_path + ".bak"
    if not os.path.exists(backup_path):
        import shutil
        shutil.copy2(graphml_path, backup_path)
        print(f"Backed up original to {backup_path}")

    nx.write_graphml(G, graphml_path)
    print(f"Saved enriched graph to {graphml_path}")


if __name__ == "__main__":
    main()
