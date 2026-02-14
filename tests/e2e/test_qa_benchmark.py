#!/usr/bin/env python3
"""
QA Benchmarking for DIGIMON operator pipeline.

Uses HotpotQAsmallest (10 questions with gold answers) to compare
retrieval approaches. LLM-judge scores each answer against gold.

Approaches tested:
  1. Named methods: basic_local, fastgraphrag, hipporag
  2. Custom compositions: VDB-only, VDB+PPR
  3. Baseline: raw LLM (no retrieval)

Usage:
    conda run -n digimon python tests/e2e/test_qa_benchmark.py
"""

import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root on path and cwd
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# llm_client for judge calls
sys.path.insert(0, "/home/brian/projects/llm_client")
from llm_client import acall_llm

DATASET = "HotpotQAsmallest"
GRAPH_ID = f"{DATASET}_ERGraph"
VDB_ID = f"{DATASET}_entities"
JUDGE_MODEL = "gemini/gemini-3-flash-preview"


# ================================================================
# Load questions
# ================================================================

def load_questions() -> list[dict]:
    """Load questions from HotpotQAsmallest/Question.json (JSONL)."""
    questions = []
    q_path = Path(PROJECT_ROOT) / "Data" / DATASET / "Question.json"
    with open(q_path) as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


# ================================================================
# LLM Judge
# ================================================================

JUDGE_PROMPT = """You are a QA evaluation judge. Compare a predicted answer to the gold (correct) answer.

Question: {question}
Gold answer: {gold}
Predicted answer: {predicted}

Score the predicted answer on a 0-3 scale:
  0 = Wrong or completely irrelevant
  1 = Partially relevant but incorrect
  2 = Mostly correct with minor errors or missing detail
  3 = Fully correct

Respond with ONLY a single digit (0, 1, 2, or 3)."""


async def judge_answer(question: str, gold: str, predicted: str) -> int:
    """Score a predicted answer against gold using LLM judge."""
    if not predicted or predicted.strip() == "" or predicted == "Failed to generate answer.":
        return 0

    prompt = JUDGE_PROMPT.format(
        question=question, gold=gold, predicted=predicted
    )
    try:
        result = await acall_llm(
            JUDGE_MODEL,
            [{"role": "user", "content": prompt}],
            temperature=0,
            num_retries=1,
        )
        score_text = result.content.strip()
        score = int(score_text[0]) if score_text and score_text[0].isdigit() else 0
        return min(score, 3)
    except Exception as e:
        print(f"    Judge error: {e}")
        return 0


# ================================================================
# Retrieval approaches
# ================================================================

async def approach_named_method(
    mcp_srv: Any, method_name: str, question: str
) -> str:
    """Run a named method pipeline end-to-end."""
    try:
        result_json = await mcp_srv.execute_method(
            method_name, question, DATASET
        )
        result = json.loads(result_json)
        final = result.get("final_output", {})
        # Look for answer in final output
        answer = final.get("answer", "")
        if not answer:
            # Try to find any string value in final output
            for v in final.values():
                if isinstance(v, str) and len(v) > 10:
                    answer = v
                    break
        return str(answer)
    except Exception as e:
        return f"ERROR: {e}"


async def approach_vdb_only(mcp_srv: Any, question: str) -> str:
    """Minimal: VDB search -> chunk_get_text -> generate_answer."""
    try:
        # Step 1: VDB search
        search_json = await mcp_srv.entity_vdb_search(VDB_ID, question, top_k=5)
        search_result = json.loads(search_json)
        entities = [
            e["entity_name"]
            for e in search_result.get("similar_entities", [])
        ]
        if not entities:
            return ""

        # Step 2: Get chunks
        chunk_json = await mcp_srv.chunk_get_text(GRAPH_ID, entities[:5])
        chunk_result = json.loads(chunk_json)
        chunks = [
            c.get("text_content", "")
            for c in chunk_result.get("retrieved_chunks", [])
            if c.get("text_content")
        ]
        if not chunks:
            return ""

        # Step 3: Generate answer
        answer = await mcp_srv.meta_generate_answer(question, chunks[:5])
        return answer
    except Exception as e:
        return f"ERROR: {e}"


async def approach_vdb_ppr(mcp_srv: Any, question: str) -> str:
    """VDB search -> PPR expansion -> chunk_get_text -> generate_answer."""
    try:
        # Step 1: VDB search for seeds
        search_json = await mcp_srv.entity_vdb_search(VDB_ID, question, top_k=5)
        search_result = json.loads(search_json)
        entities = [
            e["entity_name"]
            for e in search_result.get("similar_entities", [])
        ]
        if not entities:
            return ""

        # Step 2: PPR expansion
        ppr_json = await mcp_srv.entity_ppr(GRAPH_ID, entities[:3], top_k=10)
        ppr_result = json.loads(ppr_json)
        ranked = ppr_result.get("ranked_entities", [])
        ppr_entities = [r[0] for r in ranked] if ranked else entities

        # Step 3: Get chunks for expanded entity set
        chunk_json = await mcp_srv.chunk_get_text(GRAPH_ID, ppr_entities[:8])
        chunk_result = json.loads(chunk_json)
        chunks = [
            c.get("text_content", "")
            for c in chunk_result.get("retrieved_chunks", [])
            if c.get("text_content")
        ]
        if not chunks:
            return ""

        # Step 4: Generate answer
        answer = await mcp_srv.meta_generate_answer(question, chunks[:5])
        return answer
    except Exception as e:
        return f"ERROR: {e}"


