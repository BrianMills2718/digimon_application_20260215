#!/usr/bin/env python3
"""Agent-driven benchmark: any LLM composes operators per question via MCP.

Supports three agent backends (selected by --model):
- Codex SDK: model="codex" or "codex/gpt-5" — Codex CLI spawns MCP servers
- Claude Agent SDK: model="claude-code" or "claude-code/opus" — Claude Code spawns MCP servers
- MCP agent loop: any litellm model (e.g. "gemini/gemini-3-flash-preview") —
  llm_client starts MCP servers and runs a tool-calling loop

Saves results incrementally (partial runs preserved on Ctrl+C).

Usage:
    python eval/run_agent_benchmark.py --dataset HotpotQAsmallest --num 10
    python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --model gemini/gemini-3-flash-preview
    python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --model codex --resume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from eval.benchmark import exact_match, token_f1
from eval.data_prep import load_questions
from llm_client import MCPAgentResult


# --- Tool call extraction (works with both Codex Turn and MCPAgentResult) ---

def extract_tool_calls(raw_response: object) -> list[dict]:
    """Extract tool call records from the raw_response, regardless of backend.

    Handles:
    - Codex SDK Turn: items contain McpToolCallItem objects
    - MCPAgentResult: tool_calls contain MCPToolCallRecord objects
    - Claude Agent SDK dict: tool calls are in result.tool_calls, not here
    """
    # Claude Agent SDK: raw_response is a dict with conversation_trace — tool calls
    # are already captured in result.tool_calls, so return empty here.
    if isinstance(raw_response, dict):
        return []

    from llm_client import MCPAgentResult

    if isinstance(raw_response, MCPAgentResult):
        return [
            {
                "server": r.server,
                "tool": r.tool,
                "has_result": r.result is not None,
                "has_error": r.error is not None,
                "error": r.error[:500] if r.error else None,
                "result_preview": r.result[:200] if r.result else None,
            }
            for r in raw_response.tool_calls
        ]

    # Codex SDK Turn path
    try:
        from openai_codex_sdk import McpToolCallItem
    except ImportError:
        return []

    calls = []
    items = getattr(raw_response, "items", None)
    if not items:
        return calls

    for item in items:
        if isinstance(item, McpToolCallItem):
            error_text = getattr(item, "error", None)
            result_text = getattr(item, "result", None)
            calls.append({
                "server": getattr(item, "server", ""),
                "tool": getattr(item, "tool", ""),
                "status": str(getattr(item, "status", "")),
                "has_result": result_text is not None,
                "has_error": error_text is not None,
                "error": str(error_text)[:500] if error_text else None,
                "result_preview": str(result_text)[:200] if result_text else None,
            })
    return calls


# --- Prompt ---

PROMPT_TEMPLATES = {
    "fixed": Path(__file__).parent.parent / "prompts" / "agent_benchmark.yaml",
    "adaptive": Path(__file__).parent.parent / "prompts" / "agent_benchmark_adaptive.yaml",
}


def build_messages(question: str, dataset_name: str, mode: str = "fixed") -> list[dict]:
    """Render the agent benchmark prompt from YAML template."""
    from llm_client import render_prompt
    template = PROMPT_TEMPLATES.get(mode, PROMPT_TEMPLATES["fixed"])
    return render_prompt(template, question=question, dataset_name=dataset_name)


# --- MCP server config ---

def _build_mcp_servers(benchmark_mode: int = 1, dataset_name: str = "") -> dict:
    """Build MCP server config with API keys forwarded from current env.

    Args:
        benchmark_mode: 0=all tools, 1=prune build/pipeline shortcuts (benchmark mode)
        dataset_name: Pre-load this dataset's graph+VDB on MCP server startup
    """
    import llm_client  # triggers auto-load of ~/.secrets/api_keys.env
    env = {}
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY",
                "DEEPSEEK_API_KEY", "HOME", "PATH"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    env["DIGIMON_BENCHMARK_MODE"] = str(benchmark_mode)
    if dataset_name:
        env["DIGIMON_PRELOAD_DATASET"] = dataset_name
    return {
        "digimon-kgrag": {
            "command": "/home/brian/miniconda3/envs/digimon/bin/python",
            "args": ["-u", str(Path(__file__).parent.parent / "digimon_mcp_stdio_server.py")],
            "env": env,
        },
    }

# Default — overridden in main() based on --mode
DIGIMON_MCP_SERVERS = _build_mcp_servers(1)


# --- Agent model detection ---

def _is_codex_model(model: str) -> bool:
    """Check if model routes through the Codex SDK."""
    lower = model.lower()
    return lower == "codex" or lower.startswith("codex/")


def _is_claude_code_model(model: str) -> bool:
    """Check if model routes through the Claude Agent SDK."""
    lower = model.lower()
    return lower == "claude-code" or lower.startswith("claude-code/")


def _is_agent_sdk_model(model: str) -> bool:
    """Check if model uses any agent SDK (codex or claude-code)."""
    return _is_codex_model(model) or _is_claude_code_model(model)


def _model_slug(model: str) -> str:
    """Convert model string to filesystem-safe slug. e.g. 'gemini/gemini-3-flash-preview' -> 'gemini-3-flash-preview'."""
    # Use last segment after /
    slug = model.rsplit("/", 1)[-1]
    # Replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    return slug or "unknown"


# --- Run agent ---

async def run_agent(
    question: str,
    dataset_name: str,
    timeout: int = 120,
    model: str = "codex",
    reasoning_effort: str = "high",
    max_turns: int = 20,
    mcp_session_pool: object = None,
    mode: str = "fixed",
) -> dict:
    """Run an agent on a single question via llm_client.

    For Codex models: uses Codex SDK with MCP servers.
    For other models: uses llm_client's MCP agent loop (litellm + tool calling).

    Args:
        mcp_session_pool: Optional MCPSessionPool for reusing MCP connections
            across questions (non-Codex models only).
        mode: Prompt mode ('fixed' or 'adaptive')

    Returns dict with: answer, tool_calls, usage, cost, latency_s, error
    """
    from llm_client import acall_llm

    project_root = str(Path(__file__).parent.parent)
    messages = build_messages(question, dataset_name, mode=mode)

    t0 = time.monotonic()
    try:
        if _is_codex_model(model):
            # Codex SDK path — agent-specific kwargs
            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                working_directory=project_root,
                approval_policy="never",
                sandbox_mode="workspace-write",
                model_reasoning_effort=reasoning_effort,
                mcp_servers=DIGIMON_MCP_SERVERS,
            )
        elif _is_claude_code_model(model):
            # Claude Agent SDK path
            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                cwd=project_root,
                permission_mode="bypassPermissions",
                max_turns=max_turns,
                mcp_servers=DIGIMON_MCP_SERVERS,
            )
        elif mcp_session_pool is not None:
            # MCP agent loop with persistent session pool
            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                mcp_sessions=mcp_session_pool,
                max_turns=max_turns,
            )
        else:
            # MCP agent loop — fresh server per call (legacy)
            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                mcp_servers=DIGIMON_MCP_SERVERS,
                max_turns=max_turns,
            )

        elapsed = time.monotonic() - t0

        # Try raw_response first (Codex/MCP), fall back to result.tool_calls (Claude SDK)
        tool_calls = extract_tool_calls(result.raw_response)
        if not tool_calls and result.tool_calls:
            tool_calls = [
                {
                    "tool": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", {}),
                    "result_preview": tc.get("result_preview", ""),
                    "has_result": bool(tc.get("result_preview")),
                    "has_error": tc.get("is_error", False),
                }
                for tc in result.tool_calls
            ]

        # Extract conversation trace if available
        conversation_trace = None
        if isinstance(result.raw_response, dict):
            conversation_trace = result.raw_response.get("conversation_trace")
        elif isinstance(result.raw_response, MCPAgentResult):
            conversation_trace = result.raw_response.conversation_trace or None

        # Extract answer from submit_answer tool call if present
        answer = None
        reasoning = None
        for tc in reversed(tool_calls):
            tool_name = tc.get("tool", "")
            if tool_name.endswith("submit_answer"):
                args = tc.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        pass
                if isinstance(args, dict):
                    answer = args.get("answer", "").strip()
                    reasoning = args.get("reasoning", "")
                break

        # Fallback: extract from text if no submit_answer call
        if not answer:
            answer = result.content.strip()
            if _is_agent_sdk_model(model) and "\n" in answer:
                lines = [l.strip() for l in answer.split("\n") if l.strip()]
                answer = lines[-1] if lines else answer

        return {
            "answer": answer,
            "reasoning": reasoning,
            "full_response": result.content.strip() if _is_agent_sdk_model(model) else None,
            "tool_calls": tool_calls,
            "conversation_trace": conversation_trace,
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
    parser = argparse.ArgumentParser(description="Agent-driven benchmark (any model via llm_client)")
    parser.add_argument("--dataset", required=True, help="Dataset name (e.g. HotpotQAsmallest)")
    parser.add_argument("--start", type=int, default=0, help="Start from question index (0-based)")
    parser.add_argument("--num", type=int, default=None, help="Number of questions to run")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per question in seconds")
    parser.add_argument("--resume", action="store_true", help="Resume from previous run")
    parser.add_argument("--model", default="codex", help="Agent model (default: codex). Any litellm model string works.")
    parser.add_argument("--effort", default="high", help="Reasoning effort (Codex only): minimal/low/medium/high")
    parser.add_argument("--max-turns", type=int, default=20, help="Max tool-calling loop iterations (non-Codex only)")
    parser.add_argument("--data-root", default="./Data", help="Data root directory")
    parser.add_argument("--mode", default="fixed", choices=["fixed", "adaptive"],
                        help="Prompt mode: 'fixed' (prescribed workflow) or 'adaptive' (agent composes freely)")
    parser.add_argument("--questions", type=str, default=None,
                        help="Comma-separated question IDs to run (e.g. 'q1,q4,q7')")
    args = parser.parse_args()

    # Rebuild MCP servers with correct benchmark mode + dataset pre-loading
    global DIGIMON_MCP_SERVERS
    benchmark_mode = 1  # both fixed and adaptive hide build/pipeline tools
    DIGIMON_MCP_SERVERS = _build_mcp_servers(benchmark_mode, dataset_name=args.dataset)

    dataset_path = Path(args.data_root) / args.dataset
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found at {dataset_path}")
        sys.exit(1)

    all_questions = load_questions(str(dataset_path))
    if args.questions:
        qids = set(args.questions.split(","))
        questions = [q for q in all_questions if q["id"] in qids]
        print(f"Loaded {len(questions)} questions from {args.dataset} (ids={args.questions})")
    else:
        questions = all_questions[args.start:]
        if args.num is not None:
            questions = questions[:args.num]
        print(f"Loaded {len(questions)} questions from {args.dataset} (start={args.start}, num={args.num})")

    # Output files — include model slug + timestamp so runs never overwrite
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = _model_slug(args.model)
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{args.dataset}_{slug}_{run_ts}.json"
    log_path = output_dir / f"{args.dataset}_{slug}_{run_ts}.log"

    # Resume support — find most recent file for this dataset+model
    completed_ids: set[str] = set()
    results: list[dict] = []
    if args.resume:
        pattern = f"{args.dataset}_{slug}_*.json"
        prev_files = sorted(output_dir.glob(pattern))
        if prev_files:
            resume_path = prev_files[-1]  # most recent by timestamp
            with open(resume_path) as f:
                existing = json.load(f)
            results = existing.get("results", [])
            completed_ids = {r["id"] for r in results}
            # Reuse same output path instead of creating a new one
            output_path = resume_path
            log_path = resume_path.with_suffix(".log")
            print(f"Resuming from {resume_path}: {len(completed_ids)} questions done")

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
    if _is_codex_model(args.model):
        backend = "Codex SDK"
    elif _is_claude_code_model(args.model):
        backend = "Claude Agent SDK"
    else:
        backend = "MCP agent loop"
    print(f"Model: {args.model} ({backend}, timeout={args.timeout}s)")

    print(f"\n{'='*70}")
    print(f"AGENT BENCHMARK: {args.dataset} ({len(questions)} questions)")
    print(f"{'='*70}\n")

    # Use MCPSessionPool for non-agent-SDK models to avoid per-question server restarts
    use_session_pool = not _is_agent_sdk_model(args.model)
    if use_session_pool:
        from llm_client import MCPSessionPool
        pool_cm = MCPSessionPool(DIGIMON_MCP_SERVERS)
    else:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _noop():
            yield None
        pool_cm = _noop()

    try:
        async with pool_cm as session_pool:
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
                    max_turns=args.max_turns,
                    mcp_session_pool=session_pool,
                    mode=args.mode,
                )

                predicted = agent_result["answer"]
                reasoning = agent_result.get("reasoning")
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

                # Token counts
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                cached_tokens = usage.get("cached_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                fresh_tokens = input_tokens - cached_tokens

                # Timing breakdown (Claude Agent SDK provides these)
                duration_ms = usage.get("duration_ms", 0)
                duration_api_ms = usage.get("duration_api_ms", 0)
                num_turns = usage.get("num_turns", 0)
                overhead_ms = duration_ms - duration_api_ms if duration_ms and duration_api_ms else 0

                # Print results
                if error:
                    print(f"  ERROR: {error}")
                print(f"  Predicted: {predicted[:200]}")
                if reasoning:
                    print(f"  Reasoning: {reasoning[:300]}")
                print(f"  EM={em}  F1={f1:.2f}  ({elapsed:.1f}s, ${cost:.4f})")
                print(f"  Tools: {n_tools} calls {tool_names}")
                print(f"  Tokens: {fresh_tokens:,} fresh + {cache_read:,} cached = {input_tokens + cache_read:,} total in, {output_tokens:,} out")
                if duration_ms:
                    print(f"  Timing: {duration_api_ms/1000:.1f}s API + {overhead_ms/1000:.1f}s overhead = {duration_ms/1000:.1f}s ({num_turns} turns)")

                log_file.write(
                    f"  Predicted: {predicted}\n"
                )
                if reasoning:
                    log_file.write(f"  Reasoning: {reasoning}\n")
                log_file.write(
                    f"  EM={em}  F1={f1:.2f}  ({elapsed:.1f}s, ${cost:.4f})\n"
                    f"  Tools: {n_tools} calls {tool_names}\n"
                    f"  Tokens: {fresh_tokens} fresh + {cache_read} cached = {input_tokens + cache_read} total in, {output_tokens} out\n"
                )
                if duration_ms:
                    log_file.write(f"  Timing: {duration_api_ms/1000:.1f}s API + {overhead_ms/1000:.1f}s overhead = {duration_ms/1000:.1f}s ({num_turns} turns)\n")
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
                full_response = agent_result.get("full_response")
                result_record = {
                    "id": q_id,
                    "question": question,
                    "gold": gold,
                    "predicted": predicted,
                    "reasoning": reasoning,
                    "full_response": full_response,
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
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_create,
                    "duration_ms": duration_ms,
                    "duration_api_ms": duration_api_ms,
                    "overhead_ms": overhead_ms,
                    "num_turns": num_turns,
                    "error": error,
                    "conversation_trace": agent_result.get("conversation_trace"),
                }
                results.append(result_record)

                _save_results(output_path, args.dataset, args.model, len(questions),
                              n_done, total_em, total_f1, total_cost, results)

    except KeyboardInterrupt:
        print(f"\n\nInterrupted after {n_done} questions.")
    finally:
        log_file.close()

    # Final summary + experiment log
    if n_done > 0:
        avg_tools = sum(r["n_tool_calls"] for r in results) / n_done
        avg_latency = sum(r["latency_s"] for r in results) / n_done
        total_input = sum(r.get("input_tokens", 0) for r in results)
        total_output = sum(r.get("output_tokens", 0) for r in results)
        n_errors = sum(1 for r in results if r.get("error"))

        print(f"\n{'='*70}")
        print(f"FINAL: {n_done}/{len(questions)} questions")
        print(f"  EM:    {100*total_em/n_done:.1f}%")
        print(f"  F1:    {100*total_f1/n_done:.1f}%")
        print(f"  Cost:  ${total_cost:.2f}")
        print(f"  Tools: {avg_tools:.1f} calls/question avg")
        print(f"{'='*70}")
        print(f"Results saved to {output_path}")

        # Append to experiment log (tracked in git)
        experiment_log = Path(__file__).parent / "experiment_log.jsonl"
        entry = {
            "timestamp": run_ts,
            "dataset": args.dataset,
            "model": args.model,
            "backend": backend,
            "n_questions": len(questions),
            "n_completed": n_done,
            "n_errors": n_errors,
            "avg_em": round(100 * total_em / n_done, 1),
            "avg_f1": round(100 * total_f1 / n_done, 1),
            "total_cost": round(total_cost, 4),
            "avg_tool_calls": round(avg_tools, 1),
            "avg_latency_s": round(avg_latency, 1),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "mode": args.mode,
            "timeout": args.timeout,
            "max_turns": args.max_turns,
            "results_file": str(output_path),
        }
        with open(experiment_log, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        print(f"Experiment logged to {experiment_log}")


def _save_results(
    output_path: Path,
    dataset: str,
    model: str,
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
            "model": model,
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
