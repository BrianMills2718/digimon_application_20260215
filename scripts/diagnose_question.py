#!/usr/bin/env python3
"""Diagnose a specific benchmark question from result JSON.

Shows the full trace: plan, tool calls with arguments and results,
final answer, and comparison to gold. Uses the observability data
we already have — no speculation.

Usage:
    python scripts/diagnose_question.py RESULT_FILE QUESTION_ID
    python scripts/diagnose_question.py results/MuSiQue_gpt-5-4-mini_consolidated_20260325T232727Z.json 2hop__13548_13529

    # Or use make:
    make diagnose FILE=results/latest.json QID=2hop__13548_13529
"""

import json
import sys
from pathlib import Path


def diagnose(result_file: str, question_id: str) -> None:
    """Print full diagnostic trace for a question."""
    with open(result_file) as f:
        data = json.load(f)

    # Find the question
    question = None
    for q in data.get("results", []):
        if q["id"] == question_id:
            question = q
            break

    if not question:
        print(f"Question '{question_id}' not found in {result_file}")
        print(f"Available IDs: {[q['id'] for q in data.get('results', [])]}")
        sys.exit(1)

    # Header
    print(f"{'='*80}")
    print(f"DIAGNOSIS: {question_id}")
    print(f"{'='*80}")
    print(f"Question: {question.get('question', '?')}")
    print(f"Gold:     {question.get('gold', '?')}")
    print(f"Predicted:{question.get('predicted', '?')}")
    print(f"EM: {question.get('em', '?')}  LLM-judge: {question.get('llm_em', '?')}")
    print(f"Tools used: {len(question.get('tool_calls', []))}")
    print()

    # Full tool trace
    print(f"{'='*80}")
    print("TOOL TRACE (chronological)")
    print(f"{'='*80}")
    tool_details = question.get("tool_details", [])
    for i, td in enumerate(tool_details):
        tool = td.get("tool", "?")
        args = td.get("arguments", {})
        has_result = td.get("has_result", False)
        has_error = td.get("has_error", False)
        error = td.get("error", "")
        result_preview = td.get("result_preview", "")
        latency = td.get("latency_s", "?")
        reasoning = td.get("tool_reasoning", "")

        status = "ERROR" if has_error else ("OK" if has_result else "???")
        print(f"\n--- Call {i+1}: {tool} [{status}] (latency={latency}s) ---")

        if reasoning:
            print(f"  Reasoning: {reasoning[:200]}")

        # Show key arguments (skip boilerplate like dataset_name)
        skip_args = {"dataset_name", "graph_reference_id", "vdb_reference_id",
                     "document_collection_id", "tool_reasoning"}
        interesting_args = {k: v for k, v in args.items()
                          if k not in skip_args and v not in ("", None, [], {})}
        if interesting_args:
            for k, v in interesting_args.items():
                v_str = str(v)[:200]
                print(f"  {k}: {v_str}")

        if has_error:
            print(f"  ERROR: {error[:300]}")
        elif result_preview:
            # Show result, truncated
            preview = result_preview[:500]
            print(f"  Result: {preview}")

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    # Tool usage counts
    from collections import Counter
    tool_counts = Counter(question.get("tool_calls", []))
    print(f"Tool counts: {dict(tool_counts.most_common())}")

    # Check for planning
    has_plan = "semantic_plan" in tool_counts
    has_todo = "todo_write" in tool_counts
    print(f"Planning: semantic_plan={'YES' if has_plan else 'NO'}, todo_write={'YES' if has_todo else 'NO'}")

    # Check for grounding
    has_chunks = "chunk_retrieve" in tool_counts
    print(f"Grounding: chunk_retrieve={'YES' if has_chunks else 'NO'} ({tool_counts.get('chunk_retrieve', 0)} calls)")

    # Verdict
    print()
    if question.get("llm_em", 0) == 1:
        print("VERDICT: PASS (LLM-judge correct)")
    else:
        print("VERDICT: FAIL")
        print(f"  Gold: {question.get('gold', '?')}")
        print(f"  Pred: {question.get('predicted', '?')}")
        # Try to identify failure type
        if not has_chunks:
            print("  Likely cause: No chunk_retrieve — answer not grounded in source text")
        elif not has_plan:
            print("  Likely cause: No semantic_plan — agent may have lost track of reasoning chain")
        else:
            print("  Likely cause: Answer synthesis error — evidence was retrieved but wrong answer extracted")
            print("  Check: Does any result_preview above contain the gold answer?")


def main():
    if len(sys.argv) < 3:
        # If no args, show latest result file and its question IDs
        import glob
        files = sorted(glob.glob("results/MuSiQue_gpt-5-4-mini_consolidated_*.json"))
        if files:
            latest = files[-1]
            with open(latest) as f:
                data = json.load(f)
            print(f"Latest: {latest}")
            print(f"Questions:")
            for q in data.get("results", []):
                status = "PASS" if q.get("llm_em", 0) == 1 else "FAIL"
                print(f"  {status} {q['id']}")
        else:
            print("No result files found")
        print(f"\nUsage: python {sys.argv[0]} RESULT_FILE QUESTION_ID")
        sys.exit(0)

    diagnose(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
