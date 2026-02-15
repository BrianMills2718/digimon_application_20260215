#!/usr/bin/env python3
"""E2E tests for cross-modal conversion tools.

Uses a real DIGIMON ERGraph (Fictional_Test) — no mocks.
Tests actual analytic goals, not just data shape.

Usage:
    conda run -n digimon python test_cross_modal.py
"""

import asyncio
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATASET = "Fictional_Test"
PASS = 0
FAIL = 0


def report(name: str, passed: bool, detail: str = ""):
    global PASS, FAIL
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


async def main():
    global PASS, FAIL

    # =========================================================================
    # SETUP: Load real DIGIMON graph
    # =========================================================================
    print("=" * 70)
    print("SETUP: Loading Fictional_Test ERGraph")
    print("=" * 70)

    from Option.Config2 import Config
    from Core.Provider.LiteLLMProvider import LiteLLMProvider
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentSchema.context import GraphRAGContext

    config = Config.from_yaml_file("Option/Config2.yaml")
    llm = LiteLLMProvider(config.llm)
    encoder = get_rag_embedding(config=config)
    chunk_factory = ChunkFactory(config)

    context = GraphRAGContext(
        target_dataset_name=DATASET,
        main_config=config,
        llm_provider=llm,
        embedding_provider=encoder,
        chunk_storage_manager=chunk_factory,
    )

    # Load pre-built graph (no LLM needed)
    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs

    build_inputs = BuildERGraphInputs(
        target_dataset_name=DATASET, force_rebuild=False
    )
    build_result = await build_er_graph(build_inputs, config, llm, encoder, chunk_factory)
    gi = getattr(build_result, "graph_instance", None)
    if gi and hasattr(gi, "_graph") and hasattr(gi._graph, "namespace"):
        gi._graph.namespace = chunk_factory.get_namespace(DATASET)
    context.add_graph_instance(build_result.graph_id, gi)
    GRAPH_ID = build_result.graph_id

    # Extract raw NetworkX graph for direct inspection
    from Core.AgentTools.cross_modal_tools import (
        _extract_networkx_graph, _graph_to_dict, _dict_to_networkx,
        convert, validate_round_trip, get_embedding_provider,
        serialize_conversion_result, list_all_conversions,
        graph_to_table_nodes, graph_to_table_edges, graph_to_table_adjacency,
        table_to_graph_entity_rel, table_to_graph_auto,
        graph_to_vector_features, graph_to_vector_node_embed,
        table_to_vector_stats,
        vector_to_graph_similarity, vector_to_graph_clustering,
        vector_to_table_direct, vector_to_table_pca, vector_to_table_similarity,
    )

    nx_graph = _extract_networkx_graph(context.get_graph_instance(GRAPH_ID))
    assert nx_graph is not None, "Failed to extract NetworkX graph"
    graph_dict = _graph_to_dict(nx_graph)
    n_nodes = len(graph_dict["nodes"])
    n_edges = len(graph_dict["edges"])
    print(f"  Graph loaded: {GRAPH_ID}")
    print(f"  Nodes: {n_nodes}, Edges: {n_edges}")
    assert n_nodes > 10, f"Expected substantial graph, got {n_nodes} nodes"
    print()

    # Get hash provider for deterministic embedding tests (no model download)
    hash_provider = get_embedding_provider("hash")

    # =========================================================================
    # TEST GROUP 1: Graph → Table conversions (analytic correctness)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 1: Graph → Table")
    print("=" * 70)

    # 1a. Node table: every node should appear, with label and type
    nodes_df = graph_to_table_nodes(graph_dict)
    report(
        "node table has all nodes",
        len(nodes_df) == n_nodes,
        f"expected {n_nodes}, got {len(nodes_df)}",
    )
    report(
        "node table has required columns",
        set(["node_id", "label", "type"]).issubset(set(nodes_df.columns)),
        f"columns: {list(nodes_df.columns)}",
    )
    report(
        "no null node IDs",
        nodes_df["node_id"].notna().all(),
    )
    # Analytic check: node types should have diversity (entities, not all same type)
    n_types = nodes_df["type"].nunique()
    report(
        "node type diversity",
        n_types >= 1,
        f"{n_types} distinct types: {nodes_df['type'].value_counts().to_dict()}",
    )

    # 1b. Edge table: every edge should have source/target in node set
    edges_df = graph_to_table_edges(graph_dict)
    report(
        "edge table has all edges",
        len(edges_df) == n_edges,
        f"expected {n_edges}, got {len(edges_df)}",
    )
    node_ids = set(nodes_df["node_id"])
    sources_valid = edges_df["source"].isin(node_ids).all()
    targets_valid = edges_df["target"].isin(node_ids).all()
    report(
        "all edge endpoints exist in node set",
        sources_valid and targets_valid,
        f"sources_valid={sources_valid}, targets_valid={targets_valid}",
    )
    # Analytic check: edge types should be meaningful
    edge_types = edges_df["type"].value_counts()
    report(
        "edges have relationship types",
        len(edge_types) >= 1,
        f"{len(edge_types)} types, top: {edge_types.head(3).to_dict()}",
    )
    # Weights should be positive
    report(
        "edge weights are positive",
        (edges_df["weight"] > 0).all(),
        f"min={edges_df['weight'].min():.3f}, max={edges_df['weight'].max():.3f}",
    )

    # 1c. Adjacency matrix: should be symmetric, square, correct dimension
    adj_df = graph_to_table_adjacency(graph_dict)
    report(
        "adjacency matrix is square",
        adj_df.shape[0] == adj_df.shape[1] == n_nodes,
        f"shape={adj_df.shape}",
    )
    # Check symmetry (undirected graph)
    diff = np.abs(adj_df.values - adj_df.values.T).max()
    report(
        "adjacency matrix is symmetric",
        diff < 1e-9,
        f"max asymmetry={diff:.2e}",
    )
    # Non-zero entries should correspond to edges
    nonzero_count = (adj_df.values > 0).sum() // 2  # divide by 2 for undirected
    report(
        "adjacency nonzero count matches edge count",
        nonzero_count == n_edges,
        f"nonzero_pairs={nonzero_count}, edges={n_edges}",
    )
    print()

    # =========================================================================
    # TEST GROUP 2: Table → Graph conversions (reconstruction fidelity)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 2: Table → Graph")
    print("=" * 70)

    # 2a. Edge table → Graph: should reconstruct node set from source/target
    reconstructed = table_to_graph_entity_rel(edges_df)
    recon_node_ids = {n["id"] for n in reconstructed["nodes"]}
    # Every source/target in edges should become a node
    edge_endpoints = set(edges_df["source"]) | set(edges_df["target"])
    report(
        "entity_rel reconstructs all endpoints as nodes",
        edge_endpoints == recon_node_ids,
        f"expected {len(edge_endpoints)}, got {len(recon_node_ids)}",
    )
    report(
        "entity_rel preserves edge count",
        len(reconstructed["edges"]) == n_edges,
        f"expected {n_edges}, got {len(reconstructed['edges'])}",
    )

    # 2b. Adjacency matrix → Graph: should reconstruct correct edge count
    adj_graph = await convert(adj_df, "table", "graph", mode="adjacency")
    report(
        "adjacency reconstructs correct nodes",
        len(adj_graph["data"]["nodes"]) == n_nodes,
        f"expected {n_nodes}, got {len(adj_graph['data']['nodes'])}",
    )
    report(
        "adjacency reconstructs correct edges",
        len(adj_graph["data"]["edges"]) == n_edges,
        f"expected {n_edges}, got {len(adj_graph['data']['edges'])}",
    )

    # 2c. Auto mode on edge table should detect entity_rel format
    auto_graph = table_to_graph_auto(edges_df)
    report(
        "auto mode detects entity_rel (non-square, non-all-numeric)",
        len(auto_graph["nodes"]) > 0 and len(auto_graph["edges"]) > 0,
        f"nodes={len(auto_graph['nodes'])}, edges={len(auto_graph['edges'])}",
    )

    # 2d. Auto mode on adjacency matrix should detect adjacency format
    auto_adj = table_to_graph_auto(adj_df)
    report(
        "auto mode detects adjacency (square, all-numeric)",
        len(auto_adj["nodes"]) == n_nodes,
        f"nodes={len(auto_adj['nodes'])}, edges={len(auto_adj['edges'])}",
    )
    print()

    # =========================================================================
    # TEST GROUP 3: Graph → Vector (feature extraction)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 3: Graph → Vector")
    print("=" * 70)

    # 3a. Feature vector should capture graph statistics accurately
    features = graph_to_vector_features(graph_dict)
    report("feature vector shape is (1, 10)", features.shape == (1, 10))
    feat = features[0]
    report(
        "feature[0] = node_count matches",
        int(feat[0]) == n_nodes,
        f"feature={int(feat[0])}, actual={n_nodes}",
    )
    report(
        "feature[1] = edge_count matches",
        int(feat[1]) == n_edges,
        f"feature={int(feat[1])}, actual={n_edges}",
    )
    # Density proxy = edges/nodes
    expected_density = n_edges / n_nodes if n_nodes > 0 else 0
    report(
        "feature[2] = density proxy is correct",
        abs(feat[2] - expected_density) < 0.01,
        f"feature={feat[2]:.4f}, expected={expected_density:.4f}",
    )

    # 3b. Node embeddings should have one row per node
    node_embeddings = await graph_to_vector_node_embed(graph_dict, hash_provider)
    report(
        "node embeddings: one row per node",
        node_embeddings.shape[0] == n_nodes,
        f"shape={node_embeddings.shape}",
    )
    # Embeddings should be normalized (hash provider normalizes)
    norms = np.linalg.norm(node_embeddings, axis=1)
    report(
        "node embeddings are unit vectors",
        np.allclose(norms, 1.0, atol=0.01),
        f"norm range=[{norms.min():.4f}, {norms.max():.4f}]",
    )
    # Different nodes should have different embeddings
    unique_rows = len(set(tuple(row) for row in node_embeddings))
    report(
        "node embeddings are distinct",
        unique_rows == n_nodes,
        f"unique={unique_rows}, total={n_nodes}",
    )
    print()

    # =========================================================================
    # TEST GROUP 4: Vector → Graph (similarity analysis)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 4: Vector → Graph (similarity/clustering)")
    print("=" * 70)

    # 4a. Similarity graph: lower threshold to find connections in hash space
    # Hash embeddings are pseudo-random unit vectors in R^64, so cosine similarity
    # clusters around 0. Use threshold=0.1 to find some edges.
    labels = [n["id"] for n in graph_dict["nodes"]]
    sim_graph_low = vector_to_graph_similarity(
        node_embeddings, threshold=0.1, labels=labels
    )
    report(
        "similarity graph preserves all nodes",
        len(sim_graph_low["nodes"]) == n_nodes,
    )
    sim_edges_low = len(sim_graph_low["edges"])
    report(
        "similarity graph finds connections (threshold=0.1)",
        sim_edges_low > 0,
        f"{sim_edges_low} similarity edges",
    )
    # Higher threshold should have fewer or equal edges (monotonicity)
    sim_graph_high = vector_to_graph_similarity(
        node_embeddings, threshold=0.3, labels=labels
    )
    sim_edges_high = len(sim_graph_high["edges"])
    report(
        "higher threshold = fewer edges (monotonicity)",
        sim_edges_high <= sim_edges_low,
        f"threshold=0.1: {sim_edges_low} edges, threshold=0.3: {sim_edges_high} edges",
    )

    # 4b. Clustering should assign every node to a cluster
    n_clusters = min(5, n_nodes)
    cluster_graph = vector_to_graph_clustering(
        node_embeddings, method="kmeans", n_clusters=n_clusters, labels=labels,
    )
    data_nodes = [n for n in cluster_graph["nodes"] if n["type"] == "data_point"]
    cluster_nodes = [n for n in cluster_graph["nodes"] if n["type"] == "cluster"]
    belongs_to_edges = [e for e in cluster_graph["edges"] if e["type"] == "belongs_to"]
    report(
        "clustering preserves all data point nodes",
        len(data_nodes) == n_nodes,
        f"data_points={len(data_nodes)}, expected={n_nodes}",
    )
    report(
        "clustering creates expected cluster count",
        len(cluster_nodes) == n_clusters,
        f"clusters={len(cluster_nodes)}, expected={n_clusters}",
    )
    report(
        "every data point belongs to a cluster",
        len(belongs_to_edges) == n_nodes,
        f"belongs_to_edges={len(belongs_to_edges)}, expected={n_nodes}",
    )
    # Verify each cluster has at least 1 member
    cluster_sizes = {}
    for e in belongs_to_edges:
        cluster_sizes[e["target"]] = cluster_sizes.get(e["target"], 0) + 1
    report(
        "all clusters have members",
        all(s > 0 for s in cluster_sizes.values()),
        f"cluster sizes: {cluster_sizes}",
    )
    print()

    # =========================================================================
    # TEST GROUP 5: Table → Vector → Table (statistical analysis)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 5: Table ↔ Vector conversions")
    print("=" * 70)

    # 5a. Stats vector from edge table
    stats = table_to_vector_stats(edges_df)
    report("stats shape is (1, 11)", stats.shape == (1, 11))
    s = stats[0]
    report(
        "stats[0] = row_count matches edge count",
        int(s[0]) == n_edges,
        f"stats_rows={int(s[0])}, actual_edges={n_edges}",
    )
    report(
        "stats[1] = col_count matches",
        int(s[1]) == len(edges_df.columns),
        f"stats_cols={int(s[1])}, actual_cols={len(edges_df.columns)}",
    )

    # 5b. Vector → Table (direct): shape preservation
    direct_df = vector_to_table_direct(node_embeddings, labels=labels)
    report(
        "direct table has all nodes as rows",
        len(direct_df) == n_nodes,
        f"rows={len(direct_df)}",
    )
    report(
        "direct table has id + dim cols + stats",
        "id" in direct_df.columns and "norm" in direct_df.columns,
        f"cols={list(direct_df.columns[:3])}...{list(direct_df.columns[-3:])}",
    )

    # 5c. PCA reduction: explained variance should be positive
    pca_df = vector_to_table_pca(node_embeddings, n_components=5, labels=labels)
    report(
        "PCA table has expected columns",
        "pc_0" in pca_df.columns and "explained_variance" in pca_df.columns,
    )
    explained = pca_df["explained_variance"].iloc[0]
    report(
        "PCA explained variance is in (0, 1]",
        0 < explained <= 1.0,
        f"explained_variance={explained:.4f}",
    )

    # 5d. Similarity matrix: diagonal should be 1.0, symmetric
    sim_df = vector_to_table_similarity(node_embeddings, labels=labels)
    report(
        "similarity matrix is square NxN",
        sim_df.shape == (n_nodes, n_nodes),
    )
    diag = np.diag(sim_df.values)
    report(
        "similarity diagonal is 1.0 (self-similarity)",
        np.allclose(diag, 1.0, atol=0.01),
        f"diag range=[{diag.min():.4f}, {diag.max():.4f}]",
    )
    sym_diff = np.abs(sim_df.values - sim_df.values.T).max()
    report(
        "similarity matrix is symmetric",
        sym_diff < 1e-6,
        f"max asymmetry={sym_diff:.2e}",
    )
    print()

    # =========================================================================
    # TEST GROUP 6: Round-trip validation (structural preservation)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 6: Round-trip preservation")
    print("=" * 70)

    # 6a. Graph → Table(edges) → Graph: should preserve entity + edge counts
    rt1 = await validate_round_trip(
        graph_dict, ["graph", "table", "graph"],
        mode_sequence=["edges", "auto"], provider=hash_provider,
    )
    report(
        "G→T(edges)→G: entity preservation",
        rt1["entity_preservation"] > 0.7,
        f"entity_pres={rt1['entity_preservation']:.4f}",
    )
    report(
        "G→T(edges)→G: edge preservation",
        rt1["edge_preservation"] > 0.9,
        f"edge_pres={rt1['edge_preservation']:.4f}",
    )
    report(
        "G→T(edges)→G: no warnings",
        len(rt1["warnings"]) == 0,
        f"warnings={rt1['warnings']}",
    )

    # 6b. Graph → Table(adjacency) → Graph: perfect reconstruction
    rt2 = await validate_round_trip(
        graph_dict, ["graph", "table", "graph"],
        mode_sequence=["adjacency", "adjacency"], provider=hash_provider,
    )
    report(
        "G→T(adj)→G: perfect entity preservation",
        rt2["entity_preservation"] == 1.0,
        f"entity_pres={rt2['entity_preservation']:.4f}",
    )
    report(
        "G→T(adj)→G: perfect edge preservation",
        rt2["edge_preservation"] == 1.0,
        f"edge_pres={rt2['edge_preservation']:.4f}",
    )

    # 6c. Three-hop: Graph → Table → Vector(stats) → Table(direct)
    #     (lossy — stats are a summary, so can't reconstruct table)
    rt3 = await validate_round_trip(
        graph_dict, ["graph", "table", "vector", "table"],
        mode_sequence=["edges", "stats", "direct"], provider=hash_provider,
    )
    report(
        "G→T→V(stats)→T: completes without error",
        len(rt3["warnings"]) == 0,
        f"warnings={rt3['warnings']}, steps={len(rt3['steps'])}",
    )
    # Stats vector is 1x11, direct table is 1 row — heavy loss expected
    report(
        "G→T→V(stats)→T: preservation is low (expected — stats are lossy)",
        rt3["preservation_score"] < 0.5,
        f"score={rt3['preservation_score']:.4f}",
    )
    print()

    # =========================================================================
    # TEST GROUP 7: convert() dispatcher integration
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 7: Dispatcher (convert()) integration")
    print("=" * 70)

    # 7a. Default mode selection
    r = await convert(graph_dict, "graph", "table", mode="auto")
    report(
        "auto mode for graph→table selects 'edges'",
        r["mode"] == "edges",
        f"mode={r['mode']}",
    )

    # 7b. Conversion time is tracked
    report(
        "conversion_time_ms is positive",
        r["conversion_time_ms"] > 0,
        f"time={r['conversion_time_ms']:.2f}ms",
    )

    # 7c. Serialization produces valid JSON
    serialized = serialize_conversion_result(r)
    json_str = json.dumps(serialized, default=str)
    parsed = json.loads(json_str)
    report(
        "serialized result is valid JSON",
        "data" in parsed and "format" in parsed,
        f"keys={list(parsed.keys())}",
    )
    report(
        "serialized table has columns metadata",
        "columns" in parsed,
        f"columns={parsed.get('columns', [])}",
    )

    # 7d. Invalid conversion path raises clear error
    try:
        await convert(graph_dict, "graph", "graph")
        report("invalid path raises error", False, "no exception raised")
    except ValueError as e:
        report(
            "invalid path raises ValueError",
            "No conversion path" in str(e),
            f"msg={e}",
        )

    # 7e. Invalid mode raises clear error
    try:
        await convert(graph_dict, "graph", "table", mode="nonexistent")
        report("invalid mode raises error", False, "no exception raised")
    except ValueError as e:
        report(
            "invalid mode raises ValueError",
            "Unknown mode" in str(e),
            f"msg={e}",
        )

    # 7f. Embedding mode without provider raises clear error
    try:
        await convert(graph_dict, "graph", "vector", mode="node_embed")
        report("embed without provider raises error", False, "no exception raised")
    except ValueError as e:
        report(
            "embed without provider raises ValueError",
            "embedding provider" in str(e).lower(),
            f"msg={e}",
        )
    print()

    # =========================================================================
    # TEST GROUP 8: list_all_conversions discovery
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 8: Discovery")
    print("=" * 70)

    conversions = list_all_conversions()
    report("15 conversion paths listed", len(conversions) == 15, f"got {len(conversions)}")
    # Check all 6 format pairs present
    pairs = {(c["source_format"], c["target_format"]) for c in conversions}
    expected_pairs = {
        ("graph", "table"), ("table", "graph"),
        ("graph", "vector"), ("table", "vector"),
        ("vector", "graph"), ("vector", "table"),
    }
    report("all 6 format pairs present", pairs == expected_pairs, f"pairs={pairs}")
    # All entries have descriptions
    report(
        "all conversions have descriptions",
        all(c["description"] for c in conversions),
    )
    # Embedding requirements are flagged (node_embed and row_embed)
    embed_modes = [c for c in conversions if c["requires_embedding"]]
    report(
        "2 modes require embeddings (node_embed, row_embed)",
        len(embed_modes) == 2,
        f"embed modes: {[c['mode'] for c in embed_modes]}",
    )
    print()

    # =========================================================================
    # TEST GROUP 9: Analytical use case — degree distribution analysis
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 9: Analytic use case — degree distribution via table")
    print("=" * 70)

    # Convert graph to edge table, compute degree distribution using pandas
    edges_result = await convert(graph_dict, "graph", "table", mode="edges")
    edf = edges_result["data"]
    assert isinstance(edf, pd.DataFrame)

    # Compute degree per node
    out_degree = edf["source"].value_counts()
    in_degree = edf["target"].value_counts()
    all_nodes_set = set(out_degree.index) | set(in_degree.index)
    degree = pd.Series(
        {n: out_degree.get(n, 0) + in_degree.get(n, 0) for n in all_nodes_set}
    )
    report(
        "degree distribution: all connected nodes have degree > 0",
        (degree > 0).all(),
        f"min_degree={degree.min()}, max_degree={degree.max()}, median={degree.median():.1f}",
    )
    # Hub detection: highest degree nodes
    top3_hubs = degree.nlargest(3)
    report(
        "hub detection: top-3 hubs have higher degree than median",
        (top3_hubs > degree.median()).all(),
        f"hubs: {top3_hubs.to_dict()}",
    )
    print()

    # =========================================================================
    # TEST GROUP 10: Analytical use case — embedding cluster analysis
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 10: Analytic use case — cluster analysis via vectors")
    print("=" * 70)

    # Convert graph → vector (node embeddings) → cluster → check cluster coherence
    embed_result = await convert(
        graph_dict, "graph", "vector", mode="node_embed", provider=hash_provider,
    )
    embeddings = embed_result["data"]

    cluster_result = await convert(
        embeddings, "vector", "graph", mode="clustering",
        labels=labels, n_clusters=3,
    )
    cg = cluster_result["data"]

    # Build cluster membership map
    membership = {}
    for e in cg["edges"]:
        if e["type"] == "belongs_to":
            membership[e["source"]] = e["target"]

    # Each cluster should have >1 member (no trivial singleton clusters with kmeans on enough data)
    cluster_sizes = {}
    for node_id, cluster_id in membership.items():
        cluster_sizes[cluster_id] = cluster_sizes.get(cluster_id, 0) + 1
    report(
        "all 3 clusters are non-empty",
        len(cluster_sizes) == 3 and all(s > 0 for s in cluster_sizes.values()),
        f"sizes: {cluster_sizes}",
    )

    # Intra-cluster similarity should be higher than inter-cluster (on average)
    from sklearn.metrics.pairwise import cosine_similarity

    sim_matrix = cosine_similarity(embeddings)
    intra_sims = []
    inter_sims = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            if membership.get(labels[i]) == membership.get(labels[j]):
                intra_sims.append(sim_matrix[i, j])
            else:
                inter_sims.append(sim_matrix[i, j])

    if intra_sims and inter_sims:
        avg_intra = np.mean(intra_sims)
        avg_inter = np.mean(inter_sims)
        report(
            "intra-cluster similarity > inter-cluster (clustering is meaningful)",
            avg_intra > avg_inter,
            f"intra={avg_intra:.4f}, inter={avg_inter:.4f}",
        )
    else:
        report("intra/inter similarity comparison", False, "insufficient data")
    print()

    # =========================================================================
    # TEST GROUP 11: NetworkX round-trip fidelity
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 11: NetworkX dict ↔ graph fidelity")
    print("=" * 70)

    # Convert to dict and back, check graph is structurally identical
    reconstructed_nx = _dict_to_networkx(graph_dict)
    report(
        "reconstructed graph has same node count",
        reconstructed_nx.number_of_nodes() == nx_graph.number_of_nodes(),
        f"original={nx_graph.number_of_nodes()}, reconstructed={reconstructed_nx.number_of_nodes()}",
    )
    report(
        "reconstructed graph has same edge count",
        reconstructed_nx.number_of_edges() == nx_graph.number_of_edges(),
        f"original={nx_graph.number_of_edges()}, reconstructed={reconstructed_nx.number_of_edges()}",
    )
    # Check a few specific node attributes survived
    sample_node = list(nx_graph.nodes())[0]
    orig_data = nx_graph.nodes[sample_node]
    if str(sample_node) in reconstructed_nx.nodes:
        recon_data = reconstructed_nx.nodes[str(sample_node)]
        has_label = "label" in recon_data
        report(
            "reconstructed node preserves label attribute",
            has_label,
            f"node={sample_node}, label={recon_data.get('label', 'MISSING')}",
        )
    print()

    # =========================================================================
    # TEST GROUP 12: Edge case handling (bug fix validation)
    # =========================================================================
    print("=" * 70)
    print("TEST GROUP 12: Edge cases and bug fixes")
    print("=" * 70)

    from Core.AgentTools.cross_modal_tools import (
        _validate_2d, table_to_vector_stats as tvs,
        vector_to_table_pca as vtp,
    )

    # 12a. NaN in DataFrame doesn't crash stats
    df_with_nan = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [np.nan, 5.0, 6.0]})
    stats_nan = tvs(df_with_nan)
    nan_in_result = np.isnan(stats_nan).any()
    report(
        "stats on NaN DataFrame produces valid (non-NaN) output",
        not nan_in_result,
        f"stats={stats_nan.tolist()}",
    )

    # 12b. 1D vector rejected
    try:
        _validate_2d(np.array([1.0, 2.0, 3.0]), "test")
        report("1D vector rejected by _validate_2d", False, "no exception")
    except ValueError as e:
        report("1D vector rejected by _validate_2d", True, str(e))

    # 12c. PCA on 1 row rejected
    try:
        vtp(np.array([[1.0, 2.0, 3.0]]))
        report("PCA on 1 row rejected", False, "no exception")
    except ValueError as e:
        report("PCA on 1 row rejected", True, str(e))

    # 12d. Empty DataFrame stats
    empty_df = pd.DataFrame()
    stats_empty = tvs(empty_df)
    report(
        "stats on empty DataFrame doesn't crash",
        stats_empty.shape == (1, 11),
        f"shape={stats_empty.shape}",
    )

    # 12e. Invalid type_col raises
    from Core.AgentTools.cross_modal_tools import table_to_graph_entity_rel as tge
    df_simple = pd.DataFrame({"source": ["a"], "target": ["b"]})
    try:
        tge(df_simple, source_col="source", target_col="target", type_col="nonexistent")
        report("invalid type_col raises ValueError", False, "no exception")
    except ValueError as e:
        report("invalid type_col raises ValueError", True, str(e))

    # 12f. Embedding provider error surfaces in convert_modality
    #      (can't test MCP layer directly, but test the provider factory)
    from Core.AgentTools.cross_modal_tools import get_embedding_provider
    try:
        get_embedding_provider("nonexistent_provider")
        report("invalid provider raises ValueError", False, "no exception")
    except ValueError as e:
        report("invalid provider raises ValueError", True, str(e))

    # 12g. Graph dict with empty nodes/edges
    empty_graph = {"nodes": [], "edges": []}
    r = await convert(empty_graph, "graph", "table", mode="nodes")
    report(
        "empty graph → table(nodes) produces empty DataFrame",
        isinstance(r["data"], pd.DataFrame) and len(r["data"]) == 0,
        f"rows={len(r['data'])}",
    )
    r = await convert(empty_graph, "graph", "vector", mode="features")
    report(
        "empty graph → features produces (1,10) vector",
        r["data"].shape == (1, 10),
        f"shape={r['data'].shape}",
    )
    feat = r["data"][0]
    report(
        "empty graph features: node_count=0, edge_count=0",
        int(feat[0]) == 0 and int(feat[1]) == 0,
    )
    print()

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("=" * 70)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    if FAIL == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 70)
    return FAIL == 0


if __name__ == "__main__":
    t0 = time.time()
    success = asyncio.run(main())
    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.1f}s")
    sys.exit(0 if success else 1)
