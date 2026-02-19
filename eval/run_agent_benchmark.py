#!/usr/bin/env python3
"""Agent-driven benchmark: any LLM composes operators per question via MCP.

Supports four agent backends (selected by --model and --backend):
- Codex SDK: model="codex" or "codex/gpt-5" — Codex CLI spawns MCP servers
- Claude Agent SDK: model="claude-code" or "claude-code/opus" — Claude Code spawns MCP servers
- MCP agent loop: any litellm model (e.g. "gemini/gemini-3-flash-preview") —
  llm_client starts MCP servers and runs a tool-calling loop
- Direct Python tools: any litellm model + --backend direct — calls DIGIMON
  functions in-process via python_tools= (no subprocess, no stdio, no JSON-RPC)

Saves results incrementally (partial runs preserved on Ctrl+C).
Use --parallel N for concurrent question execution (N MCP server processes).

Usage:
    python eval/run_agent_benchmark.py --dataset HotpotQAsmallest --num 10
    python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --model gemini/gemini-3-flash-preview
    python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --model codex --resume
    python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --parallel 5
    python eval/run_agent_benchmark.py --dataset HotpotQA --num 50 --model gemini/gemini-3-flash --backend direct
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
from hashlib import md5
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from eval.benchmark import exact_match, llm_judge, token_f1
from eval.data_prep import load_questions
from llm_client import MCPAgentResult
from llm_client import start_run as llm_start_run, log_item as llm_log_item, finish_run as llm_finish_run


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
                "arguments": r.arguments,
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
    "aot": Path(__file__).parent.parent / "prompts" / "agent_benchmark_aot.yaml",
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
    # Propagate log level to MCP subprocess
    digimon_log_level = os.environ.get("DIGIMON_LOG_LEVEL", "")
    if digimon_log_level:
        env["DIGIMON_LOG_LEVEL"] = digimon_log_level
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


# --- Direct Python tools backend ---

# Populated by _init_direct_tools() — list of async callables
DIRECT_TOOLS: list = []


async def _init_direct_tools(dataset_name: str) -> list:
    """Import DIGIMON MCP server module and initialize in-process.

    Returns list of tool functions ready for python_tools= parameter.
    Must be called once before run_agent with backend="direct".
    """
    # Set benchmark mode env vars BEFORE importing the MCP server module
    os.environ["DIGIMON_BENCHMARK_MODE"] = "1"
    os.environ["LLM_CLIENT_STRICT_MODELS"] = "1"  # ban deprecated models
    if dataset_name:
        os.environ["DIGIMON_PRELOAD_DATASET"] = dataset_name

    import digimon_mcp_stdio_server as dms

    # Initialize DIGIMON context (loads config, graph, VDB)
    await dms._ensure_initialized()

    # Collect benchmark-relevant tool functions from the MCP server module.
    # These are the same functions registered with @mcp.tool() minus hidden ones.
    _BENCHMARK_TOOLS = [
        dms.entity_vdb_search,
        dms.entity_onehop,
        dms.entity_ppr,
        dms.entity_link,
        dms.entity_tfidf,
        dms.relationship_onehop,
        dms.relationship_score_aggregator,
        dms.relationship_vdb_search,
        dms.chunk_from_relationships,
        dms.chunk_occurrence,
        dms.chunk_get_text,
        dms.chunk_text_search,
        dms.chunk_vdb_search,
        dms.chunk_aggregator,
        dms.list_available_resources,
        dms.subgraph_khop_paths,
        dms.subgraph_steiner_tree,
        dms.meta_pcst_optimize,
    ]

    # submit_answer is conditionally defined in BENCHMARK_MODE.
    if hasattr(dms, "submit_answer"):
        _BENCHMARK_TOOLS.append(dms.submit_answer)
    else:
        async def submit_answer(reasoning: str, answer: str) -> str:
            """Submit your final answer. Call once with your best answer."""
            dms._reset_chunk_dedup()
            return json.dumps({"status": "submitted", "answer": answer})

        _BENCHMARK_TOOLS.append(submit_answer)

    # Dynamic filtering: only include tools whose prerequisites exist
    ctx = dms._state.get("context")
    if ctx:
        vdbs = ctx.list_vdbs() if hasattr(ctx, "list_vdbs") else []
        vdb_names = " ".join(vdbs)

        if "entities" not in vdb_names:
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "entity_vdb_search"]
        if "relationship" not in vdb_names:
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "relationship_vdb_search"]
        if "chunk" not in vdb_names:
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "chunk_vdb_search"]

        # chunk_aggregator needs sparse matrices
        e2r_path, r2c_path = dms._sparse_matrix_paths(dataset_name)
        if not (e2r_path.exists() and r2c_path.exists()):
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "chunk_aggregator"]

    tool_names = [t.__name__ for t in _BENCHMARK_TOOLS]
    print(f"Direct backend: {len(_BENCHMARK_TOOLS)} Python tools loaded: {tool_names}", file=sys.stderr)
    return _BENCHMARK_TOOLS


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
    backend: str = "mcp",
    python_tools: list | None = None,
    fallback_models: list[str] | None = None,
    num_retries: int = 2,
    trace_id: str = "",
) -> dict:
    """Run an agent on a single question via llm_client.

    For Codex models: uses Codex SDK with MCP servers.
    For other models: uses llm_client's MCP agent loop (litellm + tool calling).
    For backend="direct": calls Python functions in-process via python_tools=.

    Args:
        mcp_session_pool: Optional MCPSessionPool for reusing MCP connections
            across questions (non-Codex models only).
        mode: Prompt mode ('fixed' or 'adaptive')
        backend: 'mcp' (default) or 'direct' (in-process Python tools)
        python_tools: List of Python callables for direct backend
        trace_id: Trace ID for correlating LLM calls

    Returns dict with: answer, tool_calls, usage, cost, latency_s, error
    """
    from llm_client import acall_llm

    task = "digimon.benchmark"
    project_root = str(Path(__file__).parent.parent)
    messages = build_messages(question, dataset_name, mode=mode)

    t0 = time.monotonic()
    try:
        if backend == "direct" and python_tools:
            # Direct Python tool loop — no MCP subprocess
            # Reset chunk dedup between questions
            import digimon_mcp_stdio_server as dms
            dms._reset_chunk_dedup()

            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                python_tools=python_tools,
                max_turns=max_turns,
                num_retries=num_retries,
                task=task,
                trace_id=trace_id,
                max_budget=0,
                **({"fallback_models": fallback_models} if fallback_models else {}),
            )
        elif _is_codex_model(model):
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
                task=task,
                trace_id=trace_id,
                max_budget=0,
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
                task=task,
                trace_id=trace_id,
                max_budget=0,
            )
        elif mcp_session_pool is not None:
            # MCP agent loop with persistent session pool
            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                mcp_sessions=mcp_session_pool,
                max_turns=max_turns,
                num_retries=num_retries,
                task=task,
                trace_id=trace_id,
                max_budget=0,
                **({"fallback_models": fallback_models} if fallback_models else {}),
            )
        else:
            # MCP agent loop — fresh server per call (legacy)
            result = await acall_llm(
                model,
                messages,
                timeout=timeout,
                mcp_servers=DIGIMON_MCP_SERVERS,
                max_turns=max_turns,
                num_retries=num_retries,
                task=task,
                trace_id=trace_id,
                max_budget=0,
                **({"fallback_models": fallback_models} if fallback_models else {}),
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

        # Extract diagnostic warnings and models_used from result
        warnings = getattr(result, "warnings", []) or []
        models_used: list[str] = []
        if isinstance(result.raw_response, MCPAgentResult):
            models_used = sorted(result.raw_response.models_used)

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
            "warnings": warnings,
            "models_used": models_used,
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
    parser.add_argument("--max-turns", type=int, default=50, help="Max tool-calling loop iterations (non-Codex only)")
    parser.add_argument("--data-root", default="./Data", help="Data root directory")
    parser.add_argument("--mode", default="fixed", choices=["fixed", "adaptive", "aot"],
                        help="Prompt mode: 'fixed' (prescribed workflow) or 'adaptive' (agent composes freely)")
    parser.add_argument("--questions", type=str, default=None,
                        help="Comma-separated question IDs to run (e.g. 'q1,q4,q7')")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Number of concurrent questions (each gets its own MCP server). Default: 1 (sequential)")
    parser.add_argument("--backend", default="mcp", choices=["mcp", "direct"],
                        help="Tool backend: 'mcp' (subprocess, default) or 'direct' (in-process Python tools)")
    parser.add_argument("--judge-model", default="openrouter/deepseek/deepseek-chat",
                        help="LLM judge model for format-agnostic scoring (default: openrouter/deepseek/deepseek-chat). Set to 'none' to disable.")
    parser.add_argument("--fallback-models", default="gemini/gemini-2.5-flash",
                        help="Comma-separated fallback models if primary fails (default: gemini/gemini-2.5-flash). Set to 'none' to disable.")
    parser.add_argument("--num-retries", type=int, default=2,
                        help="Number of retries per LLM call with exponential backoff (default: 2). Set higher for flaky models.")
    parser.add_argument("--verbose", action="store_true",
                        help="Show full DIGIMON debug logs on stderr. Default: quiet (WARNING+ only on stderr, DEBUG in log file).")
    args = parser.parse_args()

    # Suppress DIGIMON internal logging on stderr unless --verbose
    if not args.verbose:
        os.environ["DIGIMON_LOG_LEVEL"] = "WARNING"

    # Rebuild MCP servers with correct benchmark mode + dataset pre-loading
    global DIGIMON_MCP_SERVERS, DIRECT_TOOLS
    benchmark_mode = 1  # both fixed and adaptive hide build/pipeline tools
    DIGIMON_MCP_SERVERS = _build_mcp_servers(benchmark_mode, dataset_name=args.dataset)

    # Validate backend choice
    if args.backend == "direct" and _is_agent_sdk_model(args.model):
        print("ERROR: --backend direct is only for litellm models (not agent SDKs like codex/claude-code)")
        sys.exit(1)

    # Initialize direct backend if requested
    if args.backend == "direct":
        DIRECT_TOOLS = await _init_direct_tools(args.dataset)

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
    mode_tag = f"_{args.mode}" if args.mode != "fixed" else ""
    output_path = output_dir / f"{args.dataset}_{slug}{mode_tag}_{run_ts}.json"
    log_path = output_dir / f"{args.dataset}_{slug}{mode_tag}_{run_ts}.log"

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
    judge_model = args.judge_model if args.judge_model.lower() != "none" else ""
    fallback_models = [m.strip() for m in args.fallback_models.split(",") if m.strip().lower() != "none"] or None
    total_llm_em: int | None = 0 if judge_model else None
    n_done = len(results)

    for r in results:
        total_em += r["em"]
        total_f1 += r["f1"]
        total_cost += r.get("cost", 0.0)
        if total_llm_em is not None and r.get("llm_em") is not None:
            total_llm_em += r["llm_em"]

    log_file = open(log_path, "a")
    print(f"Log: {log_path}")
    print(f"JSON: {output_path}")
    if args.backend == "direct":
        backend = "Direct Python tools"
    elif _is_codex_model(args.model):
        backend = "Codex SDK"
    elif _is_claude_code_model(args.model):
        backend = "Claude Agent SDK"
    else:
        backend = "MCP agent loop"
    print(f"Model: {args.model} ({backend}, timeout={args.timeout}s)")

    parallel = max(1, args.parallel)
    if parallel > 1 and _is_agent_sdk_model(args.model):
        print(f"WARNING: --parallel ignored for agent SDK models (each spawns its own servers)")
        parallel = 1

    print(f"\n{'='*70}")
    print(f"AGENT BENCHMARK: {args.dataset} ({len(questions)} questions, parallel={parallel})")
    print(f"{'='*70}\n")

    _wall_t0 = time.monotonic()

    # Register experiment run in llm_client observability
    _experiment_run_id = llm_start_run(
        dataset=args.dataset,
        model=args.model,
        config={
            "backend": args.backend, "mode": args.mode,
            "timeout": args.timeout, "max_turns": args.max_turns,
            "parallel": parallel, "judge_model": judge_model or None,
            "fallback_models": fallback_models,
            "num_retries": args.num_retries,
        },
        metrics_schema=["em", "f1", "llm_em"],
        project="Digimon_for_KG_application",
    )

    # --- Per-question processing (shared between sequential and parallel) ---

    # Lock protects running totals, results list, log_file, and incremental saves
    output_lock = asyncio.Lock()

    def _score_and_record(q: dict, agent_result: dict, llm_em_val: int | None = None) -> dict:
        """Score a question result and build the result record. Pure function."""
        q_id = q["id"]
        gold = q["answer"]
        question = q["question"]
        q_type = q.get("type", "?")

        predicted = agent_result["answer"]
        reasoning = agent_result.get("reasoning")
        error = agent_result["error"]
        tool_calls = agent_result["tool_calls"]
        usage = agent_result["usage"]
        cost = agent_result["cost"]
        elapsed = agent_result["latency_s"]

        em = int(exact_match(predicted, gold)) if predicted else 0
        f1, prec, recall = token_f1(predicted, gold) if predicted else (0.0, 0.0, 0.0)

        tool_names = [tc["tool"] for tc in tool_calls]
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cached_tokens = usage.get("cached_tokens", 0)
        cache_read = usage.get("cached_tokens", 0)  # same field, kept for output compat
        cache_create = usage.get("cache_creation_tokens", 0)
        duration_ms = usage.get("duration_ms", 0)
        duration_api_ms = usage.get("duration_api_ms", 0)
        num_turns = usage.get("num_turns", 0)

        return {
            "id": q_id,
            "question": question,
            "gold": gold,
            "predicted": predicted,
            "reasoning": reasoning,
            "full_response": agent_result.get("full_response"),
            "type": q_type,
            "em": em,
            "llm_em": llm_em_val,
            "f1": f1,
            "latency_s": elapsed,
            "cost": cost,
            "n_tool_calls": len(tool_calls),
            "tool_calls": tool_names,
            "tool_details": tool_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_create,
            "duration_ms": duration_ms,
            "duration_api_ms": duration_api_ms,
            "overhead_ms": duration_ms - duration_api_ms if duration_ms and duration_api_ms else 0,
            "num_turns": num_turns,
            "error": error,
            "warnings": agent_result.get("warnings", []),
            "models_used": agent_result.get("models_used", []),
            "conversation_trace": agent_result.get("conversation_trace"),
        }

    def _format_output(record: dict, n_done_now: int, n_total: int,
                       total_em_now: int, total_f1_now: float, total_cost_now: float,
                       total_llm_em_now: int | None = None) -> str:
        """Format a result record — verbose multi-line (for .log file)."""
        lines = []
        q_id = record["id"]
        q_type = record["type"]
        header = f"--- [{q_id}] ({n_done_now}/{n_total}) [{q_type}] ---"
        lines.append(f"\n{header}")
        lines.append(f"Q: {record['question']}")
        lines.append(f"Gold: {record['gold']}")
        if record.get("error"):
            lines.append(f"  ERROR: {record['error']}")
        lines.append(f"  Predicted: {record['predicted'][:200]}")
        if record.get("reasoning"):
            lines.append(f"  Reasoning: {record['reasoning'][:300]}")
        fresh = record["input_tokens"] - record["cached_input_tokens"]
        total_in = record["input_tokens"] + record["cache_read_input_tokens"]
        llm_em_str = f"  LLM_EM={record['llm_em']}" if record.get("llm_em") is not None else ""
        lines.append(f"  EM={record['em']}{llm_em_str}  F1={record['f1']:.2f}  ({record['latency_s']:.1f}s, ${record['cost']:.4f})")
        lines.append(f"  Tools: {record['n_tool_calls']} calls {record['tool_calls']}")
        lines.append(f"  Tokens: {fresh:,} fresh + {record['cache_read_input_tokens']:,} cached = {total_in:,} total in, {record['output_tokens']:,} out")
        if record["duration_ms"]:
            api_s = record["duration_api_ms"] / 1000
            oh_s = record["overhead_ms"] / 1000
            lines.append(f"  Timing: {api_s:.1f}s API + {oh_s:.1f}s overhead = {record['duration_ms']/1000:.1f}s ({record['num_turns']} turns)")
        if record.get("warnings"):
            for w in record["warnings"]:
                lines.append(f"  ⚠ {w}")
        if record.get("models_used") and len(record["models_used"]) > 1:
            lines.append(f"  Models: {', '.join(record['models_used'])}")
        llm_em_running = f"  LLM_EM={100*total_llm_em_now/n_done_now:.1f}%" if total_llm_em_now is not None else ""
        lines.append(f"  Running: EM={100*total_em_now/n_done_now:.1f}%{llm_em_running}  F1={100*total_f1_now/n_done_now:.1f}%  ${total_cost_now:.2f}  ({n_done_now} done)")
        return "\n".join(lines)

    def _format_compact(record: dict, n_done_now: int, n_total: int,
                        total_em_now: int, total_f1_now: float, total_cost_now: float,
                        total_llm_em_now: int | None = None) -> str:
        """Format a result record — compact one-liner for clean console output."""
        q_id = record["id"]
        em_icon = "+" if record["em"] else "-"
        llm_em_icon = ""
        if record.get("llm_em") is not None:
            llm_em_icon = "L" if record["llm_em"] else "l"
        err = " ERR" if record.get("error") else ""
        warn = " W" if record.get("warnings") else ""
        running_em = 100 * total_em_now / n_done_now
        running_llm = f" LLM={100*total_llm_em_now/n_done_now:.0f}%" if total_llm_em_now is not None else ""
        return (f"[{n_done_now:3d}/{n_total}] {q_id:5s} {em_icon}{llm_em_icon} "
                f"F1={record['f1']:.2f} {record['n_tool_calls']:2d}t {record['latency_s']:5.1f}s "
                f"${record['cost']:.4f}{err}{warn}  "
                f"| EM={running_em:.1f}%{running_llm} ${total_cost_now:.2f}")

    async def _process_question(q: dict, session_pool: object) -> dict:
        """Run agent on one question, then score + log under lock."""
        nonlocal n_done, total_em, total_f1, total_cost, total_llm_em

        q_id = q.get("id", "unknown")
        q_hash = md5(q["question"].encode()).hexdigest()[:8]
        trace_id = f"digimon.benchmark.{args.dataset}.{q_id}.{q_hash}"

        agent_result = await run_agent(
            q["question"], args.dataset,
            timeout=args.timeout,
            model=args.model,
            reasoning_effort=args.effort,
            max_turns=args.max_turns,
            mcp_session_pool=session_pool,
            mode=args.mode,
            backend=args.backend,
            python_tools=DIRECT_TOOLS if args.backend == "direct" else None,
            fallback_models=fallback_models,
            num_retries=args.num_retries,
            trace_id=trace_id,
        )

        # LLM judge (runs before lock — it's an independent LLM call)
        llm_em_val: int | None = None
        if judge_model and agent_result["answer"]:
            llm_em_val = int(await llm_judge(
                q["question"], agent_result["answer"], q["answer"],
                model=judge_model,
            ))

        record = _score_and_record(q, agent_result, llm_em_val=llm_em_val)

        # Log to centralized experiment tracking (thread-safe, never raises)
        llm_log_item(
            run_id=_experiment_run_id, item_id=record["id"],
            metrics={"em": record["em"], "f1": record["f1"], "llm_em": record.get("llm_em")},
            predicted=record["predicted"], gold=record["gold"],
            latency_s=record["latency_s"], cost=record["cost"],
            n_tool_calls=record["n_tool_calls"], error=record.get("error"),
            extra={
                "tool_calls": record["tool_calls"],
                "warnings": record.get("warnings"),
                "models_used": record.get("models_used"),
                "input_tokens": record.get("input_tokens"),
                "output_tokens": record.get("output_tokens"),
            },
        )

        # Acquire lock for shared state updates + output
        async with output_lock:
            n_done += 1
            total_em += record["em"]
            total_f1 += record["f1"]
            total_cost += record["cost"]
            if total_llm_em is not None and llm_em_val is not None:
                total_llm_em += llm_em_val

            verbose_output = _format_output(record, n_done, len(questions),
                                            total_em, total_f1, total_cost,
                                            total_llm_em)
            # Always write verbose to log file
            log_file.write(verbose_output + "\n\n")
            log_file.flush()

            # Console: compact by default, verbose with --verbose
            if args.verbose:
                print(verbose_output)
            else:
                print(_format_compact(record, n_done, len(questions),
                                      total_em, total_f1, total_cost,
                                      total_llm_em))

            results.append(record)
            _save_results(output_path, args.dataset, args.model, len(questions),
                          n_done, total_em, total_f1, total_cost, results)

        return record

    # --- Execution: sequential or parallel ---

    # Filter to pending questions (skip already completed on resume)
    pending = []
    for i, q in enumerate(questions):
        q_id = q.get("id", f"q{i}")
        if q_id not in completed_ids:
            pending.append(q)

    use_session_pool = not _is_agent_sdk_model(args.model) and args.backend != "direct"

    try:
        if args.backend == "direct":
            # --- Direct path: no MCP servers, no session pool ---
            for q in pending:
                await _process_question(q, None)
        elif parallel <= 1:
            # --- Sequential path (original behavior) ---
            if use_session_pool:
                from llm_client import MCPSessionPool
                pool_cm = MCPSessionPool(DIGIMON_MCP_SERVERS)
            else:
                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def _noop():
                    yield None
                pool_cm = _noop()

            async with pool_cm as session_pool:
                for q in pending:
                    await _process_question(q, session_pool)
        else:
            # --- Parallel path: N MCP server processes ---
            from llm_client import MCPSessionPool

            print(f"Starting {parallel} MCP server processes...")
            pools: list[MCPSessionPool] = [
                MCPSessionPool(DIGIMON_MCP_SERVERS) for _ in range(parallel)
            ]
            pool_queue: asyncio.Queue[MCPSessionPool] = asyncio.Queue()

            # Start all pools
            from contextlib import AsyncExitStack
            async with AsyncExitStack() as stack:
                for pool in pools:
                    session_pool = await stack.enter_async_context(pool)
                    pool_queue.put_nowait(session_pool)
                print(f"All {parallel} MCP servers ready.\n")

                async def _run_with_pool(q: dict) -> dict:
                    pool = await pool_queue.get()
                    try:
                        return await _process_question(q, pool)
                    finally:
                        pool_queue.put_nowait(pool)

                # Launch all questions concurrently, pool_queue limits concurrency
                gather_results = await asyncio.gather(
                    *[_run_with_pool(q) for q in pending],
                    return_exceptions=True,
                )
                # Log any unhandled exceptions from gather
                for i, gr in enumerate(gather_results):
                    if isinstance(gr, BaseException):
                        q_id = pending[i].get("id", f"q{i}")
                        print(f"\nERROR [{q_id}]: {gr}", file=sys.stderr)

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
        wall_time = time.monotonic() - _wall_t0
        print(f"FINAL: {n_done}/{len(questions)} questions (parallel={parallel})")
        print(f"  EM:    {100*total_em/n_done:.1f}%")
        if total_llm_em is not None:
            print(f"  LLM_EM:{100*total_llm_em/n_done:.1f}%  (judge: {judge_model})")
        print(f"  F1:    {100*total_f1/n_done:.1f}%")
        print(f"  Cost:  ${total_cost:.2f}")
        print(f"  Tools: {avg_tools:.1f} calls/question avg")
        print(f"  Wall:  {wall_time:.1f}s ({wall_time/n_done:.1f}s/q effective)")
        print(f"{'='*70}")
        print(f"Results saved to {output_path}")

        # Finalize centralized experiment log
        run_status = "completed" if n_done == len(questions) else "interrupted"
        llm_finish_run(
            run_id=_experiment_run_id,
            wall_time_s=wall_time,
            status=run_status,
        )
        print(f"Experiment logged to llm_client observability (run_id={_experiment_run_id})")

    # Close litellm's cached async HTTP clients and let pending logging coroutines
    # drain so asyncio.run() can tear down cleanly (no SSL transport errors).
    import litellm
    await litellm.close_litellm_async_clients()
    await asyncio.sleep(0.1)


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

    # Compute LLM EM if any results have it
    llm_em_vals = [r["llm_em"] for r in results if r.get("llm_em") is not None]
    avg_llm_em = 100 * sum(llm_em_vals) / len(llm_em_vals) if llm_em_vals else None

    with open(output_path, "w") as f:
        json.dump({
            "dataset": dataset,
            "model": model,
            "n_questions": n_questions,
            "n_completed": n_done,
            "avg_em": 100 * total_em / n_done if n_done else 0,
            "avg_llm_em": avg_llm_em,
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
