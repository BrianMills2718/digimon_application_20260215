#!/usr/bin/env python3
"""
E2E test for auto_compose — LLM-driven method selection.

Loads Fictional_Test graph + entity VDB, then tests auto_compose with
different query types to verify method selection and pipeline execution.

Usage:
    conda run -n digimon python tests/e2e/test_auto_compose.py
"""

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Ensure project root on path and cwd
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

DATASET = "Fictional_Test"
GRAPH_ID = f"{DATASET}_ERGraph"
VDB_ID = f"{DATASET}_entities"

# Different query types to test method selection
QUERIES = [
    ("What is crystal technology?", "factual"),
    ("What are the major themes across all civilizations?", "thematic"),
    ("How does the Zorathian Empire connect to crystal technology through trade routes?", "multi-hop"),
]

VALID_METHODS = {
    "basic_local", "basic_global", "lightrag", "fastgraphrag",
    "hipporag", "tog", "gr", "dalk", "kgp", "med",
}

results: list[tuple[str, bool, str, float]] = []


def record(step: str, passed: bool, detail: str = "", elapsed: float = 0.0):
    status = "PASS" if passed else "FAIL"
    results.append((step, passed, detail, elapsed))
    time_str = f" ({elapsed:.1f}s)" if elapsed > 0 else ""
    print(f"  [{status}] {step}{time_str}" + (f" -- {detail}" if detail else ""))


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


async def test_auto_compose(mcp_srv, query: str, query_type: str) -> None:
    """Run auto_compose for a single query and validate the result."""
    t0 = time.time()
    try:
        result_json = await mcp_srv.auto_compose(
            query=query,
            dataset_name=DATASET,
            auto_build=True,
            return_context_only=True,
        )
        elapsed = time.time() - t0
        result = json.loads(result_json)

        # Check for errors
        if "error" in result and "_composition" not in result:
            record(f"auto_compose ({query_type})", False, f"ERROR: {result['error']}", elapsed)
            return

        # Validate composition metadata
        comp = result.get("_composition")
        if comp is None:
            record(f"auto_compose ({query_type})", False, "Missing _composition metadata", elapsed)
            return

        method = comp.get("method_selected")
        reasoning = comp.get("reasoning", "")
        confidence = comp.get("confidence", 0.0)

        if method not in VALID_METHODS:
            record(f"auto_compose ({query_type})", False, f"Invalid method: {method}", elapsed)
            return

        # Validate pipeline output
        has_final = bool(result.get("final_output"))
        has_steps = bool(result.get("all_step_outputs"))

        detail = (
            f"method={method}, confidence={confidence:.2f}, "
            f"reasoning={reasoning[:80]}..."
        )
        record(f"auto_compose ({query_type})", has_final or has_steps, detail, elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        record(f"auto_compose ({query_type})", False, f"EXCEPTION: {e}", elapsed)
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("Auto-Compose E2E Tests -- Fictional_Test")
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

    # Run auto_compose with different query types
    print("\n--- Auto-Compose Method Selection ---")
    for query, query_type in QUERIES:
        print(f"\n  Query ({query_type}): {query}")
        await test_auto_compose(mcp_srv, query, query_type)

    # Summary
    print("\n" + "=" * 60)
    print("AUTO-COMPOSE SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, ok, _, _ in results if ok)
    total = len(results)

    for step, ok, detail, elapsed in results:
        status = "PASS" if ok else "FAIL"
        time_str = f" ({elapsed:.1f}s)" if elapsed > 0 else ""
        print(f"  [{status}] {step}{time_str}")
        if detail:
            print(f"          {detail}")

    print(f"\n{passed}/{total} passed")
    total_time = sum(e for _, _, _, e in results)
    print(f"Total execution time: {total_time:.1f}s")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