async def approach_baseline(question: str) -> str:
    """Raw LLM, no retrieval context."""
    try:
        result = await acall_llm(
            JUDGE_MODEL,
            [{"role": "user", "content": f"Answer concisely: {question}"}],
            temperature=0,
            num_retries=1,
        )
        return result.content.strip()
    except Exception as e:
        return f"ERROR: {e}"


# ================================================================
# Main
# ================================================================

async def main():
    print("=" * 70)
    print("DIGIMON QA Benchmark -- HotpotQAsmallest")
    print("=" * 70)

    questions = load_questions()
    print(f"Loaded {len(questions)} questions")

    # --- Initialize MCP server and load graph ---
    print("\nInitializing DIGIMON...")
    import digimon_mcp_stdio_server as mcp_srv

    await mcp_srv._ensure_initialized()

    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs
    from Core.AgentTools.entity_vdb_tools import entity_vdb_build_tool
    from Core.AgentSchema.tool_contracts import EntityVDBBuildInputs

    config = mcp_srv._state["config"]
    llm = mcp_srv._state["llm"]
    encoder = mcp_srv._state["encoder"]
    chunk_factory = mcp_srv._state["chunk_factory"]
    context = mcp_srv._state["context"]

    # Build or load graph
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

    if GRAPH_ID not in context.list_graphs():
        print(f"FATAL: Could not load graph {GRAPH_ID}")
        sys.exit(1)

    nx_g = context.get_graph_instance(GRAPH_ID)._graph.graph
    print(f"Graph loaded: {nx_g.number_of_nodes()} nodes, {nx_g.number_of_edges()} edges")

    # Build VDB
    vdb_inputs = EntityVDBBuildInputs(
        graph_reference_id=GRAPH_ID,
        vdb_collection_name=VDB_ID,
        force_rebuild=False,
    )
    vdb_result = await entity_vdb_build_tool(vdb_inputs, context)
    print(f"VDB: {vdb_result.num_entities_indexed} entities indexed")

    # --- Define approaches ---
    approaches = {
        "baseline": lambda q: approach_baseline(q),
        "vdb_only": lambda q: approach_vdb_only(mcp_srv, q),
        "vdb_ppr": lambda q: approach_vdb_ppr(mcp_srv, q),
        "basic_local": lambda q: approach_named_method(mcp_srv, "basic_local", q),
        "fastgraphrag": lambda q: approach_named_method(mcp_srv, "fastgraphrag", q),
        "hipporag": lambda q: approach_named_method(mcp_srv, "hipporag", q),
    }

    # --- Run benchmark ---
    print(f"\nRunning {len(approaches)} approaches x {len(questions)} questions...\n")

    # scores[approach][question_idx] = score
    scores: dict[str, list[int]] = {name: [] for name in approaches}
    answers: dict[str, list[str]] = {name: [] for name in approaches}

    for i, q in enumerate(questions):
        qtext = q["question"]
        gold = q["answer"]
        print(f"Q{i}: {qtext}")
        print(f"  Gold: {gold}")

        for approach_name, approach_fn in approaches.items():
            t0 = time.time()
            try:
                answer = await approach_fn(qtext)
            except Exception as e:
                answer = f"ERROR: {e}"
            elapsed = time.time() - t0

            score = await judge_answer(qtext, gold, answer)
            scores[approach_name].append(score)
            answers[approach_name].append(answer)

            preview = str(answer)[:80].replace("\n", " ")
            print(f"  {approach_name:15s}: score={score} ({elapsed:.1f}s) {preview}")
        print()

    # --- Summary table ---
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    header = f"{'Approach':15s}"
    for i in range(len(questions)):
        header += f"  Q{i}"
    header += "  Mean"
    print(header)
    print("-" * len(header))

    for name in approaches:
        row = f"{name:15s}"
        for s in scores[name]:
            row += f"  {s:2d}"
        mean = sum(scores[name]) / len(scores[name]) if scores[name] else 0
        row += f"  {mean:.2f}"
        print(row)

    # --- Write CSV ---
    csv_path = Path(PROJECT_ROOT) / "results" / DATASET / "benchmark_scores.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        q_headers = [f"Q{i}" for i in range(len(questions))]
        writer.writerow(["approach"] + q_headers + ["mean"])
        for name in approaches:
            mean = sum(scores[name]) / len(scores[name]) if scores[name] else 0
            writer.writerow([name] + scores[name] + [f"{mean:.2f}"])

    print(f"\nScores written to: {csv_path}")

    # --- Best approach ---
    means = {
        name: sum(s) / len(s) if s else 0
        for name, s in scores.items()
    }
    best = max(means, key=means.get)
    print(f"\nBest approach: {best} (mean={means[best]:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
