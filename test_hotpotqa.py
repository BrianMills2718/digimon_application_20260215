#!/usr/bin/env python3
"""End-to-end test on HotpotQAsmallest: build graph, cluster, run all operators.

This validates the full pipeline on real-world data (multi-hop QA dataset).
"""
import asyncio
import sys
import os
import json
import time

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATASET = 'HotpotQAsmallest'

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
        target_dataset_name=DATASET, main_config=config,
        llm_provider=llm, embedding_provider=encoder, chunk_storage_manager=chunk_factory,
    )

    # Load questions
    with open(f'Data/{DATASET}/Question.json') as f:
        questions = [json.loads(line) for line in f]
    print(f"Loaded {len(questions)} questions from {DATASET}")

    # ===== STEP 1: Build ER Graph =====
    print(f"\n{'='*60}")
    print(f"STEP 1: Build ER Graph from {DATASET} corpus (50 docs)")
    print(f"{'='*60}")
    t0 = time.time()
    build_inputs = BuildERGraphInputs(target_dataset_name=DATASET, force_rebuild=False)
    build_result = await build_er_graph(build_inputs, config, llm, encoder, chunk_factory)
    gi = getattr(build_result, 'graph_instance', None)
    if gi:
        if hasattr(gi, '_graph') and hasattr(gi._graph, 'namespace'):
            gi._graph.namespace = chunk_factory.get_namespace(DATASET)
        context.add_graph_instance(build_result.graph_id, gi)
    build_time = time.time() - t0

    GRAPH_ID = build_result.graph_id
    nx_g = context.get_graph_instance(GRAPH_ID)._graph.graph
    all_nodes = list(nx_g.nodes())
    all_edges = list(nx_g.edges())
    print(f"  Graph: {GRAPH_ID}")
    print(f"  Nodes: {len(all_nodes)}, Edges: {len(all_edges)}")
    print(f"  Build time: {build_time:.1f}s")

    # ===== STEP 2: Run Leiden clustering =====
    print(f"\n{'='*60}")
    print("STEP 2: Leiden clustering")
    print(f"{'='*60}")
    try:
        from graspologic.partition import hierarchical_leiden
        from graspologic.utils import largest_connected_component
        from Core.Common.Utils import clean_str
        import html

        graph_copy = nx_g.copy()
        lcc = largest_connected_component(graph_copy)
        node_mapping = {node: html.unescape(node.upper().strip()) for node in lcc.nodes()}
        lcc = nx.relabel_nodes(lcc, node_mapping)
        print(f"  Largest CC: {lcc.number_of_nodes()} nodes, {lcc.number_of_edges()} edges")

        community_mapping = hierarchical_leiden(lcc, max_cluster_size=30, random_seed=42)
        node_communities = defaultdict(list)
        levels = defaultdict(set)
        for partition in community_mapping:
            node_communities[clean_str(partition.node)].append(
                {"level": partition.level, "cluster": str(partition.cluster)}
            )
            levels[partition.level].add(partition.cluster)
        print(f"  Leiden levels: {dict({k: len(v) for k, v in levels.items()})}")

        for node_id, clusters in node_communities.items():
            if node_id in nx_g.nodes:
                nx_g.nodes[node_id]["clusters"] = json.dumps(clusters)
        clustered = sum(1 for _, d in nx_g.nodes(data=True) if "clusters" in d)
        print(f"  Injected cluster data into {clustered}/{len(all_nodes)} nodes")
    except Exception as e:
        print(f"  Clustering failed: {e}")

    # Find connected entities for tests
    connected_start = connected_mid = connected_end = None
    for u, v in nx_g.edges():
        for w in nx_g.neighbors(v):
            if w != u:
                connected_start, connected_mid, connected_end = u, v, w
                break
        if connected_end:
            break

    results = {}

    # ===== STEP 3: Non-LLM Operator Tests =====
    print(f"\n{'='*60}")
    print("STEP 3: Non-LLM Operator Tests")
    print(f"{'='*60}")

    # Relationship.ScoreAggregator
    try:
        from Core.AgentTools.relationship_tools import relationship_score_aggregator_tool
        from Core.AgentSchema.tool_contracts import RelationshipScoreAggregatorInputs
        sample = all_nodes[:5]
        entity_scores = {e: 1.0/(i+1) for i, e in enumerate(sample)}
        params = RelationshipScoreAggregatorInputs(
            entity_scores=entity_scores, graph_reference_id=GRAPH_ID,
            top_k_relationships=5, aggregation_method='sum')
        r = await relationship_score_aggregator_tool(params, context)
        results['Rel.ScoreAggregator'] = f'PASS ({len(r.scored_relationships)} rels)'
    except Exception as e:
        results['Rel.ScoreAggregator'] = f'FAIL: {e}'

    # Entity.TFIDF
    try:
        from Core.AgentTools.entity_tools import entity_tfidf_tool
        from Core.AgentSchema.tool_contracts import EntityTFIDFInputs
        params = EntityTFIDFInputs(
            candidate_entity_ids=all_nodes[:30],
            query_text='director film movie actor',
            graph_reference_id=GRAPH_ID, top_k=5)
        r = await entity_tfidf_tool(params, context)
        if r.ranked_entities:
            top = r.ranked_entities[0]
            results['Entity.TFIDF'] = f'PASS (top: {top[0]}, score={top[1]:.3f})'
        else:
            results['Entity.TFIDF'] = 'FAIL (empty)'
    except Exception as e:
        results['Entity.TFIDF'] = f'FAIL: {e}'

    # Community.DetectFromEntities + GetLayer
    try:
        from Core.AgentTools.community_tools import community_detect_from_entities_tool, community_get_layer_tool
        from Core.AgentSchema.tool_contracts import CommunityDetectFromEntitiesInputs, CommunityGetLayerInputs
        params = CommunityDetectFromEntitiesInputs(
            graph_reference_id=GRAPH_ID, seed_entity_ids=all_nodes[:3],
            max_communities_to_return=3)
        r = await community_detect_from_entities_tool(params, context)
        n = len(r.relevant_communities)
        results['Community.Detect'] = f'PASS ({n} communities)' if n > 0 else 'WARN (no communities)'

        params2 = CommunityGetLayerInputs(
            community_hierarchy_reference_id=GRAPH_ID, max_layer_depth=2)
        r2 = await community_get_layer_tool(params2, context)
        results['Community.GetLayer'] = f'PASS ({len(r2.communities_in_layers)} communities)'
    except Exception as e:
        results['Community'] = f'FAIL: {e}'

    # Subgraph.KHopPaths + SteinerTree
    if connected_start:
        try:
            from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool, subgraph_steiner_tree_tool
            from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs, SubgraphSteinerTreeInputs
            params = SubgraphKHopPathsInputs(
                graph_reference_id=GRAPH_ID,
                start_entity_ids=[connected_start],
                end_entity_ids=[connected_end],
                k_hops=4, max_paths_to_return=5)
            r = await subgraph_khop_paths_tool(params, context)
            n = len(r.discovered_paths)
            results['Subgraph.KHopPaths'] = f'PASS ({n} paths)' if n > 0 else 'WARN (no paths)'

            params2 = SubgraphSteinerTreeInputs(
                graph_reference_id=GRAPH_ID,
                terminal_node_ids=[connected_start, connected_mid, connected_end])
            r2 = await subgraph_steiner_tree_tool(params2, context)
            results['Subgraph.SteinerTree'] = f'PASS ({len(r2.steiner_tree_edges)} edges)'
        except Exception as e:
            results['Subgraph'] = f'FAIL: {e}'

    # ===== STEP 4: LLM Operator Tests with HotPotQA question =====
    print(f"\n{'='*60}")
    print("STEP 4: LLM Operators on HotPotQA question")
    print(f"{'='*60}")

    # Pick a question and use the relevant docs
    q = questions[0]  # "Were Scott Derrickson and Ed Wood of the same nationality?"
    print(f"  Q: {q['question']}")
    print(f"  Expected answer: {q['answer']}")

    # Load relevant corpus docs
    with open(f'Data/{DATASET}/Corpus.json') as f:
        docs = [json.loads(line) for line in f]
    # Use first few docs as context (they're relevant to q0)
    text_context = "\n\n".join(d['context'] for d in docs[:5])

    # Entity.Agent
    try:
        from Core.AgentTools.entity_tools import entity_agent_tool
        from Core.AgentSchema.tool_contracts import EntityAgentInputs
        params = EntityAgentInputs(
            query_text=q['question'],
            text_context=text_context,
            target_entity_types=["person", "film", "nationality"],
            max_entities_to_extract=8)
        r = await entity_agent_tool(params, context)
        names = [e.entity_name for e in r.extracted_entities]
        print(f"  Entity.Agent: {names}")
        results['Entity.Agent'] = f'PASS ({len(r.extracted_entities)} entities: {", ".join(names[:4])})'
    except Exception as e:
        results['Entity.Agent'] = f'FAIL: {e}'

    # Relationship.Agent
    try:
        from Core.AgentTools.relationship_tools import relationship_agent_tool
        from Core.AgentSchema.tool_contracts import RelationshipAgentInputs, ExtractedEntityData
        context_entities = [
            ExtractedEntityData(entity_name="Scott Derrickson", source_id="test",
                              entity_type="person", description="American director"),
            ExtractedEntityData(entity_name="Ed Wood", source_id="test",
                              entity_type="person", description="Cult filmmaker"),
        ]
        params = RelationshipAgentInputs(
            query_text=q['question'],
            text_context=text_context,
            context_entities=context_entities,
            max_relationships_to_extract=5)
        r = await relationship_agent_tool(params, context)
        for rel in r.extracted_relationships[:3]:
            rname = getattr(rel, 'relation_name', '') or ''
            print(f"    {rel.src_id} --[{rname}]--> {rel.tgt_id}")
        results['Relationship.Agent'] = f'PASS ({len(r.extracted_relationships)} relationships)'
    except Exception as e:
        results['Relationship.Agent'] = f'FAIL: {e}'

    # ===== STEP 5: Full ToG Pipeline on HotPotQA =====
    print(f"\n{'='*60}")
    print("STEP 5: ToG Pipeline (Entity.Agent → KHopPaths → AgentPath)")
    print(f"{'='*60}")
    try:
        from Core.AgentTools.entity_tools import entity_agent_tool
        from Core.AgentSchema.tool_contracts import EntityAgentInputs
        from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool, subgraph_agent_path_tool
        from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs, SubgraphAgentPathInputs

        # Extract entities
        ea_params = EntityAgentInputs(
            query_text=q['question'], text_context=text_context,
            target_entity_types=["person", "film", "location"],
            max_entities_to_extract=6)
        ea_result = await entity_agent_tool(ea_params, context)
        extracted = [e.entity_name.lower() for e in ea_result.extracted_entities]
        print(f"  Extracted: {extracted}")

        # Match to graph
        graph_nodes = set(nx_g.nodes())
        matched = [n for n in graph_nodes if any(
            ext in n.lower() or n.lower() in ext for ext in extracted
        )]
        print(f"  Matched to graph: {matched[:6]}")

        # Find paths
        all_paths = []
        if len(matched) >= 2:
            for i in range(min(len(matched), 3)):
                for j in range(i+1, min(len(matched), 4)):
                    kh_params = SubgraphKHopPathsInputs(
                        graph_reference_id=GRAPH_ID,
                        start_entity_ids=[matched[i]],
                        end_entity_ids=[matched[j]],
                        k_hops=4, max_paths_to_return=3)
                    kh_result = await subgraph_khop_paths_tool(kh_params, context)
                    all_paths.extend(kh_result.discovered_paths)
        print(f"  Paths found: {len(all_paths)}")

        # Rank paths
        if all_paths:
            ap_params = SubgraphAgentPathInputs(
                user_question=q['question'],
                candidate_paths=all_paths[:8],
                max_paths_to_return=3)
            ap_result = await subgraph_agent_path_tool(ap_params, context)
            for p in ap_result.relevant_paths:
                path_str = ' -> '.join(s.label for s in p.segments if s.label)
                print(f"    * {path_str}")
            results['Pipeline:ToG'] = f'PASS ({len(extracted)} → {len(matched)} → {len(all_paths)} → {len(ap_result.relevant_paths)})'
        else:
            results['Pipeline:ToG'] = f'PARTIAL (extracted {len(extracted)}, matched {len(matched)}, 0 paths)'
    except Exception as e:
        results['Pipeline:ToG'] = f'FAIL: {e}'

    # ===== SUMMARY =====
    print(f"\n{'='*60}")
    print(f"HOTPOTQA TEST RESULTS ({DATASET})")
    print(f"{'='*60}")
    for op, st in results.items():
        marker = 'OK' if 'PASS' in st else '!!' if 'FAIL' in st else '~~'
        print(f'  [{marker}] {op}: {st}')
    n_pass = sum(1 for s in results.values() if 'PASS' in s)
    print(f'\n  {n_pass} PASS out of {len(results)} tests')
    print(f'  Graph: {len(all_nodes)} nodes, {len(all_edges)} edges')
    print(f'  Agent brain: {config.llm.model}')

asyncio.run(test())
