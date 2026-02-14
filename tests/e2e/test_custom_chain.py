#!/usr/bin/env python3
"""
Test: Can we compose and execute an ARBITRARY operator chain that isn't one of the 10 named methods?

This is the acid test for true modularity. We build a novel 5-operator chain:
  meta.extract_entities → entity.link → entity.onehop → relationship.onehop → chunk.from_relation

This chain:
1. Extracts entities from the query using LLM (meta operator)
2. Links them to the knowledge graph (entity operator)
3. Expands to 1-hop entity neighbors (entity operator)
4. Gets relationships for those entities (relationship operator)
5. Gets text chunks from those relationships (chunk operator)

This is NOT one of the 10 named methods — it's a novel composition.

Usage:
    conda run -n digimon python tests/e2e/test_custom_chain.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

DATASET = "Fictional_Test"
GRAPH_ID = f"{DATASET}_ERGraph"
VDB_ID = f"{DATASET}_entities"
QUERY = "What is the connection between crystal technology and the Zorathian Empire?"


async def main():
    print("=" * 60)
    print("Custom Chain Test — Proving Operator Modularity")
    print("=" * 60)

    # --- Setup: same as test_method_plans.py ---
    print("\n--- Setup ---")
    import digimon_mcp_stdio_server as mcp_srv
    await mcp_srv._ensure_initialized()

    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs

    config = mcp_srv._state["config"]
    llm = mcp_srv._state["llm"]
    encoder = mcp_srv._state["encoder"]
    chunk_factory = mcp_srv._state["chunk_factory"]
    context = mcp_srv._state["context"]

    # Load graph
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
    print("  [OK] Graph and VDB loaded")

    # --- Build the custom chain as an ExecutionPlan ---
    print("\n--- Building custom chain ---")
    from Core.AgentSchema.plan import (
        ExecutionPlan, ExecutionStep, DynamicToolChainConfig,
        ToolCall, ToolInputSource,
    )

    # Step 1: Extract entities from query (meta operator)
    # Slot name must match operator descriptor: "query" not "query_text"
    step1 = ExecutionStep(
        step_id="extract",
        description="Extract entities from query using LLM",
        action=DynamicToolChainConfig(
            tools=[ToolCall(
                tool_id="meta.extract_entities",
                inputs={"query": "plan_inputs.user_query"},
                named_outputs={"entities": "ENTITY_SET"},
            )]
        ),
    )

    # Step 2: Link extracted entities to KG
    step2 = ExecutionStep(
        step_id="link",
        description="Link extracted entities to knowledge graph",
        action=DynamicToolChainConfig(
            tools=[ToolCall(
                tool_id="entity.link",
                inputs={"entities": ToolInputSource(from_step_id="extract", named_output_key="entities")},
                named_outputs={"entities": "ENTITY_SET"},
            )]
        ),
    )

    # Step 3: Expand to 1-hop entity neighbors
    step3 = ExecutionStep(
        step_id="expand",
        description="Get 1-hop entity neighbors",
        action=DynamicToolChainConfig(
            tools=[ToolCall(
                tool_id="entity.onehop",
                inputs={"entities": ToolInputSource(from_step_id="link", named_output_key="entities")},
                named_outputs={"entities": "ENTITY_SET"},
            )]
        ),
    )

    # Step 4: Get relationships for those entities
    step4 = ExecutionStep(
        step_id="rels",
        description="Get relationships for expanded entities",
        action=DynamicToolChainConfig(
            tools=[ToolCall(
                tool_id="relationship.onehop",
                inputs={"entities": ToolInputSource(from_step_id="expand", named_output_key="entities")},
                named_outputs={"relationships": "RELATIONSHIP_SET"},
            )]
        ),
    )

    # Step 5: Get chunks from relationships
    step5 = ExecutionStep(
        step_id="chunks",
        description="Get text chunks from relationships",
        action=DynamicToolChainConfig(
            tools=[ToolCall(
                tool_id="chunk.from_relation",
                inputs={"relationships": ToolInputSource(from_step_id="rels", named_output_key="relationships")},
                named_outputs={"chunks": "CHUNK_SET"},
            )]
        ),
    )

    plan = ExecutionPlan(
        plan_description="Custom chain: extract → link → onehop → rel.onehop → chunk.from_relation",
        target_dataset_name=DATASET,
        plan_inputs={"user_query": QUERY},
        steps=[step1, step2, step3, step4, step5],
    )

    print(f"  Plan: {len(plan.steps)} steps")
    for s in plan.steps:
        tool_ids = [t.tool_id for t in s.action.tools]
        print(f"    {s.step_id}: {' → '.join(tool_ids)}")

    # --- Validate the chain ---
    print("\n--- Validating chain ---")
    from Core.Composition.ChainValidator import ChainValidator
    from Core.Operators.registry import REGISTRY

    validator = ChainValidator(REGISTRY)
    issues = validator.validate(plan)
    if issues:
        print(f"  [WARN] Validation issues: {issues}")
    else:
        print("  [OK] Chain validates")

    # --- Execute the chain ---
    print("\n--- Executing custom chain ---")
    from Core.Composition.PipelineExecutor import PipelineExecutor

    # Build OperatorContext
    op_ctx = await mcp_srv._build_operator_context_for_dataset(DATASET)
    if op_ctx is None:
        print("  [FAIL] Could not build operator context")
        return False

    executor = PipelineExecutor(REGISTRY, op_ctx)
    t0 = time.time()
    try:
        result = await executor.execute(plan)
        elapsed = time.time() - t0
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [FAIL] Execution error ({elapsed:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return False

    # --- Analyze results ---
    print(f"\n--- Results ({elapsed:.1f}s) ---")

    # Check each step
    all_ok = True
    for step_id, step_output in result.items():
        if step_output is None:
            print(f"  {step_id}: None")
            all_ok = False
            continue

        if isinstance(step_output, dict):
            for key, val in step_output.items():
                if hasattr(val, 'data'):
                    data = val.data if hasattr(val, 'data') else val
                    count = len(data) if hasattr(data, '__len__') else "?"
                    print(f"  {step_id}.{key}: {type(val).__name__} with {count} items")
                else:
                    print(f"  {step_id}.{key}: {type(val).__name__}")
        else:
            print(f"  {step_id}: {type(step_output).__name__}")

    # Check final chunks
    final = result.get("chunks", {})
    chunks_slot = final.get("chunks") if isinstance(final, dict) else None
    if chunks_slot and hasattr(chunks_slot, 'data') and len(chunks_slot.data) > 0:
        print(f"\n  [PASS] Custom chain produced {len(chunks_slot.data)} chunks")
        # Show first chunk preview
        first = chunks_slot.data[0]
        text = getattr(first, 'content', str(first))[:200]
        print(f"  Preview: {text}...")
        return True
    else:
        print(f"\n  [FAIL] No chunks produced")
        # Show what we got for debugging
        print(f"  Raw final output: {final}")
        all_ok = False

    return all_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    print(f"\n{'=' * 60}")
    print(f"MODULARITY TEST: {'PASS — arbitrary chains work!' if success else 'FAIL'}")
    print(f"{'=' * 60}")
    sys.exit(0 if success else 1)
