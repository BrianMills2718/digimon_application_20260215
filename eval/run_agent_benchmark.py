#!/usr/bin/env python3
"""Agent-driven benchmark: Codex freely composes operators per question via MCP.

Uses llm_client's Codex SDK integration (not subprocess). The agent sees
digimon-kgrag MCP tools and autonomously composes operator chains.

Saves results incrementally (partial runs preserved on Ctrl+C).

Usage:
    python eval/run_agent_benchmark.py --dataset HotpotQAsmallest --n 10
    python eval/run_agent_benchmark.py --dataset HotpotQA --n 50 --resume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from eval.benchmark import exact_match, token_f1


# --- MCP tool call extraction from Codex SDK Turn ---

def extract_tool_calls(turn_raw: object) -> list[dict]:
    """Extract MCP tool calls from a Codex Turn's items.

    The Codex SDK exposes McpToolCallItem objects in Turn.items with:
      server, tool, arguments, result, error, status
    """
    from openai_codex_sdk import McpToolCallItem

    calls = []
    items = getattr(turn_raw, "items", None)
    if not items:
        return calls

    for item in items:
        if isinstance(item, McpToolCallItem):
            calls.append({
                "server": getattr(item, "server", ""),
                "tool": getattr(item, "tool", ""),
                "status": str(getattr(item, "status", "")),
                "has_result": getattr(item, "result", None) is not None,
                "has_error": getattr(item, "error", None) is not None,
            })
    return calls


# --- Prompt ---

SYSTEM_PROMPT = """\
You are a QA research assistant with access to knowledge graph search tools via MCP.
The tools let you search entities, traverse relationships, retrieve source text, and generate answers.
Use them to answer the question accurately and concisely."""


def build_prompt(question: str, dataset_name: str) -> str:
    """Build the user prompt for the agent."""
    return (
        f"Dataset: '{dataset_name}' (graph and indexes already built).\n\n"
        f"Question: {question}\n\n"
        f"Use the available MCP tools to search the knowledge graph, retrieve relevant "
        f"context, and answer the question. Start by searching for key entities from the "
        f"question, then follow relationships and retrieve source text.\n\n"
        f"Give your final answer as a concise phrase (a few words, not a full sentence)."
    )


# --- Main ---

def load_questions(dataset_path: str, n: int | None = None) -> list[dict]:
    qfile = Path(dataset_path) / "Question.json"
    if not qfile.exists():
        print(f"ERROR: {qfile} not found")
        sys.exit(1)
    questions = []
    with open(qfile) as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    if n:
        questions = questions[:n]
    return questions


async def run_agent(
    question: str,
    dataset_name: str,
    timeout: int = 120,
    model: str = "codex",
    reasoning_effort: str = "high",
) -> dict:
    """Run the Codex agent on a single question via llm_client.

    Returns dict with: answer, tool_calls, usage, cost, latency_s, error
    """
    from llm_client import acall_llm

    project_root = str(Path(__file__).parent.parent)
    prompt = build_prompt(question, dataset_name)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    t0 = time.monotonic()
    try:
        result = await acall_llm(
            model,
            messages,
            timeout=timeout,
            working_directory=project_root,
            approval_policy="never",
            sandbox_mode="workspace-write",
            model_reasoning_effort=reasoning_effort,
        )
        elapsed = time.monotonic() - t0

        # Extract MCP tool calls from the raw Turn object
        tool_calls = extract_tool_calls(result.raw_response)

        return {
            "answer": result.content.strip(),
            "tool_calls": tool_calls,
            "usage": result.usage,
            "cost": result.cost,
            "latency_s": round(elapsed, 2),
            "error": None if result.finish_reason != "error" else result.content,
        }

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        return {
            "answer": "",
            "tool_calls": [],
            "usage": {},
            "cost": 0.0,
            "latency_s": round(elapsed, 2),
            "error": f"TIMEOUT after {timeout}s",
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {
            "answer": "",
            "tool_calls": [],
            "usage": {},
            "cost": 0.0,
            "latency_s": round(elapsed, 2),
            "error": str(e),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Agent-driven benchmark (via llm_client Codex SDK)")
    parser.add_argument("--dataset", required=True, help="Dataset name (e.g. HotpotQAsmallest)")
    parser.add_argument("--n", type=int, default=None, help="Limit to first N questions")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per question in seconds")
    parser.add_argument("--resume", action="store_true", help="Resume from previous run")
    parser.add_argument("--model", default="codex", help="Agent model (default: codex)")
    parser.add_argument("--effort", default="high", help="Reasoning effort: minimal/low/medium/high")
    parser.add_argument("--data-root", default="./Data", help="Data root directory")
    args = parser.parse_args()

    dataset_path = Path(args.data_root) / args.dataset
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found at {dataset_path}")
        sys.exit(1)

    questions = load_questions(str(dataset_path), args.n)
    print(f"Loaded {len(questions)} questions from {args.dataset}")

    # Output files
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{args.dataset}_agent_benchmark.json"
    log_path = output_dir / f"{args.dataset}_agent_benchmark.log"

    # Resume support
    completed_ids: set[str] = set()
    results: list[dict] = []
    if args.resume and output_path.exists():
        with open(output_path) as f:
            existing = json.load(f)
        results = existing.get("results", [])
        completed_ids = {r["id"] for r in results}
        print(f"Resuming: {len(completed_ids)} questions already done")

    # Running totals
    total_em = 0
    total_f1 = 0.0
    total_cost = 0.0
    n_done = len(results)

    for r in results:
        total_em += r["em"]
        total_f1 += r["f1"]
        total_cost += r.get("cost", 0.0)

    log_file = open(log_path, "a")
    print(f"Log: {log_path}")
    print(f"JSON: {output_path}")
    print(f"Model: {args.model} (effort={args.effort}, timeout={args.timeout}s)")

    print(f"\n{'='*70}")
    print(f"AGENT BENCHMARK: {args.dataset} ({len(questions)} questions)")
    print(f"{'='*70}\n")

    try:
        for i, q in enumerate(questions):
            q_id = q.get("id", f"q{i}")
            if q_id in completed_ids:
                continue

            gold = q["answer"]
            question = q["question"]
            q_type = q.get("type", "?")

            header = f"--- [{q_id}] ({n_done+1}/{len(questions)}) [{q_type}] ---"
            print(f"\n{header}")
            print(f"Q: {question}")
            print(f"Gold: {gold}")
            log_file.write(f"\n{header}\nQ: {question}\nGold: {gold}\n")
            log_file.flush()

            # Run agent
            agent_result = await run_agent(
                question, args.dataset,
                timeout=args.timeout,
                model=args.model,
                reasoning_effort=args.effort,
            )

            predicted = agent_result["answer"]
            error = agent_result["error"]
            tool_calls = agent_result["tool_calls"]
            usage = agent_result["usage"]
            cost = agent_result["cost"]
            elapsed = agent_result["latency_s"]

            # Score
            em = int(exact_match(predicted, gold)) if predicted else 0
            f1, prec, recall = token_f1(predicted, gold) if predicted else (0.0, 0.0, 0.0)

            # Tool call summary
            tool_names = [tc["tool"] for tc in tool_calls]
            n_tools = len(tool_calls)

            # Token counts from SDK
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cached_tokens = usage.get("cached_input_tokens", 0)

            # Print results
            if error:
                print(f"  ERROR: {error}")
            print(f"  Predicted: {predicted[:200]}")
            print(f"  EM={em}  F1={f1:.2f}  ({elapsed:.1f}s, ${cost:.4f})")
            print(f"  Tools: {n_tools} calls {tool_names}")
            print(f"  Tokens: {input_tokens} in ({cached_tokens} cached) + {output_tokens} out")

            log_file.write(
                f"  Predicted: {predicted}\n"
                f"  EM={em}  F1={f1:.2f}  ({elapsed:.1f}s, ${cost:.4f})\n"
                f"  Tools: {n_tools} calls {tool_names}\n"
                f"  Tokens: {input_tokens} in + {output_tokens} out\n"
            )
            if error:
                log_file.write(f"  ERROR: {error}\n")

            # Update running totals
            n_done += 1
            total_em += em
            total_f1 += f1
            total_cost += cost

            running = f"  Running: EM={100*total_em/n_done:.1f}%  F1={100*total_f1/n_done:.1f}%  ${total_cost:.2f}  ({n_done} done)"
            print(running)
            log_file.write(running + "\n\n")
            log_file.flush()

            # Save incrementally
            result_record = {
                "id": q_id,
                "question": question,
                "gold": gold,
                "predicted": predicted,
                "type": q_type,
                "em": em,
                "f1": f1,
                "latency_s": elapsed,
                "cost": cost,
                "n_tool_calls": n_tools,
                "tool_calls": tool_names,
                "tool_details": tool_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_input_tokens": cached_tokens,
                "error": error,
            }
            results.append(result_record)

            _save_results(output_path, args.dataset, len(questions), n_done,
                          total_em, total_f1, total_cost, results)

    except KeyboardInterrupt:
        print(f"\n\nInterrupted after {n_done} questions.")
    finally:
        log_file.close()

    # Final summary
    if n_done > 0:
        avg_tools = sum(r["n_tool_calls"] for r in results) / n_done
        print(f"\n{'='*70}")
        print(f"FINAL: {n_done}/{len(questions)} questions")
        print(f"  EM:    {100*total_em/n_done:.1f}%")
        print(f"  F1:    {100*total_f1/n_done:.1f}%")
        print(f"  Cost:  ${total_cost:.2f}")
        print(f"  Tools: {avg_tools:.1f} calls/question avg")
        print(f"{'='*70}")
        print(f"Results saved to {output_path}")


def _save_results(
    output_path: Path,
    dataset: str,
    n_questions: int,
    n_done: int,
    total_em: int,
    total_f1: float,
    total_cost: float,
    results: list[dict],
) -> None:
    """Save results JSON incrementally."""
    avg_tools = sum(r["n_tool_calls"] for r in results) / len(results) if results else 0
    avg_latency = sum(r["latency_s"] for r in results) / len(results) if results else 0
    total_input = sum(r.get("input_tokens", 0) for r in results)
    total_output = sum(r.get("output_tokens", 0) for r in results)

    with open(output_path, "w") as f:
        json.dump({
            "dataset": dataset,
            "n_questions": n_questions,
            "n_completed": n_done,
            "avg_em": 100 * total_em / n_done if n_done else 0,
            "avg_f1": 100 * total_f1 / n_done if n_done else 0,
            "total_cost": round(total_cost, 4),
            "avg_tool_calls": round(avg_tools, 1),
            "avg_latency_s": round(avg_latency, 1),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "results": results,
        }, f, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
