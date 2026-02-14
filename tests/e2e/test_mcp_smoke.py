#!/usr/bin/env python3
"""
End-to-end smoke test for DIGIMON MCP server.

Calls MCP tool functions directly via Python imports (not MCP protocol)
against the pre-built Fictional_Test dataset. Tests operator composition
as an agent would do it.

Usage:
    conda run -n digimon python tests/e2e/test_mcp_smoke.py
"""

import asyncio
import json
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

# Track results
results: list[tuple[str, bool, str]] = []


def record(step: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((step, passed, detail))
    print(f"  [{status}] {step}" + (f" -- {detail}" if detail else ""))


async def main():
    print("=" * 60)
    print("DIGIMON MCP Smoke Test -- Fictional_Test")
    print("=" * 60)

    # ================================================================
    # A. SETUP -- initialize DIGIMON, load Fictional_Test graph
    # ================================================================
    print("\n--- A. Setup ---")

    import digimon_mcp_stdio_server as mcp_srv

    await mcp_srv._ensure_initialized()
    record(
        "A1: _ensure_initialized()",
        "initialized" in mcp_srv._state,
        f"keys: {list(mcp_srv._state.keys())}",
    )

    # Load the Fictional_Test graph into context
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

    graph_ok = GRAPH_ID in context.list_graphs()
    record(
        "A2: Load Fictional_Test graph",
        graph_ok,
        f"graph_id={GRAPH_ID}, status={build_result.status}",
    )

    # Build VDB if not present
    from Core.AgentTools.entity_vdb_tools import entity_vdb_build_tool
    from Core.AgentSchema.tool_contracts import EntityVDBBuildInputs

    vdb_inputs = EntityVDBBuildInputs(
        graph_reference_id=GRAPH_ID,
        vdb_collection_name=VDB_ID,
        force_rebuild=False,
    )
    vdb_result = await entity_vdb_build_tool(vdb_inputs, context)
    vdb_ok = vdb_result.num_entities_indexed > 0
    record(
        "A3: Build/load entity VDB",
        vdb_ok,
        f"entities_indexed={vdb_result.num_entities_indexed}",
    )

    # ================================================================
    # B. DISCOVERY TOOLS
    # ================================================================
    print("\n--- B. Discovery Tools ---")

    # B1: list_available_resources
    resources_json = await mcp_srv.list_available_resources()
    resources = json.loads(resources_json)
    has_graphs = len(resources.get("graphs", [])) > 0
    has_vdbs = len(resources.get("vdbs", [])) > 0
    record(
        "B1: list_available_resources()",
        has_graphs and has_vdbs,
        f"graphs={resources.get('graphs')}, vdbs={resources.get('vdbs')}",
    )

    # B2: list_methods
    methods_json = await mcp_srv.list_methods()
    methods = json.loads(methods_json)
    record(
        "B2: list_methods()",
        len(methods) == 10,
        f"count={len(methods)}, names={[m['name'] for m in methods]}",
    )

    # B3: list_graph_types
    types_json = await mcp_srv.list_graph_types()
    types_list = json.loads(types_json)
    record(
        "B3: list_graph_types()",
        len(types_list) == 5,
        f"count={len(types_list)}, names={[t['name'] for t in types_list]}",
    )

    # ================================================================
    # C. OPERATOR COMPOSITION CHAIN 1 -- basic local pattern
    # ================================================================
    print("\n--- C. Operator Composition Chain 1 (basic local) ---")

    # C1: entity_vdb_search
    search_json = await mcp_srv.entity_vdb_search(
        VDB_ID, "Zorathian Empire", top_k=5
    )
    search_result = json.loads(search_json)
    # EntityVDBSearchOutputs has similar_entities: [{node_id, entity_name, score}]
    similar = search_result.get("similar_entities", [])
    entity_names = [e["entity_name"] for e in similar]
    record(
        "C1: entity_vdb_search('Zorathian Empire')",
        len(entity_names) > 0,
        f"found {len(entity_names)} entities: {entity_names[:3]}",
    )

    if entity_names:
        # C2: entity_onehop
        onehop_json = await mcp_srv.entity_onehop(entity_names[:3], GRAPH_ID)
        onehop_result = json.loads(onehop_json)
        total_neighbors = onehop_result.get("total_neighbors_found", 0)
        record(
            "C2: entity_onehop()",
            total_neighbors > 0,
            f"total_neighbors={total_neighbors}",
        )

        # C3: relationship_onehop
        rel_json = await mcp_srv.relationship_onehop(entity_names[:3], GRAPH_ID)
        rel_result = json.loads(rel_json)
        rels = rel_result.get("one_hop_relationships", [])
        record(
            "C3: relationship_onehop()",
            len(rels) > 0,
            f"relationships={len(rels)}",
        )

        # C4: chunk_get_text
        chunk_json = await mcp_srv.chunk_get_text(GRAPH_ID, entity_names[:3])
        chunk_result = json.loads(chunk_json)
        chunks = chunk_result.get("retrieved_chunks", [])
        record(
            "C4: chunk_get_text()",
            len(chunks) > 0,
            f"chunks={len(chunks)}",
        )
    else:
        for step in ["C2: entity_onehop()", "C3: relationship_onehop()", "C4: chunk_get_text()"]:
            record(step, False, "SKIPPED -- no entities from C1")

    # ================================================================
    # D. OPERATOR COMPOSITION CHAIN 2 -- meta operator path
    # ================================================================
    print("\n--- D. Operator Composition Chain 2 (meta operators) ---")

    # D1: meta_extract_entities
    extract_json = await mcp_srv.meta_extract_entities(
        "What is the connection between crystal technology and the Zorathian Empire?"
    )
    extract_result = json.loads(extract_json)
    extracted = extract_result.get("entities", [])
    extracted_names = [e["entity_name"] for e in extracted] if extracted else []
    record(
        "D1: meta_extract_entities()",
        len(extracted_names) > 0,
        f"extracted={extracted_names}",
    )

    if extracted_names:
        # D2: entity_link (low threshold for FAISS cosine scores)
        link_json = await mcp_srv.entity_link(
            extracted_names, VDB_ID, similarity_threshold=0.1
        )
        link_result = json.loads(link_json)
        linked_pairs = link_result.get("linked_entities_results", [])
        linked_ids = [
            p["linked_entity_id"]
            for p in linked_pairs
            if p.get("linked_entity_id") and p.get("link_status") == "linked"
        ]
        record(
            "D2: entity_link()",
            len(linked_ids) > 0,
            f"linked={len(linked_ids)} of {len(extracted_names)}",
        )

        # D3: entity_ppr -- use linked IDs or fall back to VDB search entities
        ppr_seeds = linked_ids[:3] if linked_ids else entity_names[:3]
        if ppr_seeds:
            ppr_json = await mcp_srv.entity_ppr(GRAPH_ID, ppr_seeds, top_k=10)
            ppr_result = json.loads(ppr_json)
            ranked = ppr_result.get("ranked_entities", [])
            record(
                "D3: entity_ppr()",
                len(ranked) > 0,
                f"ranked={len(ranked)} entities",
            )
        else:
            record("D3: entity_ppr()", False, "SKIPPED -- no seed entities")
    else:
        record("D2: entity_link()", False, "SKIPPED -- no entities extracted")
        record("D3: entity_ppr()", False, "SKIPPED -- no entities extracted")

    # ================================================================
    # E. ANSWER GENERATION
    # ================================================================
    print("\n--- E. Answer Generation ---")

    # Collect chunk text from chain C
    test_chunks = []
    if entity_names and chunks:
        for c in chunks[:3]:
            text = c.get("text_content", c.get("text", ""))
            if text:
                test_chunks.append(text[:500])

    if not test_chunks:
        test_chunks = [
            "The Zorathian Empire was known for its crystal technology, "
            "which powered their floating cities and advanced weapons."
        ]

    answer = await mcp_srv.meta_generate_answer(
        "What is crystal technology?", test_chunks
    )
    answer_ok = len(answer) > 10 and answer != "Failed to generate answer."
    record(
        "E1: meta_generate_answer()",
        answer_ok,
        f"answer_len={len(answer)}, preview={answer[:100]}...",
    )

    # ================================================================
    # F. NAMED METHOD (convenience shortcut)
    # ================================================================
    print("\n--- F. Named Method ---")

    try:
        method_json = await mcp_srv.execute_method(
            "basic_local", "What is crystal technology?", DATASET
        )
        method_result = json.loads(method_json)
        method_ok = (
            "final_output" in method_result or "all_step_outputs" in method_result
        )
        record(
            "F1: execute_method('basic_local')",
            method_ok,
            f"keys={list(method_result.keys())}",
        )
    except Exception as e:
        record(
            "F1: execute_method('basic_local')",
            False,
            f"ERROR: {e}",
        )
        traceback.print_exc()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    for step, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {step}")

    print(f"\n{passed}/{total} passed, {failed} failed")

    if failed == 0:
        print("\nAll smoke tests PASSED!")
    else:
        print(f"\n{failed} smoke test(s) FAILED")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
