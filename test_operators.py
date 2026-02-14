#!/usr/bin/env python3
"""Integration test for all DIGIMON operators.

Runs Leiden clustering on the graph first so community operators work,
and picks connected entities from the largest CC for subgraph operators.
"""
import asyncio
import sys
import os

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

async def test():
    import networkx as nx
    from collections import defaultdict
    from Option.Config2 import Config
    from Core.Provider.LiteLLMProvider import LiteLLMProvider
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentSchema.context import GraphRAGContext
    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs

    config = Config.from_yaml_file('Option/Config2.yaml')
    llm = LiteLLMProvider(config.llm)
    encoder = get_rag_embedding(config=config)
    chunk_factory = ChunkFactory(config)
    context = GraphRAGContext(
        target_dataset_name='Fictional_Test', main_config=config,
        llm_provider=llm, embedding_provider=encoder, chunk_storage_manager=chunk_factory,
    )

    # --- Build or load graph ---
    build_inputs = BuildERGraphInputs(target_dataset_name='Fictional_Test', force_rebuild=False)
    build_result = await build_er_graph(build_inputs, config, llm, encoder, chunk_factory)
    gi = getattr(build_result, 'graph_instance', None)
    if gi:
        if hasattr(gi, '_graph') and hasattr(gi._graph, 'namespace'):
            gi._graph.namespace = chunk_factory.get_namespace('Fictional_Test')
        context.add_graph_instance(build_result.graph_id, gi)

    GRAPH_ID = build_result.graph_id
    nx_g = context.get_graph_instance(GRAPH_ID)._graph.graph
    all_nodes = list(nx_g.nodes())
    all_edges = list(nx_g.edges())
    print(f"Graph: {GRAPH_ID}, {len(all_nodes)} nodes, {nx_g.number_of_edges()} edges")

    # --- Run Leiden clustering so community operators work ---
    print("\n--- Running Leiden clustering on largest connected component ---")
    try:
        from graspologic.partition import hierarchical_leiden
        from graspologic.utils import largest_connected_component
        from Core.Common.Utils import clean_str
        import json as _json

        # Get the largest connected component
        graph_copy = nx_g.copy()
        lcc = largest_connected_component(graph_copy)
        # Normalize node names (matching NetworkXStorage.stable_largest_connected_component)
        import html
        node_mapping = {node: html.unescape(node.upper().strip()) for node in lcc.nodes()}
        lcc = nx.relabel_nodes(lcc, node_mapping)
        print(f"  Largest CC: {lcc.number_of_nodes()} nodes, {lcc.number_of_edges()} edges")

        # Run Leiden clustering
        community_mapping = hierarchical_leiden(lcc, max_cluster_size=30, random_seed=42)
        node_communities = defaultdict(list)
        levels = defaultdict(set)
        for partition in community_mapping:
            node_communities[clean_str(partition.node)].append(
                {"level": partition.level, "cluster": str(partition.cluster)}
            )
            levels[partition.level].add(partition.cluster)
        print(f"  Leiden levels: {dict({k: len(v) for k, v in levels.items()})}")

        # Inject cluster data into graph nodes
        for node_id, clusters in node_communities.items():
            if node_id in nx_g.nodes:
                nx_g.nodes[node_id]["clusters"] = _json.dumps(clusters)

        # Verify: count nodes with clusters attribute
        clustered = sum(1 for _, d in nx_g.nodes(data=True) if "clusters" in d)
        print(f"  Injected cluster data into {clustered}/{len(all_nodes)} nodes")
    except ImportError as e:
        print(f"  SKIP clustering: {e}")
    except Exception as e:
        print(f"  WARN clustering failed: {e}")

    # --- Pick connected entities from the largest CC for subgraph tests ---
    # Find a connected path: start -> mid -> end (guaranteed 2-hop reachable)
    connected_start = connected_mid = connected_end = None
    for u, v in nx_g.edges():
        # Find a 2-hop neighbor
        for w in nx_g.neighbors(v):
            if w != u:
                connected_start, connected_mid, connected_end = u, v, w
                break
        if connected_end:
            break
    if not connected_start:
        # Fallback to first edge
        connected_start, connected_mid = all_edges[0]
        connected_end = list(nx_g.neighbors(connected_mid))[0] if list(nx_g.neighbors(connected_mid)) else connected_start

    sample = all_nodes[:5]
    edges_list = all_edges[:5]
    print(f"\n  Connected test triple: {connected_start} -> {connected_mid} -> {connected_end}")

    results = {}

    # =========================================
    # NON-LLM OPERATOR TESTS
    # =========================================

    # 1: Relationship.ScoreAggregator
    try:
        from Core.AgentTools.relationship_tools import relationship_score_aggregator_tool
        from Core.AgentSchema.tool_contracts import RelationshipScoreAggregatorInputs
        entity_scores = {e: 1.0/(i+1) for i, e in enumerate(sample)}
        params = RelationshipScoreAggregatorInputs(
            entity_scores=entity_scores, graph_reference_id=GRAPH_ID,
            top_k_relationships=5, aggregation_method='sum')
        r = await relationship_score_aggregator_tool(params, context)
        if r.scored_relationships:
            top = r.scored_relationships[0]
            results['Rel.ScoreAggregator'] = f'PASS ({len(r.scored_relationships)} rels, top_score={top[1]:.3f})'
        else:
            results['Rel.ScoreAggregator'] = 'FAIL (empty)'
    except Exception as e:
        results['Rel.ScoreAggregator'] = f'FAIL: {e}'

    # 2: Chunk.Occurrence
    try:
        from Core.AgentTools.chunk_tools import chunk_occurrence_tool
        from Core.AgentSchema.tool_contracts import ChunkOccurrenceInputs
        pairs = [{'entity1_id': u, 'entity2_id': v} for u, v in edges_list[:3]]
        params = ChunkOccurrenceInputs(
            target_entity_pairs_in_relationship=pairs,
            document_collection_id=GRAPH_ID, top_k_chunks=5)
        r = await chunk_occurrence_tool(params, context)
        n = len(r.ranked_occurrence_chunks)
        results['Chunk.Occurrence'] = f'PASS ({n} chunks)' if n > 0 else 'WARN (0 co-occurring chunks)'
    except Exception as e:
        results['Chunk.Occurrence'] = f'FAIL: {e}'

    # 3: Community.DetectFromEntities
    try:
        from Core.AgentTools.community_tools import community_detect_from_entities_tool
        from Core.AgentSchema.tool_contracts import CommunityDetectFromEntitiesInputs
        params = CommunityDetectFromEntitiesInputs(
            graph_reference_id=GRAPH_ID, seed_entity_ids=sample[:3],
            max_communities_to_return=3)
        r = await community_detect_from_entities_tool(params, context)
        n = len(r.relevant_communities)
        if n > 0:
            c = r.relevant_communities[0]
            results['Community.Detect'] = f'PASS ({n} communities, top has {len(c.nodes)} nodes)'
        else:
            results['Community.Detect'] = 'WARN (0 communities - check clustering)'
    except Exception as e:
        results['Community.Detect'] = f'FAIL: {e}'

    # 4: Community.GetLayer
    try:
        from Core.AgentTools.community_tools import community_get_layer_tool
        from Core.AgentSchema.tool_contracts import CommunityGetLayerInputs
        params = CommunityGetLayerInputs(
            community_hierarchy_reference_id=GRAPH_ID, max_layer_depth=2)
        r = await community_get_layer_tool(params, context)
        n = len(r.communities_in_layers)
        if n > 0:
            level_counts = defaultdict(int)
            for c in r.communities_in_layers:
                level_counts[c.level] += 1
            results['Community.GetLayer'] = f'PASS ({n} communities, levels={dict(level_counts)})'
        else:
            results['Community.GetLayer'] = 'WARN (0 communities - check clustering)'
    except Exception as e:
        results['Community.GetLayer'] = f'FAIL: {e}'

    # 5: Subgraph.KHopPaths (use connected entities)
    try:
        from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool
        from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs
        params = SubgraphKHopPathsInputs(
            graph_reference_id=GRAPH_ID,
            start_entity_ids=[connected_start],
            end_entity_ids=[connected_end],
            k_hops=4, max_paths_to_return=5)
        r = await subgraph_khop_paths_tool(params, context)
        if r.discovered_paths:
            p = r.discovered_paths[0]
            path_str = ' -> '.join(s.label for s in p.segments[:7])
            results['Subgraph.KHopPaths'] = f'PASS ({len(r.discovered_paths)} paths, e.g. {path_str})'
        else:
            results['Subgraph.KHopPaths'] = 'WARN (no paths)'
    except Exception as e:
        results['Subgraph.KHopPaths'] = f'FAIL: {e}'

    # 6: Subgraph.SteinerTree (use connected entities from same component)
    try:
        from Core.AgentTools.subgraph_tools import subgraph_steiner_tree_tool
        from Core.AgentSchema.tool_contracts import SubgraphSteinerTreeInputs
        terminals = [connected_start, connected_mid, connected_end]
        params = SubgraphSteinerTreeInputs(
            graph_reference_id=GRAPH_ID, terminal_node_ids=terminals)
        r = await subgraph_steiner_tree_tool(params, context)
        n = len(r.steiner_tree_edges)
        if n > 0:
            results['Subgraph.SteinerTree'] = f'PASS ({n} edges connecting {len(terminals)} terminals)'
        else:
            results['Subgraph.SteinerTree'] = 'WARN (0 edges)'
    except Exception as e:
        results['Subgraph.SteinerTree'] = f'FAIL: {e}'

    # 7: Entity.TFIDF
    try:
        from Core.AgentTools.entity_tools import entity_tfidf_tool
        from Core.AgentSchema.tool_contracts import EntityTFIDFInputs
        params = EntityTFIDFInputs(
            candidate_entity_ids=all_nodes[:20],
            query_text='empire technology crystal',
            graph_reference_id=GRAPH_ID, top_k=5)
        r = await entity_tfidf_tool(params, context)
        if r.ranked_entities:
            top = r.ranked_entities[0]
            results['Entity.TFIDF'] = f'PASS (top: {top[0]}, score={top[1]:.3f})'
        else:
            results['Entity.TFIDF'] = 'FAIL (empty)'
    except Exception as e:
        results['Entity.TFIDF'] = f'FAIL: {e}'

    # 8: Entity.Link (needs entity VDB — test graceful degradation without one)
    try:
        from Core.AgentTools.entity_tools import entity_link_tool
        from Core.AgentSchema.tool_contracts import EntityLinkInputs
        params = EntityLinkInputs(
            source_entities=[connected_start, connected_mid],
            knowledge_base_reference_id=None,
            similarity_threshold=0.5)
        r = await entity_link_tool(params, context)
        n_linked = sum(1 for p in r.linked_entities_results if p.link_status == 'linked')
        n_total = len(r.linked_entities_results)
        results['Entity.Link'] = f'PASS (graceful: {n_linked}/{n_total} linked, no VDB)'
    except Exception as e:
        results['Entity.Link'] = f'FAIL: {e}'

    # =========================================
    # PIPELINE COMPOSITION TESTS
    # =========================================
    print('\n--- Pipeline Composition Tests ---')

    # Pipeline A: FastGraphRAG = Entity.PPR → Relationship.ScoreAggregator → Chunk.Aggregator
    try:
        from Core.AgentTools.entity_tools import entity_ppr_tool
        from Core.AgentSchema.tool_contracts import EntityPPRInputs
        from Core.AgentTools.relationship_tools import relationship_score_aggregator_tool
        from Core.AgentSchema.tool_contracts import RelationshipScoreAggregatorInputs
        from Core.AgentTools.chunk_tools import chunk_aggregator_tool, chunk_occurrence_tool
        from Core.AgentSchema.tool_contracts import (
            ChunkRelationshipScoreAggregatorInputs,
            ChunkOccurrenceInputs, ChunkData
        )

        # Step 1: Entity.PPR
        ppr_params = EntityPPRInputs(
            graph_reference_id=GRAPH_ID,
            seed_entity_ids=[connected_start],
            top_k_results=10)
        ppr_result = await entity_ppr_tool(ppr_params, context)
        ppr_entities = dict(ppr_result.ranked_entities)
        ppr_step = f'{len(ppr_entities)} entities'

        # Step 2: Relationship.ScoreAggregator using PPR scores
        agg_params = RelationshipScoreAggregatorInputs(
            entity_scores=ppr_entities,
            graph_reference_id=GRAPH_ID,
            top_k_relationships=10,
            aggregation_method='sum')
        agg_result = await relationship_score_aggregator_tool(agg_params, context)
        rel_scores = {f"{r[0].src_id}->{r[0].tgt_id}": r[1] for r in agg_result.scored_relationships}
        agg_step = f'{len(rel_scores)} rels'

        # Step 3: Chunk.Occurrence as proxy for chunk retrieval
        # (Chunk.Aggregator needs chunk_candidates, use occurrence to get chunks first)
        co_pairs = [{'entity1_id': u, 'entity2_id': v} for u, v in edges_list[:5]]
        co_params = ChunkOccurrenceInputs(
            target_entity_pairs_in_relationship=co_pairs,
            document_collection_id=GRAPH_ID, top_k_chunks=10)
        co_result = await chunk_occurrence_tool(co_params, context)
        chunk_step = f'{len(co_result.ranked_occurrence_chunks)} chunks'

        results['Pipeline:FastGraphRAG'] = f'PASS (PPR→{ppr_step}, ScoreAgg→{agg_step}, Chunks→{chunk_step})'
    except Exception as e:
        results['Pipeline:FastGraphRAG'] = f'FAIL: {e}'

    # Pipeline B: GGraphRAG = Community.DetectFromEntities → Community.GetLayer
    try:
        from Core.AgentTools.community_tools import community_detect_from_entities_tool, community_get_layer_tool
        from Core.AgentSchema.tool_contracts import CommunityDetectFromEntitiesInputs, CommunityGetLayerInputs

        # Step 1: Detect communities from seed entities
        detect_params = CommunityDetectFromEntitiesInputs(
            graph_reference_id=GRAPH_ID,
            seed_entity_ids=[connected_start, connected_mid, connected_end],
            max_communities_to_return=5)
        detect_result = await community_detect_from_entities_tool(detect_params, context)
        detect_step = f'{len(detect_result.relevant_communities)} communities'

        # Step 2: Get layer info
        layer_params = CommunityGetLayerInputs(
            community_hierarchy_reference_id=GRAPH_ID, max_layer_depth=3)
        layer_result = await community_get_layer_tool(layer_params, context)
        layer_step = f'{len(layer_result.communities_in_layers)} at depth<=3'

        if detect_result.relevant_communities or layer_result.communities_in_layers:
            results['Pipeline:GGraphRAG'] = f'PASS (Detect→{detect_step}, Layer→{layer_step})'
        else:
            results['Pipeline:GGraphRAG'] = f'WARN (Detect→{detect_step}, Layer→{layer_step})'
    except Exception as e:
        results['Pipeline:GGraphRAG'] = f'FAIL: {e}'

    # Pipeline C: ToG-lite = Entity.TFIDF → Subgraph.KHopPaths
    # (skip Entity.Agent and Subgraph.AgentPath since they need LLM)
    try:
        from Core.AgentTools.entity_tools import entity_tfidf_tool
        from Core.AgentSchema.tool_contracts import EntityTFIDFInputs
        from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool
        from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs

        # Step 1: Find relevant entities via TF-IDF
        tfidf_params = EntityTFIDFInputs(
            candidate_entity_ids=all_nodes[:30],
            query_text='empire technology crystal power',
            graph_reference_id=GRAPH_ID, top_k=5)
        tfidf_result = await entity_tfidf_tool(tfidf_params, context)
        top_entities = [e[0] for e in tfidf_result.ranked_entities[:3]]
        tfidf_step = f'{len(tfidf_result.ranked_entities)} entities'

        # Step 2: Find paths between top entities
        if len(top_entities) >= 2:
            khop_params = SubgraphKHopPathsInputs(
                graph_reference_id=GRAPH_ID,
                start_entity_ids=[top_entities[0]],
                end_entity_ids=top_entities[1:],
                k_hops=4, max_paths_to_return=5)
            khop_result = await subgraph_khop_paths_tool(khop_params, context)
            path_step = f'{len(khop_result.discovered_paths)} paths'
        else:
            path_step = 'skipped (< 2 entities)'

        results['Pipeline:ToG-lite'] = f'PASS (TFIDF→{tfidf_step}, KHop→{path_step})'
    except Exception as e:
        results['Pipeline:ToG-lite'] = f'FAIL: {e}'

    # =========================================
    # SUMMARY
    # =========================================
    print('\n========== INTEGRATION TEST RESULTS ==========')
    for op, st in results.items():
        marker = 'OK' if 'PASS' in st else '!!' if 'FAIL' in st else '~~'
        print(f'  [{marker}] {op}: {st}')
    n_pass = sum(1 for s in results.values() if 'PASS' in s)
    n_warn = sum(1 for s in results.values() if 'WARN' in s)
    n_fail = sum(1 for s in results.values() if 'FAIL' in s)
    print(f'\n  {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL out of {len(results)} tests')
    return n_pass, n_warn, n_fail

asyncio.run(test())
