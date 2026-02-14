#!/usr/bin/env python3
"""Test LLM-dependent operators on Fictional_Test (synthetic data).

Tests Entity.Agent, Relationship.Agent, and Subgraph.AgentPath using
GPT-4o-mini as the agent brain. Synthetic data ensures the LLM can't
draw from inherent training knowledge.
"""
import asyncio
import sys
import os

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

async def test():
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

    # Load graph
    build_inputs = BuildERGraphInputs(target_dataset_name='Fictional_Test', force_rebuild=False)
    build_result = await build_er_graph(build_inputs, config, llm, encoder, chunk_factory)
    gi = getattr(build_result, 'graph_instance', None)
    if gi:
        if hasattr(gi, '_graph') and hasattr(gi._graph, 'namespace'):
            gi._graph.namespace = chunk_factory.get_namespace('Fictional_Test')
        context.add_graph_instance(build_result.graph_id, gi)

    GRAPH_ID = build_result.graph_id
    nx_g = context.get_graph_instance(GRAPH_ID)._graph.graph

    # Load the fictional text for the LLM to work with
    with open('Data/Fictional_Test/zorathian_empire.txt') as f:
        fictional_text = f.read()

    results = {}

    # =============================================
    # TEST 1: Entity.Agent
    # Can GPT-4o-mini extract entities from fictional text?
    # =============================================
    print("=" * 60)
    print("TEST 1: Entity.Agent (LLM entity extraction)")
    print("=" * 60)
    try:
        from Core.AgentTools.entity_tools import entity_agent_tool
        from Core.AgentSchema.tool_contracts import EntityAgentInputs

        params = EntityAgentInputs(
            query_text="What was the Zorathian Empire and what technology did they use?",
            text_context=fictional_text,
            target_entity_types=["civilization", "technology", "location", "person"],
            max_entities_to_extract=8,
        )
        r = await entity_agent_tool(params, context)

        print(f"  Extracted {len(r.extracted_entities)} entities:")
        for e in r.extracted_entities:
            print(f"    - {e.entity_name} ({e.entity_type}): {e.description[:80]}...")

        # Validate: should find key fictional entities
        names = {e.entity_name.lower() for e in r.extracted_entities}
        expected_hits = 0
        for keyword in ['zorathian', 'aerophantis', 'levitite', 'xelandra', 'zorthak']:
            found = any(keyword in n for n in names)
            if found:
                expected_hits += 1
                print(f"    [+] Found expected entity matching '{keyword}'")
            else:
                print(f"    [-] Missing expected entity matching '{keyword}'")

        if len(r.extracted_entities) >= 3 and expected_hits >= 3:
            results['Entity.Agent'] = f'PASS ({len(r.extracted_entities)} entities, {expected_hits}/5 expected keywords)'
        else:
            results['Entity.Agent'] = f'WEAK ({len(r.extracted_entities)} entities, {expected_hits}/5 expected keywords)'
    except Exception as e:
        results['Entity.Agent'] = f'FAIL: {e}'
        import traceback; traceback.print_exc()

    # =============================================
    # TEST 2: Relationship.Agent
    # Can GPT-4o-mini extract relationships from fictional text?
    # =============================================
    print("\n" + "=" * 60)
    print("TEST 2: Relationship.Agent (LLM relationship extraction)")
    print("=" * 60)
    try:
        from Core.AgentTools.relationship_tools import relationship_agent_tool
        from Core.AgentSchema.tool_contracts import RelationshipAgentInputs, ExtractedEntityData

        # Provide known entities as context for relationship extraction
        context_entities = [
            ExtractedEntityData(entity_name="Zorathian Empire", source_id="test",
                              entity_type="civilization", description="A powerful crystal-based civilization"),
            ExtractedEntityData(entity_name="Aerophantis", source_id="test",
                              entity_type="city", description="The floating capital city"),
            ExtractedEntityData(entity_name="Levitite Stones", source_id="test",
                              entity_type="technology", description="Anti-gravity crystals"),
            ExtractedEntityData(entity_name="Shadowpeak Mountains", source_id="test",
                              entity_type="location", description="Mountains where levitite is mined"),
            ExtractedEntityData(entity_name="Emperor Zorthak", source_id="test",
                              entity_type="person", description="Founder of the empire"),
        ]

        params = RelationshipAgentInputs(
            query_text="How did the Zorathian Empire use crystal technology and what caused its decline?",
            text_context=fictional_text,
            context_entities=context_entities,
            max_relationships_to_extract=8,
        )
        r = await relationship_agent_tool(params, context)

        print(f"  Extracted {len(r.extracted_relationships)} relationships:")
        for rel in r.extracted_relationships:
            desc = getattr(rel, 'description', '') or ''
            rname = getattr(rel, 'relation_name', '') or getattr(rel, 'type', 'unknown')
            print(f"    - {rel.src_id} --[{rname}]--> {rel.tgt_id}")
            if desc:
                print(f"      {desc[:80]}")

        if len(r.extracted_relationships) >= 3:
            results['Relationship.Agent'] = f'PASS ({len(r.extracted_relationships)} relationships extracted)'
        else:
            results['Relationship.Agent'] = f'WEAK ({len(r.extracted_relationships)} relationships)'
    except Exception as e:
        results['Relationship.Agent'] = f'FAIL: {e}'
        import traceback; traceback.print_exc()

    # =============================================
    # TEST 3: Subgraph.AgentPath
    # Can GPT-4o-mini rank paths by relevance to a question?
    # =============================================
    print("\n" + "=" * 60)
    print("TEST 3: Subgraph.AgentPath (LLM path ranking)")
    print("=" * 60)
    try:
        from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool, subgraph_agent_path_tool
        from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs, SubgraphAgentPathInputs

        # First get some candidate paths from KHopPaths
        # Use entities we know are connected
        edges = list(nx_g.edges())
        # Find a good start with multiple neighbors
        start = max(nx_g.nodes(), key=lambda n: nx_g.degree(n))
        neighbors = list(nx_g.neighbors(start))
        # Find a 2-hop target
        end = None
        for n in neighbors:
            for n2 in nx_g.neighbors(n):
                if n2 != start and n2 not in neighbors:
                    end = n2
                    break
            if end:
                break
        if not end:
            end = neighbors[-1] if neighbors else edges[0][1]

        print(f"  Finding paths: {start} -> {end}")
        khop_params = SubgraphKHopPathsInputs(
            graph_reference_id=GRAPH_ID,
            start_entity_ids=[start],
            end_entity_ids=[end],
            k_hops=4, max_paths_to_return=6)
        khop_result = await subgraph_khop_paths_tool(khop_params, context)

        if not khop_result.discovered_paths:
            # Try with a direct neighbor
            end = neighbors[0]
            khop_params = SubgraphKHopPathsInputs(
                graph_reference_id=GRAPH_ID,
                start_entity_ids=[start],
                end_entity_ids=[end],
                k_hops=3, max_paths_to_return=6)
            khop_result = await subgraph_khop_paths_tool(khop_params, context)

        print(f"  Got {len(khop_result.discovered_paths)} candidate paths")
        for i, p in enumerate(khop_result.discovered_paths[:4]):
            path_str = ' -> '.join(s.label for s in p.segments if s.label)
            print(f"    Path {i+1} ({p.hop_count} hops): {path_str}")

        if khop_result.discovered_paths:
            # Now ask the LLM to rank them
            agent_params = SubgraphAgentPathInputs(
                user_question="What technology did the Zorathian Empire use and where did it come from?",
                candidate_paths=khop_result.discovered_paths,
                max_paths_to_return=3,
            )
            agent_result = await subgraph_agent_path_tool(agent_params, context)

            print(f"\n  LLM selected {len(agent_result.relevant_paths)} relevant paths:")
            for i, p in enumerate(agent_result.relevant_paths):
                path_str = ' -> '.join(s.label for s in p.segments if s.label)
                print(f"    Rank {i+1}: {path_str}")

            if len(agent_result.relevant_paths) > 0:
                results['Subgraph.AgentPath'] = f'PASS (ranked {len(agent_result.relevant_paths)}/{len(khop_result.discovered_paths)} paths)'
            else:
                results['Subgraph.AgentPath'] = 'WEAK (LLM returned no relevant paths)'
        else:
            results['Subgraph.AgentPath'] = 'SKIP (no candidate paths to rank)'
    except Exception as e:
        results['Subgraph.AgentPath'] = f'FAIL: {e}'
        import traceback; traceback.print_exc()

    # =============================================
    # FULL ToG PIPELINE: Entity.Agent → KHopPaths → AgentPath
    # =============================================
    print("\n" + "=" * 60)
    print("PIPELINE: ToG (Entity.Agent → KHopPaths → AgentPath)")
    print("=" * 60)
    try:
        from Core.AgentTools.entity_tools import entity_agent_tool
        from Core.AgentSchema.tool_contracts import EntityAgentInputs
        from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool, subgraph_agent_path_tool
        from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs, SubgraphAgentPathInputs

        question = "What happened to the floating cities when the Crystal Plague struck?"

        # Step 1: Extract entities from text using LLM
        print(f"  Q: {question}")
        ea_params = EntityAgentInputs(
            query_text=question,
            text_context=fictional_text,
            target_entity_types=["event", "location", "technology"],
            max_entities_to_extract=5,
        )
        ea_result = await entity_agent_tool(ea_params, context)
        extracted_names = [e.entity_name.lower() for e in ea_result.extracted_entities]
        print(f"  Step 1 (Entity.Agent): Extracted {extracted_names}")

        # Step 2: Match extracted entities to graph nodes
        graph_nodes = set(nx_g.nodes())
        matched = [n for n in graph_nodes if any(
            ext in n.lower() or n.lower() in ext for ext in extracted_names
        )]
        print(f"  Step 2 (Entity match): {matched[:5]}")

        # Step 3: Find paths between matched entities
        all_paths = []
        if len(matched) >= 2:
            for i in range(min(len(matched), 3)):
                for j in range(i+1, min(len(matched), 4)):
                    kh_params = SubgraphKHopPathsInputs(
                        graph_reference_id=GRAPH_ID,
                        start_entity_ids=[matched[i]],
                        end_entity_ids=[matched[j]],
                        k_hops=3, max_paths_to_return=3)
                    kh_result = await subgraph_khop_paths_tool(kh_params, context)
                    all_paths.extend(kh_result.discovered_paths)
            print(f"  Step 3 (KHopPaths): Found {len(all_paths)} paths")

        # Step 4: Rank paths by relevance using LLM
        if all_paths:
            ap_params = SubgraphAgentPathInputs(
                user_question=question,
                candidate_paths=all_paths[:10],
                max_paths_to_return=3,
            )
            ap_result = await subgraph_agent_path_tool(ap_params, context)
            print(f"  Step 4 (AgentPath): LLM selected {len(ap_result.relevant_paths)} relevant paths")
            for p in ap_result.relevant_paths:
                path_str = ' -> '.join(s.label for s in p.segments if s.label)
                print(f"    * {path_str}")
            results['Pipeline:ToG'] = f'PASS ({len(ea_result.extracted_entities)} entities → {len(matched)} matched → {len(all_paths)} paths → {len(ap_result.relevant_paths)} ranked)'
        elif matched:
            results['Pipeline:ToG'] = f'PARTIAL (entities extracted & matched but no paths between them)'
        else:
            results['Pipeline:ToG'] = f'WEAK (entities extracted but none matched graph nodes)'
    except Exception as e:
        results['Pipeline:ToG'] = f'FAIL: {e}'
        import traceback; traceback.print_exc()

    # =============================================
    # SUMMARY
    # =============================================
    print("\n" + "=" * 60)
    print("LLM OPERATOR TEST RESULTS")
    print("=" * 60)
    for op, st in results.items():
        marker = 'OK' if 'PASS' in st else '!!' if 'FAIL' in st else '~~'
        print(f'  [{marker}] {op}: {st}')
    n_pass = sum(1 for s in results.values() if 'PASS' in s)
    n_other = len(results) - n_pass
    print(f'\n  {n_pass} PASS, {n_other} other out of {len(results)} tests')
    print(f'\n  Agent brain: {config.llm.model}')

asyncio.run(test())
