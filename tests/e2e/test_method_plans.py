#!/usr/bin/env python3
"""
Method plan execution tests — run each of the 10 method plans via execute_method.

Tests are tiered by prerequisite complexity:
  Tier 1 (entity VDB only): basic_local, hipporag, med, dalk
  Tier 2 (relationship VDB): lightrag, gr
  Tier 3 (community structure): basic_global
  Tier 4 (sparse matrices): fastgraphrag
  Tier 5 (loops, most complex): tog, kgp

Usage:
    conda run -n digimon python tests/e2e/test_method_plans.py
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
QUERY = "What is the connection between crystal technology and the Zorathian Empire?"

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


async def run_method(mcp_srv, method_name: str, tier: str) -> None:
    """Run a single method plan and record results."""
    t0 = time.time()
    try:
        result_json = await mcp_srv.execute_method(
            method_name, QUERY, DATASET, return_context_only=True
        )
        elapsed = time.time() - t0
        result = json.loads(result_json)

        # Check for prerequisite error
        if "error" in result:
            error_msg = result["error"]
            missing = result.get("missing", [])
            if missing:
                record(
                    f"[{tier}] {method_name}",
                    False,
                    f"PREREQ: {'; '.join(missing)}",
                    elapsed,
                )
            else:
                record(f"[{tier}] {method_name}", False, f"ERROR: {error_msg}", elapsed)
            return

        # Success checks
        has_final = bool(result.get("final_output"))
        has_steps = bool(result.get("all_step_outputs"))

        if has_final:
            detail = f"final_output keys={list(result['final_output'].keys())}"
        elif has_steps:
            detail = f"steps completed={list(result['all_step_outputs'].keys())}"
        else:
            detail = f"result keys={list(result.keys())}"

        record(f"[{tier}] {method_name}", has_final or has_steps, detail, elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        record(f"[{tier}] {method_name}", False, f"EXCEPTION: {e}", elapsed)
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("Method Plan Execution Tests -- Fictional_Test")
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

    # ================================================================
    # TIER 1: Entity VDB only (no special prerequisites)
    # ================================================================
    print("\n--- Tier 1: Entity VDB methods ---")
    for method in ["basic_local", "med"]:
        await run_method(mcp_srv, method, "T1")

    # hipporag and dalk need LLM for meta.extract_entities
    for method in ["hipporag", "dalk"]:
        await run_method(mcp_srv, method, "T1-LLM")

    # ================================================================
    # TIER 2: Relationship VDB required
    # ================================================================
    print("\n--- Tier 2: Relationship VDB methods ---")
    for method in ["lightrag", "gr"]:
        await run_method(mcp_srv, method, "T2")

    # ================================================================
    # TIER 3: Community structure required
    # ================================================================
    print("\n--- Tier 3: Community methods ---")
    await run_method(mcp_srv, "basic_global", "T3")

    # ================================================================
    # TIER 4: Sparse matrices required
    # ================================================================
    print("\n--- Tier 4: Sparse matrix methods ---")
    await run_method(mcp_srv, "fastgraphrag", "T4")

    # ================================================================
    # TIER 5: Loop-based methods (most complex)
    # ================================================================
    print("\n--- Tier 5: Loop-based methods ---")
    for method in ["tog", "kgp"]:
        await run_method(mcp_srv, method, "T5")

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 60)
    print("METHOD PLAN SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, ok, _, _ in results if ok)
    prereq = sum(1 for _, ok, d, _ in results if not ok and "PREREQ" in d)
    failed = sum(1 for _, ok, d, _ in results if not ok and "PREREQ" not in d)
    total = len(results)

    for step, ok, detail, elapsed in results:
        if ok:
            status = "PASS"
        elif "PREREQ" in detail:
            status = "PREREQ"
        else:
            status = "FAIL"
        time_str = f" ({elapsed:.1f}s)" if elapsed > 0 else ""
        print(f"  [{status}] {step}{time_str}")

    print(f"\n{passed}/{total} passed, {prereq} missing prerequisites, {failed} failed")

    total_time = sum(e for _, _, _, e in results)
    print(f"Total execution time: {total_time:.1f}s")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
