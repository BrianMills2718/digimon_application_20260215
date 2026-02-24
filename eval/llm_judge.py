#!/usr/bin/env python3
"""Post-hoc LLM-as-judge scoring for benchmark results.

Reads a benchmark results JSON, re-scores each question using an LLM judge,
and outputs updated metrics. Cheap model (deepseek) is fine for this.

Usage:
    python eval/llm_judge.py results/HotpotQA_200_gemini-3-flash-preview_*.json
    python eval/llm_judge.py results/*.json --model deepseek/deepseek-chat
"""
import argparse
import asyncio
import json
import sys
from hashlib import md5
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_client import acall_llm, render_prompt, strip_fences
from eval.benchmark import _parse_llm_judge_correct

PROMPT_TEMPLATE = str(Path(__file__).parent.parent / "prompts" / "llm_judge.yaml")


async def judge_one(question: str, gold: str, predicted: str, model: str) -> dict:
    """Judge a single QA pair. Returns {"correct": bool, "reason": str}."""
    if not predicted or not predicted.strip():
        return {"correct": False, "reason": "empty prediction"}

    messages = render_prompt(
        PROMPT_TEMPLATE,
        question=question,
        gold=gold,
        predicted=predicted,
    )
    q_hash = md5(question.encode()).hexdigest()[:8]
    trace_id = f"digimon.llm_judge.{q_hash}"
    result = await acall_llm(model, messages, timeout=0, num_retries=3, task="digimon.llm_judge", trace_id=trace_id, max_budget=0)
    try:
        parsed = json.loads(strip_fences(result.content))
        return {
            "correct": bool(parsed.get("correct", False)),
            "reason": parsed.get("reason", ""),
        }
    except (json.JSONDecodeError, AttributeError):
        # If LLM didn't return valid JSON, use shared robust parser.
        return {
            "correct": _parse_llm_judge_correct(result.content),
            "reason": f"parse fallback: {result.content[:100]}",
        }


async def judge_results(results_path: str, model: str, max_concurrent: int = 10) -> None:
    """Re-score all results in a benchmark JSON file."""
    with open(results_path) as f:
        data = json.load(f)

    results = data["results"]
    n = len(results)
    print(f"Judging {n} results from {Path(results_path).name}")
    print(f"Judge model: {model}")
    print(f"Original scores: EM={data['avg_em']:.1f}%, F1={data['avg_f1']:.1f}%")
    print()

    # Run judgments with concurrency control
    sem = asyncio.Semaphore(max_concurrent)

    async def judge_with_sem(r: dict) -> dict:
        async with sem:
            return await judge_one(r["question"], r["gold"], r["predicted"], model)

    judgments = await asyncio.gather(
        *[judge_with_sem(r) for r in results],
        return_exceptions=True,
    )

    # Process results
    n_correct = 0
    n_changed = 0
    for i, (r, j) in enumerate(zip(results, judgments)):
        if isinstance(j, Exception):
            print(f"  [{r['id']}] ERROR: {j}")
            r["llm_judge"] = {"correct": False, "reason": f"error: {j}"}
            continue

        r["llm_judge"] = j
        llm_correct = j["correct"]
        em_correct = bool(r["em"])

        if llm_correct:
            n_correct += 1

        if llm_correct != em_correct:
            n_changed += 1
            direction = "EM=0 → LLM=correct" if llm_correct else "EM=1 → LLM=incorrect"
            print(f"  [{r['id']}] {direction}")
            print(f"    Q: {r['question'][:80]}")
            print(f"    Gold: {r['gold']!r}  Predicted: {r['predicted']!r}")
            print(f"    Reason: {j['reason']}")
            print()

    llm_acc = 100 * n_correct / n if n else 0

    print(f"{'='*60}")
    print(f"RESULTS: {n} questions")
    print(f"  EM accuracy:        {data['avg_em']:.1f}%")
    print(f"  LLM judge accuracy: {llm_acc:.1f}%")
    print(f"  F1 (unchanged):     {data['avg_f1']:.1f}%")
    print(f"  Changed verdicts:   {n_changed}")
    print(f"{'='*60}")

    # Save updated results
    data["llm_judge_accuracy"] = llm_acc
    data["llm_judge_model"] = model
    data["llm_judge_changed"] = n_changed

    output_path = results_path.replace(".json", "_judged.json")
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nSaved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="LLM-as-judge scoring for benchmark results")
    parser.add_argument("results_file", help="Path to benchmark results JSON")
    parser.add_argument("--model", default="gemini/gemini-2.5-flash",
                        help="Model for judging (default: gemini/gemini-2.5-flash)")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Max concurrent judge calls")
    args = parser.parse_args()

    asyncio.run(judge_results(args.results_file, args.model, args.concurrency))


if __name__ == "__main__":
    main()
