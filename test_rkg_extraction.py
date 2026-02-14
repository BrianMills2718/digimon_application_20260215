#!/usr/bin/env python3
"""Test RKG-level extraction: extract_two_step=False + enable_edge_keywords=True.

Verifies that delimiter-based extraction produces entities with types/descriptions
and relationships with keywords/descriptions.
"""
import asyncio
import sys
import os
import json

sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATASET = 'HotpotQAsmallest'

async def test():
    from Option.Config2 import Config
    from Core.Provider.LiteLLMProvider import LiteLLMProvider
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.Graph.ERGraph import ERGraph

    config = Config.from_yaml_file('Option/Config2.yaml')
    llm = LiteLLMProvider(config.llm)
    encoder = get_rag_embedding(config=config)
    chunk_factory = ChunkFactory(config)

    # Override graph config for RKG-level extraction
    config.graph.extract_two_step = False
    config.graph.enable_edge_keywords = True
    config.graph.enable_entity_description = True
    config.graph.enable_entity_type = True
    config.graph.enable_edge_description = True
    config.graph.enable_edge_name = True
    print(f"Config: extract_two_step={config.graph.extract_two_step}, "
          f"enable_edge_keywords={config.graph.enable_edge_keywords}, "
          f"enable_entity_type={config.graph.enable_entity_type}, "
          f"enable_entity_description={config.graph.enable_entity_description}, "
          f"enable_edge_description={config.graph.enable_edge_description}")

    # Load a subset of chunks (5 docs to keep LLM costs down)
    chunks = await chunk_factory.get_chunks_for_dataset(DATASET)
    subset = chunks[:5]
    print(f"Testing on {len(subset)} chunks out of {len(chunks)} total")

    # Build ERGraph with RKG settings
    er = ERGraph(config.graph, llm, encoder)

    # Build graph
    success = await er._build_graph(subset)
    print(f"\nBuild success: {success}")

    # Analyze results
    nx_g = er._graph.graph
    nodes = list(nx_g.nodes(data=True))
    edges = list(nx_g.edges(data=True))
    print(f"Nodes: {len(nodes)}, Edges: {len(edges)}")

    if not nodes:
        print("FAIL: No nodes extracted")
        return

    # Check entity attributes
    print(f"\n{'='*60}")
    print("ENTITY ATTRIBUTE COVERAGE")
    print(f"{'='*60}")
    has_type = sum(1 for _, d in nodes if d.get('entity_type', '').strip())
    has_desc = sum(1 for _, d in nodes if d.get('description', '').strip())
    has_source = sum(1 for _, d in nodes if d.get('source_id', '').strip())
    print(f"  entity_type:   {has_type}/{len(nodes)} ({100*has_type/len(nodes):.0f}%)")
    print(f"  description:   {has_desc}/{len(nodes)} ({100*has_desc/len(nodes):.0f}%)")
    print(f"  source_id:     {has_source}/{len(nodes)} ({100*has_source/len(nodes):.0f}%)")

    # Sample entities
    print(f"\nSample entities:")
    for name, data in nodes[:5]:
        print(f"  {name}: type={data.get('entity_type','')}, desc={str(data.get('description',''))[:80]}")

    # Check relationship attributes
    print(f"\n{'='*60}")
    print("RELATIONSHIP ATTRIBUTE COVERAGE")
    print(f"{'='*60}")
    has_desc_e = sum(1 for _, _, d in edges if d.get('description', '').strip())
    has_keywords = sum(1 for _, _, d in edges if d.get('keywords', '').strip())
    has_weight = sum(1 for _, _, d in edges if d.get('weight', 0) > 0)
    has_source_e = sum(1 for _, _, d in edges if d.get('source_id', '').strip())
    print(f"  description:   {has_desc_e}/{len(edges)} ({100*has_desc_e/len(edges):.0f}%)" if edges else "  No edges")
    print(f"  keywords:      {has_keywords}/{len(edges)} ({100*has_keywords/len(edges):.0f}%)" if edges else "")
    print(f"  weight:        {has_weight}/{len(edges)} ({100*has_weight/len(edges):.0f}%)" if edges else "")
    print(f"  source_id:     {has_source_e}/{len(edges)} ({100*has_source_e/len(edges):.0f}%)" if edges else "")

    # Sample relationships
    print(f"\nSample relationships:")
    for src, tgt, data in edges[:5]:
        kw = data.get('keywords', '')
        desc = str(data.get('description', ''))[:60]
        w = data.get('weight', 0)
        print(f"  {src} -> {tgt}: kw='{kw}', desc='{desc}', w={w}")

    # Verdict
    print(f"\n{'='*60}")
    print("VERDICT")
    print(f"{'='*60}")
    checks = {
        'Nodes > 0': len(nodes) > 0,
        'Edges > 0': len(edges) > 0,
        'Entity types > 50%': has_type / max(len(nodes), 1) > 0.5,
        'Entity descriptions > 50%': has_desc / max(len(nodes), 1) > 0.5,
        'Rel descriptions > 50%': has_desc_e / max(len(edges), 1) > 0.5 if edges else False,
        'Rel keywords > 50%': has_keywords / max(len(edges), 1) > 0.5 if edges else False,
        'Rel weights > 50%': has_weight / max(len(edges), 1) > 0.5 if edges else False,
    }
    for check, passed in checks.items():
        print(f"  [{'OK' if passed else 'FAIL'}] {check}")
    n_pass = sum(checks.values())
    print(f"\n  {n_pass}/{len(checks)} checks passed")

asyncio.run(test())
