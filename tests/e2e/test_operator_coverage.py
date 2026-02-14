#!/usr/bin/env python3
"""
Operator coverage tests for the 9 previously-untested operators.

Tests call operator functions directly against the Fictional_Test dataset,
same pattern as test_mcp_smoke.py.

Usage:
    conda run -n digimon python tests/e2e/test_operator_coverage.py
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

# Ensure project root on path and cwd
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

DATASET = "Fictional_Test"
GRAPH_ID = f"{DATASET}_ERGraph"
VDB_ID = f"{DATASET}_entities"

results: list[tuple[str, bool, str]] = []


def record(step: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((step, passed, detail))
    print(f"  [{status}] {step}" + (f" -- {detail}" if detail else ""))


async def setup():
    """Initialize DIGIMON and load Fictional_Test graph + VDB."""
    import digimon_mcp_stdio_server as mcp_srv

    await mcp_srv._ensure_initialized()

    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs

    config = mcp_srv._state["config"]
    llm = mcp_srv._state["llm"]
    encoder = mcp_srv._state["encoder"]
    chunk_factory = mcp_srv._state["chunk_factory"]
    context = mcp_srv._state["context"]

    build_inputs = BuildERGraphInputs(
        target_dataset_name=DATASET, force_rebuild=False
    )
    build_result = await build_er_graph(
        build_inputs, config, llm, encoder, chunk_factory
    )
    gi = getattr(build_result, "graph_instance", None)
    if gi:
        if hasattr(gi, "_graph") and hasattr(gi._graph, "namespace"):
            gi._graph.namespace = chunk_factory.get_namespace(DATASET)
        context.add_graph_instance(GRAPH_ID, gi)

    # Build entity VDB
    from Core.AgentTools.entity_vdb_tools import entity_vdb_build_tool
    from Core.AgentSchema.tool_contracts import EntityVDBBuildInputs

    vdb_inputs = EntityVDBBuildInputs(
        graph_reference_id=GRAPH_ID,
        vdb_collection_name=VDB_ID,
        force_rebuild=False,
    )
    await entity_vdb_build_tool(vdb_inputs, context)

    return mcp_srv


async def _build_op_ctx(mcp_srv):
    """Build an OperatorContext for Fictional_Test."""
    return await mcp_srv._build_operator_context_for_dataset(DATASET)


async def main():
    print("=" * 60)
    print("Operator Coverage Tests -- Fictional_Test")
    print("=" * 60)

    # Setup
    print("\n--- Setup ---")
    try:
        mcp_srv = await setup()
        record("Setup: load graph + VDB", True)
    except Exception as e:
        record("Setup: load graph + VDB", False, str(e))
        traceback.print_exc()
        return False

    op_ctx = await _build_op_ctx(mcp_srv)

    from Core.Schema.SlotTypes import (
        EntityRecord, RelationshipRecord, SlotKind, SlotValue,
    )

    # ================================================================
    # NON-LLM OPERATORS (5)
    # ================================================================
    print("\n--- Non-LLM Operators ---")

    # 1. entity.rel_node — needs relationships as input
    print("\n  Testing entity.rel_node...")
    try:
        from Core.Operators.entity.rel_node import entity_rel_node

        # First get some relationships via onehop
        from Core.Operators.relationship.onehop import relationship_onehop

        # Get seed entities from VDB first
        from Core.Operators.entity.vdb import entity_vdb

        seed_result = await entity_vdb(
            inputs={"query": SlotValue(kind=SlotKind.QUERY_TEXT, data="Zorathian Empire", producer="test")},
            ctx=op_ctx,
        )
        seed_entities = seed_result["entities"]

        rel_result = await relationship_onehop(
            inputs={"entities": seed_entities},
            ctx=op_ctx,
        )
        test_rels = rel_result["relationships"]

        if test_rels.data:
            result = await entity_rel_node(
                inputs={"relationships": test_rels},
                ctx=op_ctx,
            )
            entities = result["entities"]
            ok = entities.kind == SlotKind.ENTITY_SET and len(entities.data) > 0
            record("entity.rel_node", ok, f"extracted {len(entities.data)} entities from {len(test_rels.data)} relationships")
        else:
            record("entity.rel_node", False, "SKIPPED -- no relationships from onehop")
    except Exception as e:
        record("entity.rel_node", False, f"ERROR: {e}")
        traceback.print_exc()

    # 2. relationship.vdb — needs relationship VDB
    print("\n  Testing relationship.vdb...")
    try:
        from Core.Operators.relationship.vdb import relationship_vdb

        if op_ctx.relations_vdb is not None:
            result = await relationship_vdb(
                inputs={"query": SlotValue(kind=SlotKind.QUERY_TEXT, data="crystal technology", producer="test")},
                ctx=op_ctx,
            )
            rels = result["relationships"]
            ok = rels.kind == SlotKind.RELATIONSHIP_SET
            record("relationship.vdb", ok, f"found {len(rels.data)} relationships")
        else:
            record("relationship.vdb", False, "SKIPPED -- no relationship VDB built")
    except Exception as e:
        record("relationship.vdb", False, f"ERROR: {e}")
        traceback.print_exc()

    # 3. chunk.from_relation — needs relationships with source_ids
    print("\n  Testing chunk.from_relation...")
    try:
        from Core.Operators.chunk.from_relation import chunk_from_relation

        # Use the relationships we got from entity.rel_node test
        if test_rels.data:
            result = await chunk_from_relation(
                inputs={"relationships": test_rels},
                ctx=op_ctx,
            )
            chunks = result["chunks"]
            ok = chunks.kind == SlotKind.CHUNK_SET
            record("chunk.from_relation", ok, f"found {len(chunks.data)} chunks")
        else:
            record("chunk.from_relation", False, "SKIPPED -- no relationships available")
    except Exception as e:
        record("chunk.from_relation", False, f"ERROR: {e}")
        traceback.print_exc()

    # 4. chunk.aggregator — needs sparse matrices
    print("\n  Testing chunk.aggregator...")
    try:
        from Core.Operators.chunk.aggregator import chunk_aggregator
        import numpy as np

        if op_ctx.sparse_matrices and "entity_to_rel" in op_ctx.sparse_matrices:
            # Create a dummy score vector with the right size
            n_entities = op_ctx.sparse_matrices["entity_to_rel"].shape[0]
            score_vec = np.random.rand(n_entities)

            result = await chunk_aggregator(
                inputs={"score_vector": SlotValue(kind=SlotKind.SCORE_VECTOR, data=score_vec, producer="test")},
                ctx=op_ctx,
            )
            chunks = result["chunks"]
            ok = chunks.kind == SlotKind.CHUNK_SET
            record("chunk.aggregator", ok, f"found {len(chunks.data)} chunks")
        else:
            record("chunk.aggregator", False, "SKIPPED -- no sparse matrices built (requires FastGraphRAG-style graph)")
    except Exception as e:
        record("chunk.aggregator", False, f"ERROR: {e}")
        traceback.print_exc()

    # 5. entity.tfidf — create entities with descriptions for TF-IDF ranking
    print("\n  Testing entity.tfidf...")
    try:
        from Core.Operators.entity.tfidf import entity_tfidf

        # Build candidate set with descriptions (VDB/graph descriptions may be empty)
        test_entities = SlotValue(
            kind=SlotKind.ENTITY_SET,
            data=[
                EntityRecord(entity_name="crystal technology", description="Advanced crystalline materials used for power generation and weapons"),
                EntityRecord(entity_name="zorathian empire", description="Ancient empire known for conquering through crystal-powered armies"),
                EntityRecord(entity_name="levitite crystals", description="Rare crystals found in the Shadowpeak Mountains"),
                EntityRecord(entity_name="the crystal plague", description="Devastating event where crystals became unstable and toxic"),
            ],
            producer="test",
        )

        result = await entity_tfidf(
            inputs={
                "query": SlotValue(kind=SlotKind.QUERY_TEXT, data="crystal technology weapons", producer="test"),
                "entities": test_entities,
            },
            ctx=op_ctx,
        )
        entities = result["entities"]
        ok = entities.kind == SlotKind.ENTITY_SET and len(entities.data) > 0
        record("entity.tfidf", ok, f"ranked {len(entities.data)} entities")
    except Exception as e:
        record("entity.tfidf", False, f"ERROR: {e}")
        traceback.print_exc()

    # ================================================================
    # LLM-DEPENDENT OPERATORS (4)
    # ================================================================
    print("\n--- LLM-Dependent Operators ---")

    if op_ctx.llm is None:
        print("  SKIPPING all LLM operators -- no LLM configured")
        for name in ["meta.reason_step", "meta.rerank", "meta.pcst_optimize", "relationship.agent"]:
            record(name, False, "SKIPPED -- no LLM")
    else:
        # 6. meta.reason_step
        print("\n  Testing meta.reason_step...")
        try:
            from Core.Operators.meta.reason_step import meta_reason_step

            # Get some chunks for context
            from Core.Operators.chunk.occurrence import chunk_occurrence

            chunk_result = await chunk_occurrence(
                inputs={"entities": seed_entities},
                ctx=op_ctx,
            )
            test_chunks = chunk_result["chunks"]

            result = await meta_reason_step(
                inputs={
                    "query": SlotValue(kind=SlotKind.QUERY_TEXT, data="What is the connection between crystal technology and the Zorathian Empire?", producer="test"),
                    "chunks": test_chunks,
                },
                ctx=op_ctx,
            )
            refined = result["query"]
            ok = refined.kind == SlotKind.QUERY_TEXT and len(refined.data) > 0
            record("meta.reason_step", ok, f"refined_len={len(refined.data)}, preview={refined.data[:80]}...")
        except Exception as e:
            record("meta.reason_step", False, f"ERROR: {e}")
            traceback.print_exc()

        # 7. meta.rerank
        print("\n  Testing meta.rerank...")
        try:
            from Core.Operators.meta.rerank import meta_rerank

            result = await meta_rerank(
                inputs={
                    "query": SlotValue(kind=SlotKind.QUERY_TEXT, data="crystal technology", producer="test"),
                    "items": seed_entities,
                },
                ctx=op_ctx,
                params={"top_k": 3},
            )
            reranked = result["items"]
            ok = reranked.kind == SlotKind.ENTITY_SET and len(reranked.data) > 0
            record("meta.rerank", ok, f"reranked to {len(reranked.data)} items")
        except Exception as e:
            record("meta.rerank", False, f"ERROR: {e}")
            traceback.print_exc()

        # 8. meta.pcst_optimize — needs entities + relationships
        print("\n  Testing meta.pcst_optimize...")
        try:
            from Core.Operators.meta.pcst_optimize import meta_pcst_optimize

            if test_rels.data:
                result = await meta_pcst_optimize(
                    inputs={
                        "entities": seed_entities,
                        "relationships": test_rels,
                    },
                    ctx=op_ctx,
                )
                subgraph = result["subgraph"]
                ok = subgraph.kind == SlotKind.SUBGRAPH and len(subgraph.data.nodes) > 0
                record("meta.pcst_optimize", ok, f"nodes={len(subgraph.data.nodes)}, edges={len(subgraph.data.edges)}")
            else:
                record("meta.pcst_optimize", False, "SKIPPED -- no relationships available")
        except Exception as e:
            record("meta.pcst_optimize", False, f"ERROR: {e}")
            traceback.print_exc()

        # 9. relationship.agent — needs LLM + graph
        print("\n  Testing relationship.agent...")
        try:
            from Core.Operators.relationship.agent import relationship_agent

            if seed_entities.data:
                result = await relationship_agent(
                    inputs={
                        "query": SlotValue(kind=SlotKind.QUERY_TEXT, data="What is crystal technology?", producer="test"),
                        "entities": seed_entities,
                    },
                    ctx=op_ctx,
                    params={"width": 3},
                )
                rels = result["relationships"]
                ok = rels.kind == SlotKind.RELATIONSHIP_SET
                record("relationship.agent", ok, f"found {len(rels.data)} relationships")
            else:
                record("relationship.agent", False, "SKIPPED -- no seed entities")
        except Exception as e:
            record("relationship.agent", False, f"ERROR: {e}")
            traceback.print_exc()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 60)
    print("OPERATOR COVERAGE SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, ok, _ in results if ok)
    skipped = sum(1 for _, ok, d in results if not ok and "SKIPPED" in d)
    failed = sum(1 for _, ok, d in results if not ok and "SKIPPED" not in d)
    total = len(results)

    for step, ok, detail in results:
        status = "PASS" if ok else ("SKIP" if "SKIPPED" in detail else "FAIL")
        print(f"  [{status}] {step}")

    print(f"\n{passed}/{total} passed, {skipped} skipped, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
