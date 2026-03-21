#!/usr/bin/env python3
"""Agent-driven benchmark: any LLM composes operators per question via MCP.

Supports four execution backends (selected by --model and --backend):
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
    python eval/run_agent_benchmark.py --dataset MuSiQue --questions-file results/locked_eval/locked_eval_ids.txt --mode baseline
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import random
import re
import sys
import time
import inspect
from datetime import datetime, timezone
from hashlib import md5, sha256
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from eval.benchmark import exact_match, llm_judge, token_f1
from eval.data_prep import load_question_ids_file, load_questions
from eval.graph_manifest import (
    filter_tool_names_by_graph_manifest,
    load_required_graph_manifest,
)
from llm_client import MCPAgentResult
from llm_client import (
    activate_feature_profile as llm_activate_feature_profile,
    activate_experiment_run as llm_activate_experiment_run,
    build_gate_signals,
    evaluate_gate_policy,
    finish_run as llm_finish_run,
    get_run_items as llm_get_run_items,
    load_gate_policy,
    log_item as llm_log_item,
    review_items_with_rubric,
    run_deterministic_checks_for_items,
    start_run as llm_start_run,
    triage_items,
)


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
                "tool_reasoning": getattr(r, "tool_reasoning", None),
                "arg_coercions": getattr(r, "arg_coercions", None) or [],
                "has_result": r.result is not None,
                "has_error": r.error is not None,
                "error": r.error[:500] if r.error else None,
                "result_preview": r.result[:500] if r.result else None,
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
                "result_preview": str(result_text)[:500] if result_text else None,
            })
    return calls


def _install_event_loop_exception_filter() -> None:
    """Suppress known benign asyncio SSL teardown noise at process shutdown."""
    loop = asyncio.get_running_loop()
    prior_handler = loop.get_exception_handler()

    def _handler(loop_: asyncio.AbstractEventLoop, context: dict) -> None:
        message = str(context.get("message") or "")
        exc = context.get("exception")
        exc_text = str(exc) if exc is not None else ""
        combined = f"{message} {exc_text}"
        is_benign_ssl_teardown = (
            ("SSL transport" in message or "socket transport" in message)
            and ("Event loop is closed" in combined or "Bad file descriptor" in combined)
        )
        if is_benign_ssl_teardown:
            return
        if prior_handler is not None:
            prior_handler(loop_, context)
        else:
            loop_.default_exception_handler(context)

    loop.set_exception_handler(_handler)


class _AsyncioTeardownNoiseFilter(logging.Filter):
    """Suppress known benign asyncio SSL teardown noise."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Fatal error on SSL transport" in msg:
            return False
        if "Fatal write error on socket transport" in msg:
            return False
        if "Event loop is closed" in msg and record.name.startswith("asyncio"):
            return False
        return True


def _install_asyncio_log_filter() -> None:
    logger = logging.getLogger("asyncio")
    logger.addFilter(_AsyncioTeardownNoiseFilter())


# --- Prompt ---

CANONICAL_MODE = "hybrid"
PROMPT_TEMPLATES = {
    "hybrid": Path(__file__).parent.parent / "prompts" / "agent_benchmark_hybrid.yaml",
    "codex_compact": Path(__file__).parent.parent / "prompts" / "agent_benchmark_codex_compact.yaml",
    "baseline": Path(__file__).parent.parent / "prompts" / "agent_benchmark_baseline.yaml",
    "fixed_graph": Path(__file__).parent.parent / "prompts" / "agent_benchmark_fixed_graph.yaml",
}
LEGACY_MODE_ALIASES = {
    "fixed": CANONICAL_MODE,
    "adaptive": CANONICAL_MODE,
    "aot": CANONICAL_MODE,
}

_DEFAULT_POST_GATE_POLICIES: dict[str, Path] = {
    "musique": Path(__file__).parent / "gate_policies" / "musique_default.json",
}


def _resolve_post_gate_policy(dataset_name: str, requested_policy: str) -> tuple[str, str]:
    """Resolve post-run gate policy from explicit arg or dataset defaults.

    Returns:
        (policy_spec, source) where source is one of:
        - "explicit": user passed --post-gate-policy
        - "dataset_default": auto-selected for known dataset
        - "none": no policy resolved
    """
    explicit = (requested_policy or "").strip()
    if explicit:
        return explicit, "explicit"

    dataset_key = (dataset_name or "").strip().lower()
    for prefix, path in _DEFAULT_POST_GATE_POLICIES.items():
        if dataset_key.startswith(prefix) and path.exists():
            return str(path), "dataset_default"
    return "", "none"

_BENCHMARK_TOOL_NAME_CANDIDATES = [
    "entity_vdb_search",
    "entity_onehop",
    "entity_ppr",
    "entity_link",
    "entity_resolve_names_to_ids",
    "entity_profile",
    "entity_select_candidate",
    "entity_tfidf",
    "relationship_onehop",
    "relationship_score_aggregator",
    "relationship_vdb_search",
    "chunk_from_relationships",
    "chunk_occurrence",
    "chunk_get_text_by_chunk_ids",
    "chunk_get_text_by_entity_ids",
    "extract_date_mentions",
    "extract_date_mentions_from_artifacts",
    "chunk_text_search",
    "chunk_vdb_search",
    "search_then_expand_onehop",
    "chunk_aggregator",
    "list_available_resources",
    "subgraph_khop_paths",
    "subgraph_steiner_tree",
    "meta_pcst_optimize",
    "semantic_plan",
    "todo_write",
    "bridge_disambiguate",
    "submit_answer",
]

_TOOL_MODE_BOUNDARIES: dict[str, str] = {
    "chunk_get_text_by_chunk_ids": "chunk_ids",
    "chunk_get_text_by_entity_ids": "entity_ids",
}

_BENCHMARK_INITIAL_ARTIFACTS: tuple[str, ...] = ("QUERY_TEXT",)

_BENCHMARK_TOOL_CONTRACTS: dict[str, dict[str, object]] = {
    "entity_vdb_search": {
        "requires_any": ["QUERY_TEXT", "ENTITY_SET", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_onehop": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_ppr": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_link": {
        "requires_any": ["QUERY_TEXT", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_resolve_names_to_ids": {
        "requires_any": ["QUERY_TEXT", "ENTITY_SET", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_profile": {
        "requires_any": ["QUERY_TEXT", {"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_select_candidate": {
        "requires_any": [
            {"kind": "ENTITY_SET", "ref_type": "candidate"},
            {"kind": "CHUNK_SET", "ref_type": "fulltext"},
            {"kind": "CHUNK_SET", "ref_type": "id"},
        ],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "entity_tfidf": {
        "requires_any": ["QUERY_TEXT", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    "relationship_onehop": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": ["RELATIONSHIP_SET"],
    },
    "relationship_score_aggregator": {
        "requires_any": ["ENTITY_SET", "RELATIONSHIP_SET"],
        "produces": ["RELATIONSHIP_SET"],
    },
    "relationship_vdb_search": {
        "requires_any": ["QUERY_TEXT", "ENTITY_SET", "CHUNK_SET"],
        "produces": ["RELATIONSHIP_SET"],
    },
    "chunk_from_relationships": {
        "requires_all": ["RELATIONSHIP_SET"],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "id"}],
    },
    "chunk_occurrence": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "id"}],
    },
    # Explicit wrappers only in benchmark mode (no multi-mode ambiguity).
    "chunk_get_text_by_chunk_ids": {
        "artifact_prereqs": "none",
        "mode": "chunk_ids",
        "requires_all": [{"kind": "CHUNK_SET", "ref_type": "id"}],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "fulltext"}],
    },
    "chunk_get_text_by_entity_ids": {
        "artifact_prereqs": "none",
        "mode": "entity_ids",
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "fulltext"}],
    },
    "extract_date_mentions": {
        "requires_any": [
            {"kind": "CHUNK_SET", "ref_type": "fulltext"},
            {"kind": "CHUNK_SET", "ref_type": "id"},
        ],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "fulltext"}],
    },
    "extract_date_mentions_from_artifacts": {
        "artifact_prereqs": "none",
        "handle_inputs": [
            {
                "arg": "chunk_artifact_ids",
                "inject_arg": "chunk_artifacts",
                "representation": "payload",
                "accepts": [{"kind": "CHUNK_SET", "ref_type": "fulltext"}],
            }
        ],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "fulltext"}],
    },
    "chunk_text_search": {
        "requires_all": ["QUERY_TEXT"],
        "produces": [
            {"kind": "CHUNK_SET", "ref_type": "id"},
            {"kind": "CHUNK_SET", "ref_type": "fulltext"},
            {"kind": "ENTITY_SET", "ref_type": "candidate"},
        ],
    },
    "chunk_vdb_search": {
        "requires_any": ["QUERY_TEXT", "ENTITY_SET", "CHUNK_SET"],
        "produces": [
            {"kind": "CHUNK_SET", "ref_type": "id"},
            {"kind": "CHUNK_SET", "ref_type": "fulltext"},
            {"kind": "ENTITY_SET", "ref_type": "candidate"},
        ],
    },
    "search_then_expand_onehop": {
        "requires_all": ["QUERY_TEXT"],
        "produces": [
            {"kind": "CHUNK_SET", "ref_type": "id"},
            {"kind": "CHUNK_SET", "ref_type": "fulltext"},
            {"kind": "ENTITY_SET", "ref_type": "candidate"},
            {"kind": "ENTITY_SET", "ref_type": "id"},
        ],
    },
    "chunk_aggregator": {
        "requires_any": ["ENTITY_SET", "RELATIONSHIP_SET"],
        "produces": [{"kind": "CHUNK_SET", "ref_type": "id"}],
    },
    "subgraph_khop_paths": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": ["SUBGRAPH"],
    },
    "subgraph_steiner_tree": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": ["SUBGRAPH"],
    },
    "meta_pcst_optimize": {
        "requires_any": ["ENTITY_SET", "RELATIONSHIP_SET"],
        "produces": ["SUBGRAPH"],
    },
    "bridge_disambiguate": {
        "requires_any": ["ENTITY_SET", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
    },
    # Control/planning tools intentionally bypass artifact requirements.
    "list_available_resources": {"is_control": True},
    "semantic_plan": {"is_control": True},
    "todo_write": {"is_control": True},
    "submit_answer": {"is_control": True},
}
_CONTROL_TOOL_NAMES: set[str] = {
    name
    for name, spec in _BENCHMARK_TOOL_CONTRACTS.items()
    if isinstance(spec, dict) and bool(spec.get("is_control"))
}


def _resolve_mode(mode: str) -> tuple[str, bool]:
    """Resolve legacy prompt modes to the canonical mode.

    Returns (effective_mode, was_aliased).
    """
    requested = (mode or CANONICAL_MODE).strip().lower()
    effective = LEGACY_MODE_ALIASES.get(requested, requested)
    if effective not in PROMPT_TEMPLATES:
        return CANONICAL_MODE, True
    return effective, requested != effective


def _is_disabled_token(value: str | None) -> bool:
    token = (value or "").strip().lower()
    return token in {"", "none", "off", "0", "false", "null"}


def _sha256_json(obj: object) -> str:
    payload = json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256(path.read_bytes()).hexdigest()


def _tool_surface() -> tuple[list[dict[str, str]], str]:
    """Return a stable tool surface manifest and hash for this run."""
    surface: list[dict[str, str]] = []
    if DIRECT_TOOLS:
        for tool in sorted(DIRECT_TOOLS, key=lambda fn: fn.__name__):
            try:
                signature = str(inspect.signature(tool))
            except (TypeError, ValueError):
                signature = "()"
            doc = inspect.getdoc(tool) or ""
            desc = doc.splitlines()[0].strip() if doc else ""
            surface.append({
                "name": tool.__name__,
                "signature": signature,
                "description": desc,
            })
    else:
        surface = [{"name": name} for name in sorted(_BENCHMARK_TOOL_NAME_CANDIDATES)]
    return surface, _sha256_json(surface)


def _build_run_provenance(
    *,
    dataset_path: Path,
    questions: list[dict],
    mode: str,
    prompt_variant: str = "default",
) -> dict[str, object]:
    effective_mode, _ = _resolve_mode(mode)
    variant = (prompt_variant or "default").strip().lower()
    template_key = "codex_compact" if variant == "codex_compact" else effective_mode
    template_path = PROMPT_TEMPLATES[template_key]
    tool_surface, tool_schema_sha = _tool_surface()
    dataset_projection = [
        {
            "id": q.get("id"),
            "question": q.get("question"),
            "answer": q.get("answer"),
        }
        for q in questions
    ]
    return {
        "dataset_path": str(dataset_path.resolve()),
        "dataset_hash_sha256": _sha256_json(dataset_projection),
        "dataset_question_count": len(questions),
        "prompt_variant": variant,
        "prompt_template_key": template_key,
        "prompt_template_path": str(template_path.resolve()),
        "prompt_template_sha256": _sha256_file(template_path),
        "tool_schema_sha256": tool_schema_sha,
        "tool_surface": tool_surface,
        "tool_contracts_sha256": _sha256_json(_BENCHMARK_TOOL_CONTRACTS),
        "tool_contracts": _BENCHMARK_TOOL_CONTRACTS,
        "tool_mode_boundaries_sha256": _sha256_json(_TOOL_MODE_BOUNDARIES),
        "tool_mode_boundaries": _TOOL_MODE_BOUNDARIES,
        "initial_artifacts": list(_BENCHMARK_INITIAL_ARTIFACTS),
        "enforce_tool_contracts": True,
    }


def build_messages(
    question: str,
    dataset_name: str,
    mode: str = CANONICAL_MODE,
    prompt_variant: str = "default",
) -> list[dict]:
    """Render the agent benchmark prompt from YAML template."""
    from llm_client import render_prompt
    variant = (prompt_variant or "default").strip().lower()
    if variant == "codex_compact":
        template = PROMPT_TEMPLATES["codex_compact"]
    else:
        effective_mode, _ = _resolve_mode(mode)
        template = PROMPT_TEMPLATES[effective_mode]
    return render_prompt(template, question=question, dataset_name=dataset_name)


def _extract_tool_error_text(tool_call: dict) -> str:
    """Extract best-effort tool error text from a normalized tool call record."""
    err = tool_call.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()

    preview = tool_call.get("result_preview")
    if isinstance(preview, str) and preview.strip():
        text = preview.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                payload = json.loads(text)
                nested_error = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(nested_error, str) and nested_error.strip():
                    return nested_error.strip()
            except Exception:
                pass

    if tool_call.get("has_error") or tool_call.get("is_error"):
        return "tool call marked as error"
    return ""


def _parse_tool_arguments(raw_arguments: object) -> dict[str, object] | None:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_tool_mode_trace(tool_calls: list[dict]) -> list[dict[str, object]]:
    mode_trace: list[dict[str, object]] = []
    for idx, tool_call in enumerate(tool_calls):
        tool_name = str(tool_call.get("tool", "")).strip()
        expected_mode = _TOOL_MODE_BOUNDARIES.get(tool_name)
        if not expected_mode:
            continue
        parsed_args = _parse_tool_arguments(tool_call.get("arguments"))
        declared_mode = ""
        if isinstance(parsed_args, dict):
            raw_mode = parsed_args.get("mode")
            if isinstance(raw_mode, str):
                declared_mode = raw_mode.strip().lower()
        mode_trace.append(
            {
                "turn_index": idx,
                "tool": tool_name,
                "expected_mode": expected_mode,
                "declared_mode": declared_mode or None,
                "mode_matches_expected": declared_mode == expected_mode if declared_mode else None,
                "arg_keys": sorted(parsed_args.keys()) if isinstance(parsed_args, dict) else [],
            }
        )
    return mode_trace


def _classify_tool_error(error_text: str) -> str:
    """Classify tool errors into coarse composability/runtime buckets."""
    msg = (error_text or "").lower()
    if not msg:
        return "tool_runtime_error"
    if "tool contract violation" in msg:
        return "contract_violation"
    if "unknown tool:" in msg:
        return "tool_unavailable"
    if "missing required argument: tool_reasoning" in msg:
        return "missing_tool_reasoning"
    if "suppressed:" in msg and ("submit_answer" in msg or "todo_write" in msg):
        return "control_loop_suppressed"
    if (
        "unexpected keyword argument" in msg
        or "required positional argument" in msg
        or "takes " in msg and " positional argument" in msg
        or "validation error" in msg
        or "validationerror" in msg
        or "pydantic" in msg
        or "input should" in msg
        or "typeerror" in msg
    ):
        return "tool_interface_mismatch"
    if (
        "requires one of" in msg
        or "requires all" in msg
        or "not built" in msg
        or "not found in context" in msg
        or "missing prerequisites" in msg
    ):
        return "missing_prerequisite"
    if "timeout" in msg:
        return "tool_timeout"
    return "tool_runtime_error"


def _classify_run_error(error_text: str) -> tuple[str | None, str | None, dict[str, int]]:
    """Classify top-level run failures for summary attribution."""
    msg = (error_text or "").lower()
    if not msg:
        return None, None, {}

    if (
        "insufficient credits" in msg
        or "\"code\":402" in msg
        or "openrouterexception" in msg and "402" in msg
    ):
        code = "PROVIDER_CREDITS_EXHAUSTED"
        return "provider", code, {code: 1}

    if "provider_empty_candidates" in msg or "empty content from llm" in msg:
        code = "PROVIDER_EMPTY_CANDIDATES"
        return "provider", code, {code: 1}

    if ("429" in msg) and ("rate limit" in msg or "too many requests" in msg):
        code = "PROVIDER_RATE_LIMIT"
        return "provider", code, {code: 1}

    if "code_timeout[" in msg or "codex_timeout[" in msg:
        code = "AGENT_TURN_TIMEOUT"
        return "runtime", code, {code: 1}

    if "timeout after" in msg and "question_timeout" in msg:
        code = "QUESTION_TIMEOUT"
        return "runtime", code, {code: 1}

    return None, None, {}


def _build_composability_diagnostics(
    *,
    tool_calls: list[dict],
    tool_contract_rejections: int | None,
    rejected_missing_reasoning_calls: int | None,
    control_loop_suppressed_calls: int | None,
    tool_contract_violation_events: list[dict] | None,
    available_artifacts_final: list[str] | None,
) -> dict:
    """Summarize composability health from tool-call traces + agent metadata."""
    category_counts: dict[str, int] = {}
    error_tools: dict[str, int] = {}
    examples: list[dict[str, str]] = []

    for tc in tool_calls:
        error_text = _extract_tool_error_text(tc)
        if not error_text:
            continue
        category = _classify_tool_error(error_text)
        tool_name = str(tc.get("tool", "") or "<unknown>")
        category_counts[category] = category_counts.get(category, 0) + 1
        error_tools[tool_name] = error_tools.get(tool_name, 0) + 1
        if len(examples) < 5:
            examples.append({
                "tool": tool_name,
                "category": category,
                "error": error_text[:240],
            })

    n_errors = sum(category_counts.values())
    arg_coercion_events = sum(
        len(tc.get("arg_coercions", []) or [])
        for tc in tool_calls
        if isinstance(tc, dict)
    )
    arg_coercion_calls = sum(
        1
        for tc in tool_calls
        if isinstance(tc, dict) and len(tc.get("arg_coercions", []) or []) > 0
    )
    n_non_control_calls = sum(
        1 for tc in tool_calls if str(tc.get("tool", "")) not in _CONTROL_TOOL_NAMES
    )
    unknown_tools = sorted({
        str(tc.get("tool", ""))
        for tc in tool_calls
        if str(tc.get("tool", "")) and str(tc.get("tool", "")) not in _BENCHMARK_TOOL_CONTRACTS
    })

    n_contract = int(tool_contract_rejections or 0)
    if n_contract == 0:
        n_contract = category_counts.get("contract_violation", 0)

    status = "ok"
    if n_errors > 0:
        status = "degraded"
        if (
            category_counts.get("tool_interface_mismatch", 0) > 0
            or category_counts.get("missing_prerequisite", 0) > 0
            or category_counts.get("tool_unavailable", 0) > 0
        ):
            status = "broken"

    return {
        "status": status,
        "n_errors": n_errors,
        "error_categories": dict(sorted(category_counts.items())),
        "error_tools": dict(sorted(error_tools.items(), key=lambda kv: (-kv[1], kv[0]))),
        "error_examples": examples,
        "n_contract_rejections": n_contract,
        "n_missing_reasoning_rejections": int(rejected_missing_reasoning_calls or 0),
        "n_control_loop_suppressed": int(control_loop_suppressed_calls or 0),
        "n_arg_coercions": arg_coercion_events,
        "n_arg_coercion_calls": arg_coercion_calls,
        "n_non_control_calls": n_non_control_calls,
        "unknown_tools": unknown_tools,
        "available_artifacts_final": available_artifacts_final or [],
        "contract_violation_events": tool_contract_violation_events or [],
    }


def _resolve_failure_threshold(metric: str, threshold: float | None) -> float:
    """Resolve metric threshold used to classify failing questions."""
    if threshold is not None:
        return float(threshold)
    if metric == "f1":
        return 0.999999
    return 0.5


def _collect_failing_ids(
    records: list[dict],
    *,
    metric: str,
    threshold: float | None = None,
) -> set[str]:
    """Collect question ids considered failing under the chosen metric."""
    resolved_threshold = _resolve_failure_threshold(metric, threshold)
    failing: set[str] = set()
    for rec in records:
        qid = rec.get("id")
        if not qid:
            continue
        value = rec.get(metric)
        if value is None:
            failing.add(qid)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            failing.add(qid)
            continue
        if numeric < resolved_threshold:
            failing.add(qid)
    return failing


def _load_failing_ids_from_results_file(
    results_path: Path,
    *,
    metric: str,
    threshold: float | None = None,
) -> set[str]:
    """Load failing question IDs from a prior benchmark JSON file."""
    with open(results_path) as f:
        payload = json.load(f)
    records = payload.get("results") or []
    if not isinstance(records, list):
        return set()
    return _collect_failing_ids(records, metric=metric, threshold=threshold)


def _write_selected_question_ids(ids_path: Path, question_ids: list[str]) -> None:
    """Persist the final selected question IDs for reproducible reruns."""
    ids_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ids_path, "w") as f:
        for qid in question_ids:
            f.write(f"{qid}\n")


# --- MCP server config ---

def _build_mcp_servers(
    benchmark_mode: int = 1,
    dataset_name: str = "",
    embed_model: str = "",
    embed_dimensions: int | None = None,
    disable_embedding_tools: bool = False,
) -> dict:
    """Build MCP server config with API keys forwarded from current env.

    Args:
        benchmark_mode: 0=all tools, 1=benchmark prune, 2=aggressive benchmark prune
        dataset_name: Pre-load this dataset's graph+VDB on MCP server startup
    """
    import llm_client  # triggers auto-load of ~/.secrets/api_keys.env
    env = {}
    for key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "HOME",
        "PATH",
    ):
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
    if embed_model:
        env["DIGIMON_EMBED_MODEL"] = embed_model
    if isinstance(embed_dimensions, int) and embed_dimensions > 0:
        env["DIGIMON_EMBED_DIMENSIONS"] = str(embed_dimensions)
    if disable_embedding_tools:
        env["DIGIMON_SKIP_VDB_PRELOAD"] = "1"
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


async def _extract_date_mentions_from_artifacts_direct(
    chunk_artifact_ids: list[str] | None = None,
    chunk_artifacts: list[dict] | None = None,
    max_mentions: int = 20,
) -> str:
    """Extract date mentions from runtime-resolved chunk artifact handles.

    Use `chunk_artifact_ids` with llm_client handle-input contracts. `chunk_artifacts`
    is runtime-injected and should not be populated by the model directly.
    """
    import digimon_mcp_stdio_server as dms

    sources: list[dict[str, str]] = []
    for item in chunk_artifacts or []:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "").strip()
        text = str(
            item.get("text")
            or item.get("text_content")
            or item.get("content")
            or ""
        ).strip()
        if not text:
            continue
        sources.append({"chunk_id": chunk_id, "text": text})

    if not sources:
        requested = [
            str(item).strip()
            for item in (chunk_artifact_ids or [])
            if str(item).strip()
        ]
        return json.dumps(
            {
                "error": "No runtime-resolved chunk artifacts were available for the requested handles.",
                "requested_chunk_artifact_ids": requested,
                "n_sources": 0,
            },
            indent=2,
        )

    return dms._extract_date_mentions_from_sources(
        sources=sources,
        max_mentions=max_mentions,
    )


_extract_date_mentions_from_artifacts_direct.__name__ = "extract_date_mentions_from_artifacts"
_extract_date_mentions_from_artifacts_direct.__tool_description__ = (
    "Extract normalized date mentions from previously produced chunk artifact handles. "
    "Use chunk_artifact_ids; chunk_artifacts is runtime-resolved."
)
_extract_date_mentions_from_artifacts_direct.__tool_input_examples__ = [
    {"chunk_artifact_ids": ["art_chunk_1"], "max_mentions": 5},
]


async def _init_direct_tools(dataset_name: str, disable_embedding_tools: bool = False) -> list:
    """Import DIGIMON MCP server module and initialize in-process.

    Returns list of tool functions ready for python_tools= parameter.
    Must be called once before run_agent with backend="direct".
    """
    # Set benchmark mode env vars BEFORE importing the MCP server module
    os.environ["DIGIMON_BENCHMARK_MODE"] = "1"
    os.environ["LLM_CLIENT_STRICT_MODELS"] = "1"  # ban deprecated models
    if dataset_name:
        os.environ["DIGIMON_PRELOAD_DATASET"] = dataset_name
    if disable_embedding_tools:
        os.environ["DIGIMON_SKIP_VDB_PRELOAD"] = "1"
    else:
        os.environ.pop("DIGIMON_SKIP_VDB_PRELOAD", None)

    import digimon_mcp_stdio_server as dms

    # Initialize DIGIMON context (loads config, graph, VDB)
    await dms._ensure_initialized()

    # Collect benchmark-relevant tool functions from the MCP server module.
    # These are the same functions registered with @mcp.tool() minus hidden ones.
    _BENCHMARK_TOOLS = [
        dms.entity_vdb_search,
        dms.entity_string_search,
        dms.entity_neighborhood,
        dms.entity_onehop,
        dms.entity_ppr,
        dms.entity_link,
        dms.entity_resolve_names_to_ids,
        dms.entity_profile,
        dms.entity_select_candidate,
        dms.entity_tfidf,
        dms.relationship_onehop,
        dms.relationship_score_aggregator,
        dms.relationship_vdb_search,
        dms.chunk_from_relationships,
        dms.chunk_occurrence,
        dms.chunk_get_text_by_chunk_ids,
        dms.chunk_get_text_by_entity_ids,
        dms.extract_date_mentions,
        _extract_date_mentions_from_artifacts_direct,
        dms.chunk_text_search,
        dms.chunk_vdb_search,
        dms.search_then_expand_onehop,
        dms.chunk_aggregator,
        dms.list_available_resources,
        dms.subgraph_khop_paths,
        dms.subgraph_steiner_tree,
        dms.meta_pcst_optimize,
    ]

    # Benchmark planning/disambiguation controls (if available in server mode)
    for maybe_tool in (
        "semantic_plan",
        "todo_write",
        "bridge_disambiguate",
    ):
        if hasattr(dms, maybe_tool):
            _BENCHMARK_TOOLS.append(getattr(dms, maybe_tool))

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
        main_config = dms._state.get("config")
        graph_type = getattr(getattr(main_config, "graph", None), "type", "er_graph")
        working_dir = str(getattr(main_config, "working_dir", "./results"))
        manifest = load_required_graph_manifest(
            dataset_name=dataset_name,
            graph_type=graph_type,
            working_dir=working_dir,
        )
        manifest_allowed_tool_names = set(
            filter_tool_names_by_graph_manifest(
                (tool.__name__ for tool in _BENCHMARK_TOOLS),
                manifest,
            )
        )
        _BENCHMARK_TOOLS = [
            tool for tool in _BENCHMARK_TOOLS if tool.__name__ in manifest_allowed_tool_names
        ]
        print(
            "Direct backend: graph manifest "
            f"{manifest.graph_type}/{manifest.graph_profile.value} filtered tools to "
            f"{len(_BENCHMARK_TOOLS)} entries",
            file=sys.stderr,
        )

        vdbs = ctx.list_vdbs() if hasattr(ctx, "list_vdbs") else []
        vdb_names = " ".join(vdbs)

        if "entities" not in vdb_names:
            _BENCHMARK_TOOLS = [
                t for t in _BENCHMARK_TOOLS
                if t.__name__ not in {"entity_vdb_search", "entity_link"}
            ]
        if "relationship" not in vdb_names:
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "relationship_vdb_search"]
        if "chunk" not in vdb_names:
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "chunk_vdb_search"]

        # chunk_aggregator needs sparse matrices
        e2r_path, r2c_path = dms._sparse_matrix_paths(dataset_name)
        if not (e2r_path.exists() and r2c_path.exists()):
            _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ != "chunk_aggregator"]

    if disable_embedding_tools:
        disabled = {"entity_vdb_search", "chunk_vdb_search", "entity_link"}
        _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ not in disabled]
        print(
            f"Direct backend: embedding tools disabled ({', '.join(sorted(disabled))})",
            file=sys.stderr,
        )

    # Mode-based tool filtering
    mode_env = os.environ.get("DIGIMON_BENCHMARK_MODE_NAME", "")
    if mode_env == "baseline":
        # Non-graph baseline: only chunk search + submit
        baseline_tools = {"chunk_text_search", "chunk_vdb_search", "submit_answer",
                          "list_available_resources"}
        _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ in baseline_tools]
        print(f"Baseline mode: {len(_BENCHMARK_TOOLS)} tools (no graph)", file=sys.stderr)
    elif mode_env == "fixed_graph":
        # Fixed graph pipeline: entity search + neighborhood + chunk + submit
        fixed_tools = {"entity_string_search", "entity_neighborhood", "entity_profile",
                       "chunk_text_search", "chunk_get_text_by_chunk_ids",
                       "list_available_resources", "submit_answer"}
        _BENCHMARK_TOOLS = [t for t in _BENCHMARK_TOOLS if t.__name__ in fixed_tools]
        print(f"Fixed graph mode: {len(_BENCHMARK_TOOLS)} tools", file=sys.stderr)

    tool_names = [t.__name__ for t in _BENCHMARK_TOOLS]
    short_descs = getattr(dms, "_BENCHMARK_SHORT_DESCS", {})
    for tool_fn in _BENCHMARK_TOOLS:
        short = short_descs.get(tool_fn.__name__)
        if isinstance(short, str) and short.strip():
            setattr(tool_fn, "__tool_description__", short.strip())

    print(f"Direct backend: {len(_BENCHMARK_TOOLS)} Python tools loaded: {tool_names}", file=sys.stderr)
    return _BENCHMARK_TOOLS


# --- Agent model detection ---

def _is_codex_model(model: str) -> bool:
    """Check if model routes through the Codex SDK."""
    lower = model.lower()
    return lower == "codex" or lower.startswith("codex/") or lower.startswith("codex-")


def _is_claude_code_model(model: str) -> bool:
    """Check if model routes through the Claude Agent SDK."""
    lower = model.lower()
    return lower == "claude-code" or lower.startswith("claude-code/")


def _is_agent_sdk_model(model: str) -> bool:
    """Check if model uses any agent SDK (codex or claude-code)."""
    return _is_codex_model(model) or _is_claude_code_model(model)


def _resolve_codex_profile(model: str, profile: str) -> str:
    """Resolve codex profile. Non-codex models always use 'default'."""
    if not _is_codex_model(model):
        return "default"
    normalized = (profile or "").strip().lower()
    if normalized in {"compact", "default"}:
        return normalized
    return "compact"


def _model_slug(model: str) -> str:
    """Convert model string to filesystem-safe slug. e.g. 'gemini/gemini-3-flash-preview' -> 'gemini-3-flash-preview'."""
    # Use last segment after /
    slug = model.rsplit("/", 1)[-1]
    # Replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    return slug or "unknown"


def _is_image_generation_model(model: str) -> bool:
    """Return True for known image-generation model families."""
    lower = (model or "").strip().lower()
    if not lower:
        return False
    base = lower.rsplit("/", 1)[-1]
    hints = (
        "gpt-image",
        "dall-e",
        "imagen",
        "stable-diffusion",
        "sdxl",
        "flux",
    )
    return any(h in base for h in hints)


def _normalize_primary_model_for_benchmark(model: str) -> str:
    """Route non-Gemini, non-image models through OpenRouter by default.

    Policy requested by project owner:
    - keep Gemini provider-native model IDs (gemini/*)
    - keep image-generation families provider-native
    - route everything else through OpenRouter when possible
    """
    raw = (model or "").strip()
    if not raw:
        return raw

    lower = raw.lower()
    if lower.startswith(("codex", "claude-code", "openai-agents")):
        return raw
    if lower.startswith(("openrouter/", "gemini/")):
        return raw
    if _is_image_generation_model(raw):
        return raw

    # Provider-prefixed model IDs (openai/*, anthropic/*, deepseek/*, etc.).
    if "/" in raw:
        return f"openrouter/{raw}"

    # Bare model IDs: map common families to OpenRouter provider namespaces.
    bare = lower
    if bare.startswith(("gpt-", "o1", "o3", "o4", "chatgpt", "text-embedding-", "text-moderation-")):
        return f"openrouter/openai/{raw}"
    if bare.startswith("claude"):
        return f"openrouter/anthropic/{raw}"
    if bare.startswith("deepseek"):
        return f"openrouter/deepseek/{raw}"
    if bare.startswith("grok"):
        return f"openrouter/x-ai/{raw}"
    if bare.startswith("mistral"):
        return f"openrouter/mistralai/{raw}"
    return raw


def _resolve_embed_model_for_benchmark(
    *,
    explicit_embed_model: str,
    disable_embedding_tools: bool,
    primary_model: str,
) -> str:
    """Choose embedding model for benchmark runs when caller did not specify one.

    Priority:
    1) explicit --embed-model
    2) if embedding tools disabled: no override needed
    3) provider-aware default based on primary model lane
       - gemini/* primary + GEMINI_API_KEY -> Gemini embeddings
       - openrouter/* primary + OPENROUTER_API_KEY -> OpenRouter embeddings
    4) fallback to available provider keys
    5) else: keep default config
    """
    explicit = (explicit_embed_model or "").strip()
    if explicit:
        return explicit
    if disable_embedding_tools:
        return ""
    model_lower = (primary_model or "").strip().lower()
    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))

    if model_lower.startswith("gemini/") and has_gemini:
        return "gemini/gemini-embedding-001"
    if model_lower.startswith("openrouter/") and has_openrouter:
        return "openrouter/openai/text-embedding-3-small"

    if has_openrouter:
        return "openrouter/openai/text-embedding-3-small"
    if has_gemini:
        return "gemini/gemini-embedding-001"
    return ""


def _resolve_fallback_models_for_benchmark(
    *,
    model: str,
    fallback_models_arg: str,
    lane_policy: str = "pure",
) -> list[str] | None:
    """Resolve fallback chain, removing blanks/duplicates/primary model."""
    raw = (fallback_models_arg or "").strip()
    if raw.lower() == "none":
        return None

    if raw:
        candidates = [_normalize_primary_model_for_benchmark(m.strip()) for m in raw.split(",") if m.strip()]
    else:
        if lane_policy == "pure" and _is_codex_model(model):
            return None
        prefer_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
        lower = model.lower()
        if prefer_openrouter:
            if lower.startswith("openrouter/"):
                candidates = [
                    "openrouter/deepseek/deepseek-chat",
                    "openrouter/google/gemini-2.5-flash",
                    "openrouter/openai/gpt-5-mini",
                ]
            elif lower.startswith("gemini/"):
                candidates = [
                    "openrouter/deepseek/deepseek-chat",
                    "openrouter/openai/gpt-5-mini",
                ]
            else:
                candidates = [
                    "openrouter/deepseek/deepseek-chat",
                    "openrouter/google/gemini-2.5-flash",
                ]
        else:
            if lower.startswith("gemini/"):
                candidates = ["openrouter/deepseek/deepseek-chat", "gpt-5-mini"]
            elif lower.startswith("openrouter/"):
                candidates = ["gpt-5-mini", "gemini/gemini-2.5-flash"]
            else:
                candidates = ["openrouter/deepseek/deepseek-chat", "gemini/gemini-2.5-flash"]

    primary = model.strip().lower()
    resolved: list[str] = []
    seen: set[str] = {primary}
    for cand in candidates:
        name = cand.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(name)
    return resolved or None


def _resolve_finalization_fallback_models_for_benchmark(
    *,
    model: str,
    lane_policy: str,
    fallback_models: list[str] | None,
    finalization_fallback_models_arg: str,
) -> list[str] | None:
    """Resolve forced-final fallback chain.

    Rules:
    1) explicit --finalization-fallback-models wins ("none" disables)
    2) reliability lane defaults to first two normal fallback models
    3) pure lane defaults to none
    """
    raw = (finalization_fallback_models_arg or "").strip()
    if raw.lower() == "none":
        return None

    if raw:
        candidates = [_normalize_primary_model_for_benchmark(m.strip()) for m in raw.split(",") if m.strip()]
    elif lane_policy == "reliability":
        candidates = list(fallback_models or [])[:2]
    else:
        candidates = []

    primary = (model or "").strip().lower()
    deduped: list[str] = []
    seen: set[str] = {primary}
    for candidate in candidates:
        value = (candidate or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped or None


def _extract_answer_from_freeform_content(content: str) -> str | None:
    """Extract an answer span from freeform final text when submit_answer was not accepted."""
    text = (content or "").strip()
    if not text:
        return None

    def _extract_from_json_blob(blob: str) -> str | None:
        try:
            payload = json.loads(blob)
        except Exception:
            return None
        if isinstance(payload, dict):
            answer = payload.get("answer")
            if isinstance(answer, str) and answer.strip():
                return answer.strip()
        return None

    # Try full text and fenced JSON blocks first.
    direct = _extract_from_json_blob(text)
    if direct:
        return direct

    for fenced in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
        extracted = _extract_from_json_blob(fenced.strip())
        if extracted:
            return extracted

    # Try submit_answer(...) plaintext patterns.
    patterns = [
        r'answer\s*=\s*"([^"\n]{1,300})"',
        r"answer\s*=\s*'([^'\n]{1,300})'",
        r'"answer"\s*:\s*"([^"\n]{1,300})"',
        r"'answer'\s*:\s*'([^'\n]{1,300})'",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate

    labeled_match = re.search(
        r"(?:final answer|answer)\s*:\s*([^\n]{1,300})",
        text,
        flags=re.IGNORECASE,
    )
    if labeled_match:
        candidate = labeled_match.group(1).strip(" `*\"'")
        if candidate:
            return candidate

    lines = [line.strip(" `*\"'") for line in text.splitlines() if line.strip()]
    if lines:
        last_line = lines[-1]
        if last_line and len(last_line.split()) <= 12:
            return last_line

    # If the model answered in a sentence but contains a single explicit full date,
    # extract the span to avoid formatting-only score misses.
    month_date_matches = re.findall(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
        text,
        flags=re.IGNORECASE,
    )
    if len(month_date_matches) == 1:
        return month_date_matches[0].strip()

    return None


_WARNING_EVIDENCE_METRIC_RE = re.compile(
    r"METRIC:\s+evidence_turns=(?P<total>\d+),\s+new_evidence_turns=(?P<new>\d+),\s+"
    r"stagnant_evidence_turns=(?P<stagnant>\d+),\s+retrieval_stagnation_streak_max=(?P<streak>\d+),\s+"
    r"evidence_pointer_count=(?P<pointers>\d+)"
)


def _populate_warning_derived_fields(
    *,
    warnings: list[str],
    evidence_turns_total: Any,
    evidence_turns_with_new_evidence: Any,
    evidence_turns_without_new_evidence: Any,
    retrieval_stagnation_streak_max: Any,
    evidence_pointer_count: Any,
    evidence_digest_basis: Any,
    submit_completion_mode: Any,
    submit_validator_accepted: Any,
    submit_forced_accept_on_budget_exhaustion: Any,
    first_terminal_failure_event_code: Any,
    tool_arg_validation_rejections: Any,
    required_submit_missing: Any = None,
) -> dict[str, Any]:
    """Backfill observability fields from warning strings when metadata is missing."""
    for warning in warnings:
        if (
            evidence_turns_total is None
            or evidence_turns_with_new_evidence is None
            or evidence_turns_without_new_evidence is None
            or retrieval_stagnation_streak_max is None
            or evidence_pointer_count is None
        ):
            metric_match = _WARNING_EVIDENCE_METRIC_RE.search(warning)
            if metric_match:
                evidence_turns_total = int(metric_match.group("total"))
                evidence_turns_with_new_evidence = int(metric_match.group("new"))
                evidence_turns_without_new_evidence = int(metric_match.group("stagnant"))
                retrieval_stagnation_streak_max = int(metric_match.group("streak"))
                evidence_pointer_count = int(metric_match.group("pointers"))
                if evidence_digest_basis is None:
                    evidence_digest_basis = "canonical_evidence_pointers"

        if tool_arg_validation_rejections is None and warning.startswith("TOOL_ARG_VALIDATION:"):
            match = re.search(r"rejected\s+(\d+)\s+tool call", warning)
            if match:
                tool_arg_validation_rejections = int(match.group(1))

        if first_terminal_failure_event_code is None:
            if warning.startswith("SUBMIT_FORCED_ACCEPT_BUDGET_EXHAUSTION:"):
                first_terminal_failure_event_code = "SUBMIT_FORCED_ACCEPT_BUDGET_EXHAUSTION"
            elif warning.startswith("SUBMIT_FORCED_ACCEPT_TURN_EXHAUSTION:"):
                first_terminal_failure_event_code = "SUBMIT_FORCED_ACCEPT_TURN_EXHAUSTION"
            elif warning.startswith("SUBMIT_FORCED_ACCEPT_FORCED_FINAL:"):
                first_terminal_failure_event_code = "SUBMIT_FORCED_ACCEPT_FORCED_FINAL"

    if submit_completion_mode is None:
        if submit_validator_accepted:
            submit_completion_mode = "grounded_submit"
        elif required_submit_missing:
            submit_completion_mode = "missing_required_submit"
        elif submit_forced_accept_on_budget_exhaustion:
            submit_completion_mode = "forced_terminal_accept"
        elif isinstance(first_terminal_failure_event_code, str) and first_terminal_failure_event_code.startswith(
            "SUBMIT_FORCED_ACCEPT_"
        ):
            submit_completion_mode = "forced_terminal_accept"

    if first_terminal_failure_event_code is None and required_submit_missing:
        first_terminal_failure_event_code = "REQUIRED_SUBMIT_MISSING"

    return {
        "evidence_turns_total": evidence_turns_total,
        "evidence_turns_with_new_evidence": evidence_turns_with_new_evidence,
        "evidence_turns_without_new_evidence": evidence_turns_without_new_evidence,
        "retrieval_stagnation_streak_max": retrieval_stagnation_streak_max,
        "evidence_pointer_count": evidence_pointer_count,
        "evidence_digest_basis": evidence_digest_basis,
        "submit_completion_mode": submit_completion_mode,
        "first_terminal_failure_event_code": first_terminal_failure_event_code,
        "tool_arg_validation_rejections": tool_arg_validation_rejections,
    }


# --- Run agent ---

async def run_agent(
    question: str,
    dataset_name: str,
    timeout: int = 0,
    turn_timeout: int | None = None,
    model: str = "codex",
    reasoning_effort: str = "high",
    max_turns: int = 20,
    max_tool_calls: int | None = 20,
    mcp_session_pool: object = None,
    mode: str = CANONICAL_MODE,
    backend: str = "mcp",
    python_tools: list | None = None,
    temperature: float | None = 0.0,
    fallback_models: list[str] | None = None,
    finalization_fallback_models: list[str] | None = None,
    num_retries: int = 2,
    forced_final_max_attempts: int = 1,
    forced_final_circuit_breaker_threshold: int = 2,
    retrieval_stagnation_turns: int = 4,
    retrieval_stagnation_action: str = "force_final",
    suppress_control_loop_calls: bool = True,
    force_submit_retry_on_max_tool_calls: bool = True,
    accept_forced_answer_on_max_tool_calls: bool = True,
    lane_policy: str = "pure",
    trace_id: str = "",
    max_message_chars: int = 0,  # 0 = no compaction (use model's full context window)
    codex_profile: str = "default",
) -> dict:
    """Run an agent on a single question via llm_client.

    For Codex models: uses Codex SDK with MCP servers.
    For other models: uses llm_client's MCP agent loop (litellm + tool calling).
    For backend="direct": calls Python functions in-process via python_tools=.

    Args:
        mcp_session_pool: Optional MCPSessionPool for reusing MCP connections
            across questions (non-Codex models only).
        timeout: Hard timeout per question (seconds). <=0 disables this watchdog.
        turn_timeout: Per-LLM-call timeout (seconds). <=0 disables per-call
            timeout. If omitted, defaults to 0 when hard timeout is disabled,
            otherwise min(timeout, 60).
        max_tool_calls: Tool-call budget per question for non-agent tool loops.
        mode: Prompt mode (canonical hybrid; legacy aliases are mapped).
        backend: 'mcp' (default) or 'direct' (in-process Python tools)
        python_tools: List of Python callables for direct backend
        lane_policy: 'pure' (strict attribution) or 'reliability' (finalization rescue allowed)
        trace_id: Trace ID for correlating LLM calls
        codex_profile: 'default' or 'compact' for Codex-specific benchmark tuning.
        retrieval_stagnation_action: 'force_final' (default) or 'observe'
        suppress_control_loop_calls: Suppress repeated invalid submit/todo control loops.
        force_submit_retry_on_max_tool_calls: Count forced submit retry attempt after budget exhaustion.
        accept_forced_answer_on_max_tool_calls: Accept forced-final plain answer when submit validation cannot be satisfied at budget exhaustion.

    Returns dict with: answer, tool_calls, usage, cost, latency_s, error
    """
    from llm_client import acall_llm

    task = "digimon.benchmark"
    project_root = str(Path(__file__).parent.parent)
    prompt_variant = "codex_compact" if (_is_codex_model(model) and codex_profile == "compact") else "default"
    messages = build_messages(
        question,
        dataset_name,
        mode=mode,
        prompt_variant=prompt_variant,
    )

    question_timeout = max(0, int(timeout))
    default_turn_timeout = 0 if question_timeout <= 0 else min(question_timeout, 60)
    effective_turn_timeout = max(0, int(turn_timeout if turn_timeout is not None else default_turn_timeout))
    t0 = time.monotonic()
    try:
        async def _invoke_agent() -> object:
            if backend == "direct" and python_tools:
                # Direct Python tool loop — no MCP subprocess
                # Reset chunk dedup between questions
                import digimon_mcp_stdio_server as dms
                dms._reset_chunk_dedup()

                # Tool contract enforcement disabled: binding_conflict between
                # entity VDB (musique_ergraph) and chunk VDB (musique_chunks)
                # causes repeated rejections → timeout. The contract system
                # treats different VDB collections as conflicting dataset_ids.
                # TODO: fix the binding_conflict logic in llm_client to handle
                # multiple VDB collections per dataset.
                return await acall_llm(
                    model,
                    messages,
                    timeout=effective_turn_timeout,
                    python_tools=python_tools,
                    max_turns=max_turns,
                    max_tool_calls=max_tool_calls,
                    require_tool_reasoning=True,
                    enforce_tool_contracts=False,
                    num_retries=num_retries,
                    task=task,
                    trace_id=trace_id,
                    max_budget=0,
                    max_message_chars=max_message_chars,
                    forced_final_max_attempts=forced_final_max_attempts,
                    forced_final_circuit_breaker_threshold=forced_final_circuit_breaker_threshold,
                    retrieval_stagnation_turns=retrieval_stagnation_turns,
                    retrieval_stagnation_action=retrieval_stagnation_action,
                    suppress_control_loop_calls=suppress_control_loop_calls,
                    **({"temperature": temperature} if temperature is not None else {}),
                    **({"fallback_models": fallback_models} if fallback_models else {}),
                    **({"finalization_fallback_models": finalization_fallback_models} if finalization_fallback_models else {}),
                )
            if _is_codex_model(model):
                # Codex SDK path — agent-specific kwargs
                codex_network_access = False if codex_profile == "compact" else True
                codex_turn_timeout = effective_turn_timeout
                if question_timeout > 0:
                    # Prevent worker waits from outliving the question watchdog.
                    codex_turn_timeout = min(codex_turn_timeout, question_timeout)
                return await acall_llm(
                    model,
                    messages,
                    timeout=codex_turn_timeout,
                    # Run each Codex turn in a worker process so timeout/cancel
                    # behavior is bounded even when the SDK becomes unresponsive.
                    codex_process_isolation=True,
                    # Keep Codex on MCP tools only for benchmark determinism and
                    # lower first-turn latency variance.
                    web_search_enabled=False,
                    network_access_enabled=codex_network_access,
                    working_directory=project_root,
                    approval_policy="never",
                    sandbox_mode="workspace-write",
                    skip_git_repo_check=True,
                    model_reasoning_effort=reasoning_effort,
                    mcp_servers=DIGIMON_MCP_SERVERS,
                    # Benchmark tool calls are read-only/idempotent; allow retries.
                    agent_retry_safe=True,
                    num_retries=num_retries,
                    task=task,
                    trace_id=trace_id,
                    max_budget=0,
                    **({"fallback_models": fallback_models} if fallback_models else {}),
                )
            if _is_claude_code_model(model):
                # Claude Agent SDK path
                return await acall_llm(
                    model,
                    messages,
                    timeout=effective_turn_timeout,
                    cwd=project_root,
                    permission_mode="bypassPermissions",
                    max_turns=max_turns,
                    mcp_servers=DIGIMON_MCP_SERVERS,
                    task=task,
                    trace_id=trace_id,
                    max_budget=0,
                )
            if mcp_session_pool is not None:
                # MCP agent loop with persistent session pool
                return await acall_llm(
                    model,
                    messages,
                    timeout=effective_turn_timeout,
                    mcp_sessions=mcp_session_pool,
                    max_turns=max_turns,
                    max_tool_calls=max_tool_calls,
                    require_tool_reasoning=True,
                    enforce_tool_contracts=False,
                    tool_contracts=_BENCHMARK_TOOL_CONTRACTS,
                    initial_artifacts=_BENCHMARK_INITIAL_ARTIFACTS,
                    num_retries=num_retries,
                    task=task,
                    trace_id=trace_id,
                    max_budget=0,
                    max_message_chars=max_message_chars,
                    forced_final_max_attempts=forced_final_max_attempts,
                    forced_final_circuit_breaker_threshold=forced_final_circuit_breaker_threshold,
                    retrieval_stagnation_turns=retrieval_stagnation_turns,
                    retrieval_stagnation_action=retrieval_stagnation_action,
                    suppress_control_loop_calls=suppress_control_loop_calls,
                    force_submit_retry_on_max_tool_calls=force_submit_retry_on_max_tool_calls,
                    accept_forced_answer_on_max_tool_calls=accept_forced_answer_on_max_tool_calls,
                    **({"temperature": temperature} if temperature is not None else {}),
                    **({"fallback_models": fallback_models} if fallback_models else {}),
                    **({"finalization_fallback_models": finalization_fallback_models} if finalization_fallback_models else {}),
                )
            # MCP agent loop — fresh server per call (legacy)
            return await acall_llm(
                model,
                messages,
                timeout=effective_turn_timeout,
                mcp_servers=DIGIMON_MCP_SERVERS,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                require_tool_reasoning=True,
                enforce_tool_contracts=False,
                tool_contracts=_BENCHMARK_TOOL_CONTRACTS,
                initial_artifacts=_BENCHMARK_INITIAL_ARTIFACTS,
                num_retries=num_retries,
                task=task,
                trace_id=trace_id,
                max_budget=0,
                max_message_chars=max_message_chars,
                forced_final_max_attempts=forced_final_max_attempts,
                forced_final_circuit_breaker_threshold=forced_final_circuit_breaker_threshold,
                retrieval_stagnation_turns=retrieval_stagnation_turns,
                retrieval_stagnation_action=retrieval_stagnation_action,
                suppress_control_loop_calls=suppress_control_loop_calls,
                force_submit_retry_on_max_tool_calls=force_submit_retry_on_max_tool_calls,
                accept_forced_answer_on_max_tool_calls=accept_forced_answer_on_max_tool_calls,
                **({"temperature": temperature} if temperature is not None else {}),
                **({"fallback_models": fallback_models} if fallback_models else {}),
                **({"finalization_fallback_models": finalization_fallback_models} if finalization_fallback_models else {}),
            )

        async def _invoke_agent_with_hard_timeout() -> object:
            """Enforce hard question timeout even if inner cancellation is slow."""
            agent_task = asyncio.create_task(_invoke_agent())
            try:
                done, _ = await asyncio.wait({agent_task}, timeout=question_timeout)
                if agent_task in done:
                    return await agent_task

                # Timeout hit: request cancellation, then bound how long we wait.
                agent_task.cancel()
                cancel_grace_s = 1.0
                try:
                    await asyncio.wait_for(asyncio.shield(agent_task), timeout=cancel_grace_s)
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    # Ignore slow/uncooperative cancellation; timeout should still surface.
                    pass
                raise asyncio.TimeoutError
            finally:
                # Drain task exceptions when it does finish to avoid unhandled warnings.
                if not agent_task.done():
                    def _drain_unhandled(t: asyncio.Task) -> None:
                        try:
                            t.exception()
                        except BaseException:
                            pass
                    agent_task.add_done_callback(_drain_unhandled)

        # Optional hard per-question watchdog.
        if question_timeout > 0:
            result = await _invoke_agent_with_hard_timeout()
        else:
            result = await _invoke_agent()

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
        budgeted_tool_calls_used = None
        rejected_missing_reasoning_calls = None
        control_loop_suppressed_calls = None
        tool_contract_rejections = None
        available_artifacts_final = None
        tool_contract_violation_events = None
        artifact_timeline = None
        tool_arg_coercions = None
        tool_arg_coercion_calls = None
        tool_arg_validation_rejections = None
        available_capabilities_final = None
        primary_failure_class = None
        secondary_failure_classes = None
        first_terminal_failure_event_code = None
        failure_event_codes = None
        failure_event_code_counts = None
        no_legal_noncontrol_turns = None
        retrieval_no_hits_count = None
        submit_validation_reason_counts = None
        hard_bindings_hash = None
        full_bindings_hash = None
        run_config_hash = None
        lane_closure_analysis = None
        tool_disclosure_repair_suggestions = None
        deficit_no_progress_streak_max = None
        deficit_no_progress_nudges = None
        finalization_fallback_used = None
        finalization_fallback_succeeded = None
        finalization_events = None
        forced_final_attempts = None
        forced_final_circuit_breaker_opened = None
        retrieval_stagnation_triggered = None
        retrieval_stagnation_turn = None
        retrieval_stagnation_streak_max = None
        evidence_digest_change_count = None
        evidence_turns_total = None
        evidence_turns_with_new_evidence = None
        evidence_turns_without_new_evidence = None
        evidence_pointer_count = None
        evidence_digest_basis = None
        context_tool_result_clearings = None
        context_tool_results_cleared = None
        context_tool_result_cleared_chars = None
        requires_submit_answer = None
        submit_answer_call_count = None
        submit_answer_attempted = None
        submit_answer_succeeded = None
        submit_validator_accepted = None
        required_submit_missing = None
        submit_forced_retry_on_budget_exhaustion = None
        submit_forced_accept_on_budget_exhaustion = None
        submit_completion_mode = None
        raw_response = result.raw_response
        raw_metadata = None
        if isinstance(raw_response, dict):
            conversation_trace = raw_response.get("conversation_trace")
            candidate_metadata = raw_response.get("metadata")
            if isinstance(candidate_metadata, dict):
                raw_metadata = candidate_metadata
        else:
            conversation_trace = getattr(raw_response, "conversation_trace", None) or None
            candidate_metadata = getattr(raw_response, "metadata", None)
            if isinstance(candidate_metadata, dict):
                raw_metadata = candidate_metadata

        if isinstance(raw_metadata, dict):
            budgeted_tool_calls_used = raw_metadata.get("budgeted_tool_calls_used")
            rejected_missing_reasoning_calls = raw_metadata.get("rejected_missing_reasoning_calls")
            control_loop_suppressed_calls = raw_metadata.get("control_loop_suppressed_calls")
            tool_contract_rejections = raw_metadata.get("tool_contract_rejections")
            available_artifacts_final = raw_metadata.get("available_artifacts_final")
            tool_contract_violation_events = raw_metadata.get("tool_contract_violation_events")
            artifact_timeline = raw_metadata.get("artifact_timeline")
            tool_arg_coercions = raw_metadata.get("tool_arg_coercions")
            tool_arg_coercion_calls = raw_metadata.get("tool_arg_coercion_calls")
            tool_arg_validation_rejections = raw_metadata.get("tool_arg_validation_rejections")
            available_capabilities_final = raw_metadata.get("available_capabilities_final")
            primary_failure_class = raw_metadata.get("primary_failure_class")
            secondary_failure_classes = raw_metadata.get("secondary_failure_classes")
            first_terminal_failure_event_code = raw_metadata.get("first_terminal_failure_event_code")
            failure_event_codes = raw_metadata.get("failure_event_codes")
            failure_event_code_counts = raw_metadata.get("failure_event_code_counts")
            no_legal_noncontrol_turns = raw_metadata.get("no_legal_noncontrol_turns")
            retrieval_no_hits_count = raw_metadata.get("retrieval_no_hits_count")
            submit_validation_reason_counts = raw_metadata.get("submit_validation_reason_counts")
            hard_bindings_hash = raw_metadata.get("hard_bindings_hash")
            full_bindings_hash = raw_metadata.get("full_bindings_hash")
            run_config_hash = raw_metadata.get("run_config_hash")
            lane_closure_analysis = raw_metadata.get("lane_closure_analysis")
            tool_disclosure_repair_suggestions = raw_metadata.get("tool_disclosure_repair_suggestions")
            deficit_no_progress_streak_max = raw_metadata.get("deficit_no_progress_streak_max")
            deficit_no_progress_nudges = raw_metadata.get("deficit_no_progress_nudges")
            finalization_fallback_used = raw_metadata.get("finalization_fallback_used")
            finalization_fallback_succeeded = raw_metadata.get("finalization_fallback_succeeded")
            finalization_events = raw_metadata.get("finalization_events")
            forced_final_attempts = raw_metadata.get("forced_final_attempts")
            forced_final_circuit_breaker_opened = raw_metadata.get(
                "forced_final_circuit_breaker_opened"
            )
            retrieval_stagnation_triggered = raw_metadata.get("retrieval_stagnation_triggered")
            retrieval_stagnation_turn = raw_metadata.get("retrieval_stagnation_turn")
            retrieval_stagnation_streak_max = raw_metadata.get("retrieval_stagnation_streak_max")
            evidence_digest_change_count = raw_metadata.get("evidence_digest_change_count")
            evidence_turns_total = raw_metadata.get("evidence_turns_total")
            evidence_turns_with_new_evidence = raw_metadata.get("evidence_turns_with_new_evidence")
            evidence_turns_without_new_evidence = raw_metadata.get("evidence_turns_without_new_evidence")
            evidence_pointer_count = raw_metadata.get("evidence_pointer_count")
            evidence_digest_basis = raw_metadata.get("evidence_digest_basis")
            context_tool_result_clearings = raw_metadata.get("context_tool_result_clearings")
            context_tool_results_cleared = raw_metadata.get("context_tool_results_cleared")
            context_tool_result_cleared_chars = raw_metadata.get("context_tool_result_cleared_chars")
            requires_submit_answer = raw_metadata.get("requires_submit_answer")
            submit_answer_call_count = raw_metadata.get("submit_answer_call_count")
            submit_answer_attempted = raw_metadata.get("submit_answer_attempted")
            submit_answer_succeeded = raw_metadata.get("submit_answer_succeeded")
            submit_validator_accepted = raw_metadata.get("submit_validator_accepted")
            required_submit_missing = raw_metadata.get("required_submit_missing")
            submit_forced_retry_on_budget_exhaustion = raw_metadata.get(
                "submit_forced_retry_on_budget_exhaustion"
            )
            submit_forced_accept_on_budget_exhaustion = raw_metadata.get(
                "submit_forced_accept_on_budget_exhaustion"
            )
            submit_completion_mode = raw_metadata.get("submit_completion_mode")

        # Extract answer from the most recent successful submit_answer call.
        # Ignore rejected/errored submits so the agent can keep searching.
        answer = None
        reasoning = None
        for tc in reversed(tool_calls):
            tool_name = tc.get("tool", "")
            if tool_name.endswith("submit_answer"):
                has_error = bool(tc.get("has_error") or tc.get("is_error") or tc.get("error"))
                if has_error:
                    continue

                result_preview = tc.get("result_preview")
                if isinstance(result_preview, str):
                    # Accept only explicit submit confirmations when result preview is available.
                    if '"status": "submitted"' not in result_preview:
                        continue

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

        # Fallback: check submitted_answer_value from agent metadata (set by
        # forced-final acceptance path when the agent submitted an answer that
        # was rejected by the validator but later accepted on budget exhaustion).
        if not answer and isinstance(raw_metadata, dict):
            meta_answer = raw_metadata.get("submitted_answer_value")
            if isinstance(meta_answer, str) and meta_answer.strip():
                answer = meta_answer.strip()

        # Fallback: extract from text if no submit_answer call and no metadata
        if not answer:
            raw_fallback = result.content.strip()
            extracted = _extract_answer_from_freeform_content(raw_fallback)
            answer = extracted or raw_fallback
            if _is_agent_sdk_model(model) and "\n" in answer:
                lines = [l.strip() for l in answer.split("\n") if l.strip()]
                answer = lines[-1] if lines else answer

        # SDK-backed runs do not always populate MCPAgent metadata fields.
        # Synthesize submit-answer observability so missing submit is explicit.
        if _is_agent_sdk_model(model):
            submit_events: list[dict[str, Any]] = []
            successful_submit = False
            for tc in tool_calls:
                tool_name = str(tc.get("tool", "")).strip()
                if not tool_name.endswith("submit_answer"):
                    continue
                submit_events.append(tc)
                has_error = bool(tc.get("has_error") or tc.get("is_error") or tc.get("error"))
                if has_error:
                    continue
                result_preview = tc.get("result_preview")
                if isinstance(result_preview, str):
                    lowered_preview = result_preview.lower()
                    # Treat explicit reject statuses as unsuccessful; otherwise
                    # consider non-error submit calls successful.
                    if "status" in lowered_preview and "rejected" in lowered_preview:
                        continue
                successful_submit = True

            if requires_submit_answer is None:
                requires_submit_answer = True
            if submit_answer_call_count is None:
                submit_answer_call_count = len(submit_events)
            if submit_answer_attempted is None:
                submit_answer_attempted = bool(submit_answer_call_count)
            if submit_answer_succeeded is None:
                submit_answer_succeeded = successful_submit
            if required_submit_missing is None and requires_submit_answer:
                required_submit_missing = not bool(submit_answer_succeeded)

            sdk_result_error = getattr(result, "error", None)
            if required_submit_missing and not sdk_result_error:
                if primary_failure_class is None:
                    primary_failure_class = "required_submit_missing"
                elif primary_failure_class != "required_submit_missing":
                    if not isinstance(secondary_failure_classes, list):
                        secondary_failure_classes = []
                    if "required_submit_missing" not in secondary_failure_classes:
                        secondary_failure_classes.append("required_submit_missing")

                if not isinstance(failure_event_codes, list):
                    failure_event_codes = []
                if "REQUIRED_SUBMIT_MISSING" not in failure_event_codes:
                    failure_event_codes.append("REQUIRED_SUBMIT_MISSING")

                if not isinstance(failure_event_code_counts, dict):
                    failure_event_code_counts = {}
                failure_event_code_counts["REQUIRED_SUBMIT_MISSING"] = max(
                    1,
                    int(failure_event_code_counts.get("REQUIRED_SUBMIT_MISSING", 0)),
                )

                if not first_terminal_failure_event_code:
                    first_terminal_failure_event_code = "REQUIRED_SUBMIT_MISSING"

        # Extract diagnostic warnings and models_used from result
        warnings = getattr(result, "warnings", []) or []
        warning_derived = _populate_warning_derived_fields(
            warnings=warnings,
            evidence_turns_total=evidence_turns_total,
            evidence_turns_with_new_evidence=evidence_turns_with_new_evidence,
            evidence_turns_without_new_evidence=evidence_turns_without_new_evidence,
            retrieval_stagnation_streak_max=retrieval_stagnation_streak_max,
            evidence_pointer_count=evidence_pointer_count,
            evidence_digest_basis=evidence_digest_basis,
            submit_completion_mode=submit_completion_mode,
            submit_validator_accepted=submit_validator_accepted,
            submit_forced_accept_on_budget_exhaustion=submit_forced_accept_on_budget_exhaustion,
            first_terminal_failure_event_code=first_terminal_failure_event_code,
            tool_arg_validation_rejections=tool_arg_validation_rejections,
            required_submit_missing=required_submit_missing,
        )
        evidence_turns_total = warning_derived["evidence_turns_total"]
        evidence_turns_with_new_evidence = warning_derived["evidence_turns_with_new_evidence"]
        evidence_turns_without_new_evidence = warning_derived["evidence_turns_without_new_evidence"]
        retrieval_stagnation_streak_max = warning_derived["retrieval_stagnation_streak_max"]
        evidence_pointer_count = warning_derived["evidence_pointer_count"]
        evidence_digest_basis = warning_derived["evidence_digest_basis"]
        submit_completion_mode = warning_derived["submit_completion_mode"]
        first_terminal_failure_event_code = warning_derived["first_terminal_failure_event_code"]
        tool_arg_validation_rejections = warning_derived["tool_arg_validation_rejections"]
        models_used: list[str] = []
        if isinstance(raw_response, dict):
            raw_models_used = raw_response.get("models_used")
            if isinstance(raw_models_used, list):
                models_used = sorted(str(m) for m in raw_models_used if isinstance(m, str))
        else:
            raw_models_used = getattr(raw_response, "models_used", None)
            if isinstance(raw_models_used, set):
                models_used = sorted(str(m) for m in raw_models_used if isinstance(m, str))
            elif isinstance(raw_models_used, list):
                models_used = sorted(str(m) for m in raw_models_used if isinstance(m, str))

        return {
            "answer": answer,
            "reasoning": reasoning,
            "full_response": result.content.strip() if _is_agent_sdk_model(model) else None,
            "tool_calls": tool_calls,
            "budgeted_tool_calls_used": budgeted_tool_calls_used,
            "rejected_missing_reasoning_calls": rejected_missing_reasoning_calls,
            "control_loop_suppressed_calls": control_loop_suppressed_calls,
            "tool_contract_rejections": tool_contract_rejections,
            "available_artifacts_final": available_artifacts_final,
            "tool_contract_violation_events": tool_contract_violation_events,
            "artifact_timeline": artifact_timeline,
            "available_capabilities_final": available_capabilities_final,
            "primary_failure_class": primary_failure_class,
            "secondary_failure_classes": secondary_failure_classes,
            "first_terminal_failure_event_code": first_terminal_failure_event_code,
            "failure_event_codes": failure_event_codes,
            "failure_event_code_counts": failure_event_code_counts,
            "no_legal_noncontrol_turns": no_legal_noncontrol_turns,
            "retrieval_no_hits_count": retrieval_no_hits_count,
            "submit_validation_reason_counts": submit_validation_reason_counts,
            "hard_bindings_hash": hard_bindings_hash,
            "full_bindings_hash": full_bindings_hash,
            "run_config_hash": run_config_hash,
            "lane_closure_analysis": lane_closure_analysis,
            "lane_policy": lane_policy,
            "tool_disclosure_repair_suggestions": tool_disclosure_repair_suggestions,
            "deficit_no_progress_streak_max": deficit_no_progress_streak_max,
            "deficit_no_progress_nudges": deficit_no_progress_nudges,
            "finalization_fallback_used": finalization_fallback_used,
            "finalization_fallback_succeeded": finalization_fallback_succeeded,
            "finalization_events": finalization_events,
            "forced_final_attempts": forced_final_attempts,
            "forced_final_circuit_breaker_opened": forced_final_circuit_breaker_opened,
            "retrieval_stagnation_triggered": retrieval_stagnation_triggered,
            "retrieval_stagnation_turn": retrieval_stagnation_turn,
            "retrieval_stagnation_streak_max": retrieval_stagnation_streak_max,
            "evidence_digest_change_count": evidence_digest_change_count,
            "evidence_turns_total": evidence_turns_total,
            "evidence_turns_with_new_evidence": evidence_turns_with_new_evidence,
            "evidence_turns_without_new_evidence": evidence_turns_without_new_evidence,
            "evidence_pointer_count": evidence_pointer_count,
            "evidence_digest_basis": evidence_digest_basis,
            "context_tool_result_clearings": context_tool_result_clearings,
            "context_tool_results_cleared": context_tool_results_cleared,
            "context_tool_result_cleared_chars": context_tool_result_cleared_chars,
            "requires_submit_answer": requires_submit_answer,
            "submit_answer_call_count": submit_answer_call_count,
            "submit_answer_attempted": submit_answer_attempted,
            "submit_answer_succeeded": submit_answer_succeeded,
            "submit_validator_accepted": submit_validator_accepted,
            "required_submit_missing": required_submit_missing,
            "submit_forced_retry_on_budget_exhaustion": submit_forced_retry_on_budget_exhaustion,
            "submit_forced_accept_on_budget_exhaustion": submit_forced_accept_on_budget_exhaustion,
            "submit_completion_mode": submit_completion_mode,
            "tool_arg_coercions": tool_arg_coercions,
            "tool_arg_coercion_calls": tool_arg_coercion_calls,
            "tool_arg_validation_rejections": tool_arg_validation_rejections,
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
        turn_timeout_label = "off" if effective_turn_timeout <= 0 else f"{effective_turn_timeout}s"
        timeout_error = (
            f"TIMEOUT after {round(elapsed, 2)}s "
            f"(question_timeout={'off' if question_timeout <= 0 else f'{question_timeout}s'}, "
            f"turn_timeout={turn_timeout_label})"
        )
        primary_failure_class, terminal_event_code, event_counts = _classify_run_error(timeout_error)
        failure_event_codes = [terminal_event_code] if terminal_event_code else ["QUESTION_TIMEOUT"]
        return {
            "answer": "",
            "tool_calls": [],
            "usage": {},
            "cost": 0.0,
            "latency_s": round(elapsed, 2),
            "error": timeout_error,
            "primary_failure_class": primary_failure_class or "runtime",
            "secondary_failure_classes": [],
            "first_terminal_failure_event_code": terminal_event_code or "QUESTION_TIMEOUT",
            "failure_event_codes": failure_event_codes,
            "failure_event_code_counts": event_counts or {"QUESTION_TIMEOUT": 1},
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        error_text = str(e)
        primary_failure_class, terminal_event_code, event_counts = _classify_run_error(error_text)
        failure_event_codes = [terminal_event_code] if terminal_event_code else []
        return {
            "answer": "",
            "tool_calls": [],
            "usage": {},
            "cost": 0.0,
            "latency_s": round(elapsed, 2),
            "error": error_text,
            "primary_failure_class": primary_failure_class or "none",
            "secondary_failure_classes": [],
            "first_terminal_failure_event_code": terminal_event_code,
            "failure_event_codes": failure_event_codes,
            "failure_event_code_counts": event_counts,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Agent-driven benchmark (any model via llm_client)")
    parser.add_argument("--dataset", required=True, help="Dataset name (e.g. HotpotQAsmallest)")
    parser.add_argument("--start", type=int, default=0, help="Start from question index (0-based)")
    parser.add_argument("--num", type=int, default=None, help="Number of questions to run")
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Hard timeout per question in seconds (0 disables; default: 0).",
    )
    parser.add_argument("--turn-timeout", type=int, default=0,
                        help="Per-LLM-call timeout in seconds within a question (0 disables; default: 0).")
    parser.add_argument("--resume", action="store_true", help="Resume from previous run")
    parser.add_argument("--model", default="codex", help="Agent model (default: codex). Any litellm model string works.")
    parser.add_argument("--effort", default="medium", help="Reasoning effort (Codex only): minimal/low/medium/high")
    parser.add_argument(
        "--codex-profile",
        default="compact",
        choices=["default", "compact"],
        help="Codex benchmark profile. 'compact' uses lighter prompt + MCP tool surface (benchmark mode 2).",
    )
    parser.add_argument("--max-tool-calls", type=int, default=20,
                        help="Tool-call budget per question (non-agent models only).")
    parser.add_argument("--max-turns", type=int, default=80, help=argparse.SUPPRESS)
    parser.add_argument("--data-root", default="./Data", help="Data root directory")
    parser.add_argument("--mode", default=CANONICAL_MODE, choices=["fixed", "adaptive", "aot", "hybrid", "baseline", "fixed_graph"],
                        help="Prompt mode. 'hybrid' is canonical. 'baseline' uses no graph tools. 'fixed_graph' uses deterministic graph pipeline.")
    parser.add_argument("--condition", type=str, default=None,
                        help="Condition ID for experiment tracking (e.g. 'multi_query_v1', 'baseline'). Enables cohort comparison.")
    parser.add_argument("--question-delay", type=float, default=2.0,
                        help="Seconds to wait between questions to avoid rate limiting (default: 2.0).")
    parser.add_argument("--tag", type=str, default=None,
                        help="Free-form tag for this run (stored in provenance, queryable).")
    parser.add_argument("--questions", type=str, default=None,
                        help="Comma-separated question IDs to run (e.g. 'q1,q4,q7')")
    parser.add_argument("--questions-file", type=str, default=None,
                        help="Path to newline-separated question IDs to run.")
    parser.add_argument("--only-failures-from", type=str, default=None,
                        help="Path to a prior benchmark JSON; run only IDs that failed.")
    parser.add_argument("--failure-metric", type=str, default="llm_em",
                        choices=["llm_em", "em", "f1"],
                        help="Metric used to define failures for --only-failures-from (default: llm_em).")
    parser.add_argument("--failure-threshold", type=float, default=None,
                        help="Failure threshold for metric (< threshold => fail). "
                             "Defaults: llm_em/em=0.5, f1=0.999999.")
    parser.add_argument("--write-failing-ids", type=str, default=None,
                        help="Write failing IDs from this run to a file (one ID per line).")
    parser.add_argument("--write-selected-ids", type=str, default=None,
                        help="Write the final selected question IDs to a file (one ID per line).")
    parser.add_argument("--sample-seed", type=int, default=None,
                        help="Deterministically sample questions instead of taking the first N after --start.")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Number of concurrent questions (each gets its own MCP server). Default: 1 (sequential)")
    parser.add_argument("--backend", default="mcp", choices=["mcp", "direct"],
                        help="Tool backend: 'mcp' (subprocess, default) or 'direct' (in-process Python tools)")
    parser.add_argument("--judge-model", default="openrouter/deepseek/deepseek-chat",
                        help="LLM judge model for format-agnostic scoring (default: openrouter/deepseek/deepseek-chat). Set to 'none' to disable.")
    parser.add_argument("--lane-policy", default="pure", choices=["pure", "reliability"],
                        help="Execution lane policy: pure (strict attribution) or reliability (completion-first finalization rescue).")
    parser.add_argument("--fallback-models", default="",
                        help="Comma-separated fallback models if primary fails. "
                             "Default: provider-aware auto chain with primary de-duplicated. "
                             "Set to 'none' to disable.")
    parser.add_argument("--finalization-fallback-models", default="",
                        help="Comma-separated forced-final fallback models (no tools allowed). "
                             "Default: none for pure lane; first two fallback models for reliability lane. "
                             "Set to 'none' to disable.")
    parser.add_argument("--forced-final-max-attempts", type=int, default=0,
                        help="Max forced-final attempts across primary + finalization fallbacks (0=lane default).")
    parser.add_argument("--forced-final-circuit-breaker-threshold", type=int, default=2,
                        help="Open forced-final circuit breaker after this many consecutive forced-final failures.")
    parser.add_argument("--retrieval-stagnation-turns", type=int, default=4,
                        help="Consecutive evidence turns with no new evidence before stagnation action triggers.")
    parser.add_argument(
        "--stagnation-action",
        type=str,
        default="force_final",
        choices=["force_final", "observe"],
        help="When retrieval stagnates: force final answer or only log/continue (default: force_final).",
    )
    parser.add_argument("--num-retries", type=int, default=2,
                        help="Number of retries per LLM call with exponential backoff (default: 2). Set higher for flaky models.")
    parser.add_argument(
        "--suppress-control-loop-calls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Suppress repeated invalid submit/todo control calls until evidence or TODO state changes "
            "(default: true)."
        ),
    )
    parser.add_argument(
        "--force-submit-retry-on-max-tool-calls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When tool budget is exhausted, count a forced submit retry attempt for observability "
            "(default: true)."
        ),
    )
    parser.add_argument(
        "--accept-forced-answer-on-max-tool-calls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When tool budget is exhausted, accept forced-final plain answer even if submit "
            "validation cannot be satisfied (default: true)."
        ),
    )
    parser.add_argument(
        "--fail-on-fallback-use",
        action="store_true",
        help=(
            "Exit with code 2 if any model fallback (primary->fallback) or finalization fallback is used."
        ),
    )
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="Sampling temperature for non-SDK tool-calling runs (default: 0.0).")
    parser.add_argument("--embed-model", type=str, default="",
                        help="Optional embedding model override for DIGIMON tools (e.g. gemini/gemini-embedding-001).")
    parser.add_argument("--embed-dimensions", type=int, default=None,
                        help="Optional embedding dimensions override (must match chosen embed model).")
    parser.add_argument("--disable-embedding-tools", action="store_true",
                        help="Disable embedding-based retrieval tools (entity_vdb_search/chunk_vdb_search).")
    parser.add_argument(
        "--agent-spec",
        type=str,
        default=str(Path(__file__).parent.parent / "specs" / "agent_spec.benchmark.yaml"),
        help="AgentSpec path (required for benchmark/eval runs unless explicitly opted out). Use 'none' with --allow-missing-agent-spec to bypass.",
    )
    parser.add_argument(
        "--allow-missing-agent-spec",
        action="store_true",
        help="Explicitly opt out of AgentSpec requirement. Must provide --missing-agent-spec-reason.",
    )
    parser.add_argument(
        "--missing-agent-spec-reason",
        type=str,
        default="",
        help="Required justification when --allow-missing-agent-spec is set.",
    )
    parser.add_argument("--verbose", action="store_true",
                        help="Show full DIGIMON debug logs on stderr. Default: quiet (WARNING+ only on stderr, DEBUG in log file).")
    parser.add_argument(
        "--heartbeat-secs",
        type=int,
        default=20,
        help="Emit per-question progress heartbeat every N seconds (0 disables).",
    )
    parser.add_argument(
        "--post-det-checks",
        type=str,
        default="default",
        help="Post-run deterministic checks over logged items: none|default|comma-separated names.",
    )
    parser.add_argument(
        "--post-review-rubric",
        type=str,
        default="",
        help="Optional post-run LLM review rubric name/path (e.g. extraction_quality).",
    )
    parser.add_argument(
        "--post-review-model",
        type=str,
        default="",
        help="Optional judge model override for --post-review-rubric.",
    )
    parser.add_argument(
        "--post-review-max-items",
        type=int,
        default=0,
        help="Max items to review in post-run rubric scoring (0=all).",
    )
    parser.add_argument(
        "--post-gate-policy",
        type=str,
        default="",
        help="Optional gate policy JSON or @path evaluated after run completion. "
             "If omitted, dataset defaults may apply (MuSiQue).",
    )
    parser.add_argument(
        "--post-gate-fail-exit-code",
        action="store_true",
        help="Exit with code 2 when post-run gate policy evaluates to FAIL.",
    )
    args = parser.parse_args()
    _install_event_loop_exception_filter()
    _install_asyncio_log_filter()
    requested_model = (args.model or "").strip()
    requested_judge_model = (args.judge_model or "").strip()
    requested_mode = args.mode
    effective_mode, was_aliased = _resolve_mode(requested_mode)
    args.mode = effective_mode
    args.model = _normalize_primary_model_for_benchmark(requested_model)
    effective_codex_profile = _resolve_codex_profile(args.model, args.codex_profile)
    if args.model != requested_model:
        print(
            f"Routing primary model via OpenRouter: {requested_model} -> {args.model}",
            file=sys.stderr,
        )
    if _is_codex_model(args.model) and effective_codex_profile != (args.codex_profile or "").strip().lower():
        print(
            f"WARNING: --codex-profile {args.codex_profile!r} unsupported; using {effective_codex_profile!r}.",
            file=sys.stderr,
        )
    if (not _is_codex_model(args.model)) and (args.codex_profile != "default"):
        print(
            "INFO: --codex-profile is ignored for non-codex models.",
            file=sys.stderr,
        )
    if _is_codex_model(args.model) and effective_codex_profile == "compact":
        # Profile-level defaults tuned for Codex SDK benchmark stability.
        if args.num_retries == 2:
            args.num_retries = 0
            print(
                "Codex compact profile: auto-adjusting --num-retries 2 -> 0 to avoid timeout multiplication.",
                file=sys.stderr,
            )
        if args.timeout > 0 and args.turn_timeout > 0 and args.timeout <= args.turn_timeout:
            print(
                "WARNING: question timeout is <= turn timeout in codex compact profile; "
                "question may terminate before meaningful progress.",
                file=sys.stderr,
            )
    if requested_judge_model and requested_judge_model.lower() != "none":
        args.judge_model = _normalize_primary_model_for_benchmark(requested_judge_model)
        if args.judge_model != requested_judge_model:
            print(
                f"Routing judge model via OpenRouter: {requested_judge_model} -> {args.judge_model}",
                file=sys.stderr,
            )
    if not _is_disabled_token(args.post_review_model):
        requested_post_review_model = (args.post_review_model or "").strip()
        normalized_post_review_model = _normalize_primary_model_for_benchmark(requested_post_review_model)
        if normalized_post_review_model != requested_post_review_model:
            print(
                f"Routing post-review model via OpenRouter: "
                f"{requested_post_review_model} -> {normalized_post_review_model}",
                file=sys.stderr,
            )
        args.post_review_model = normalized_post_review_model

    effective_embed_model = _resolve_embed_model_for_benchmark(
        explicit_embed_model=(args.embed_model or ""),
        disable_embedding_tools=bool(args.disable_embedding_tools),
        primary_model=args.model,
    )
    if was_aliased:
        print(
            f"WARNING: --mode {requested_mode!r} is a legacy alias; using canonical mode '{effective_mode}'.",
            file=sys.stderr,
        )
    if args.allow_missing_agent_spec and not (args.missing_agent_spec_reason or "").strip():
        print(
            "ERROR: --allow-missing-agent-spec requires --missing-agent-spec-reason "
            "with an explicit justification.",
            file=sys.stderr,
        )
        sys.exit(1)
    agent_spec_arg = (args.agent_spec or "").strip()
    agent_spec_value: Path | None
    if agent_spec_arg.lower() in {"", "none", "off"}:
        agent_spec_value = None
    else:
        agent_spec_value = Path(agent_spec_arg).expanduser()

    # Suppress DIGIMON internal logging on stderr unless --verbose
    if not args.verbose:
        os.environ["DIGIMON_LOG_LEVEL"] = "WARNING"

    # Rebuild MCP servers with correct benchmark mode + dataset pre-loading
    global DIGIMON_MCP_SERVERS, DIRECT_TOOLS
    benchmark_mode = 2 if (_is_codex_model(args.model) and effective_codex_profile == "compact") else 1
    DIGIMON_MCP_SERVERS = _build_mcp_servers(
        benchmark_mode,
        dataset_name=args.dataset,
        embed_model=effective_embed_model,
        embed_dimensions=args.embed_dimensions,
        disable_embedding_tools=args.disable_embedding_tools,
    )

    # Validate backend choice
    if args.backend == "direct" and _is_agent_sdk_model(args.model):
        print("ERROR: --backend direct is only for litellm models (not agent SDKs like codex/claude-code)")
        sys.exit(1)

    dataset_path = Path(args.data_root) / args.dataset
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found at {dataset_path}")
        sys.exit(1)

    all_questions = load_questions(str(dataset_path))
    selected_ids: set[str] | None = None

    if args.only_failures_from:
        failure_path = Path(args.only_failures_from)
        if not failure_path.exists():
            print(f"ERROR: --only-failures-from file not found: {failure_path}")
            sys.exit(1)
        selected_ids = _load_failing_ids_from_results_file(
            failure_path,
            metric=args.failure_metric,
            threshold=args.failure_threshold,
        )
        resolved_threshold = _resolve_failure_threshold(args.failure_metric, args.failure_threshold)
        print(
            f"Loaded {len(selected_ids)} failing IDs from {failure_path} "
            f"(metric={args.failure_metric}, threshold={resolved_threshold})"
        )

    if args.questions:
        requested_ids = {qid.strip() for qid in args.questions.split(",") if qid.strip()}
        selected_ids = requested_ids if selected_ids is None else (selected_ids & requested_ids)
        print(f"Question ID filter active: {len(selected_ids)} IDs")

    if args.questions_file:
        file_ids = load_question_ids_file(args.questions_file)
        file_id_set = set(file_ids)
        selected_ids = file_id_set if selected_ids is None else (selected_ids & file_id_set)
        print(f"Question file filter active: {len(selected_ids)} IDs from {args.questions_file}")

    if selected_ids is not None:
        known_ids = {q.get("id") for q in all_questions if q.get("id")}
        missing_ids = sorted([qid for qid in selected_ids if qid not in known_ids])
        if missing_ids:
            preview = ", ".join(missing_ids[:8])
            extra = f" (+{len(missing_ids)-8} more)" if len(missing_ids) > 8 else ""
            print(f"WARNING: {len(missing_ids)} selected IDs not found in dataset: {preview}{extra}")
        questions = [q for q in all_questions if q.get("id") in selected_ids]
        print(f"Loaded {len(questions)} selected questions from {args.dataset}")
    else:
        candidate_questions = all_questions[args.start:]
        if args.sample_seed is not None:
            rng = random.Random(args.sample_seed)
            if args.num is not None:
                sample_size = min(args.num, len(candidate_questions))
                questions = rng.sample(candidate_questions, sample_size)
            else:
                questions = candidate_questions[:]
                rng.shuffle(questions)
            print(
                f"Loaded {len(questions)} sampled questions from {args.dataset} "
                f"(start={args.start}, num={args.num}, sample_seed={args.sample_seed})"
            )
        else:
            questions = candidate_questions
            if args.num is not None:
                questions = questions[:args.num]
            print(f"Loaded {len(questions)} questions from {args.dataset} (start={args.start}, num={args.num})")

    if not questions:
        print("No questions selected; exiting.")
        return

    if args.write_selected_ids:
        selected_question_ids = [str(q.get("id")) for q in questions if q.get("id")]
        _write_selected_question_ids(Path(args.write_selected_ids), selected_question_ids)
        print(f"Wrote {len(selected_question_ids)} selected question IDs to {args.write_selected_ids}")

    post_gate_policy_effective, post_gate_policy_source = _resolve_post_gate_policy(
        args.dataset,
        args.post_gate_policy,
    )

    # Initialize direct backend only after question selection resolves.
    if args.backend == "direct":
        # Pass mode name to tool init for mode-based filtering
        os.environ["DIGIMON_BENCHMARK_MODE_NAME"] = args.mode
        if effective_embed_model:
            os.environ["DIGIMON_EMBED_MODEL"] = effective_embed_model
        if isinstance(args.embed_dimensions, int) and args.embed_dimensions > 0:
            os.environ["DIGIMON_EMBED_DIMENSIONS"] = str(args.embed_dimensions)
        DIRECT_TOOLS = await _init_direct_tools(
            args.dataset,
            disable_embedding_tools=args.disable_embedding_tools,
        )

    run_provenance = _build_run_provenance(
        dataset_path=dataset_path,
        questions=questions,
        mode=args.mode,
        prompt_variant=("codex_compact" if (_is_codex_model(args.model) and effective_codex_profile == "compact") else "default"),
    )
    run_provenance["condition_id"] = getattr(args, "condition", None) or args.mode
    run_provenance["tag"] = getattr(args, "tag", None)
    run_provenance["codex_profile"] = effective_codex_profile if _is_codex_model(args.model) else None
    run_provenance["digimon_benchmark_mode"] = benchmark_mode
    run_provenance["post_run_eval_config"] = {
        "det_checks": args.post_det_checks,
        "review_rubric": None if _is_disabled_token(args.post_review_rubric) else (args.post_review_rubric or "").strip(),
        "review_model": None if _is_disabled_token(args.post_review_model) else (args.post_review_model or "").strip(),
        "review_max_items": args.post_review_max_items,
        "gate_policy": post_gate_policy_effective or None,
        "gate_policy_source": post_gate_policy_source,
        "gate_fail_exit_code": bool(args.post_gate_fail_exit_code),
    }
    run_provenance["agent_spec_path"] = str(agent_spec_value) if agent_spec_value is not None else None
    run_provenance["allow_missing_agent_spec"] = bool(args.allow_missing_agent_spec)
    if args.allow_missing_agent_spec:
        run_provenance["missing_agent_spec_reason"] = (args.missing_agent_spec_reason or "").strip() or None

    # Output files — include model slug + timestamp so runs never overwrite
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = _model_slug(args.model)
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    mode_tag = f"_{args.mode}" if args.mode != CANONICAL_MODE else ""
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
    fallback_models = _resolve_fallback_models_for_benchmark(
        model=args.model,
        fallback_models_arg=(args.fallback_models or ""),
        lane_policy=args.lane_policy,
    )
    finalization_fallback_models = _resolve_finalization_fallback_models_for_benchmark(
        model=args.model,
        lane_policy=args.lane_policy,
        fallback_models=fallback_models,
        finalization_fallback_models_arg=(args.finalization_fallback_models or ""),
    )
    forced_final_max_attempts = int(args.forced_final_max_attempts or 0)
    if forced_final_max_attempts <= 0:
        if finalization_fallback_models:
            forced_final_max_attempts = 1 + len(finalization_fallback_models)
        else:
            forced_final_max_attempts = 1
    forced_final_circuit_breaker_threshold_requested = max(
        1,
        int(args.forced_final_circuit_breaker_threshold),
    )
    forced_final_circuit_breaker_threshold = min(
        forced_final_circuit_breaker_threshold_requested,
        forced_final_max_attempts,
    )
    if forced_final_circuit_breaker_threshold != forced_final_circuit_breaker_threshold_requested:
        print(
            "Adjusting forced-final circuit breaker threshold "
            f"{forced_final_circuit_breaker_threshold_requested} -> "
            f"{forced_final_circuit_breaker_threshold} to keep breaker effective.",
            file=sys.stderr,
        )
    retrieval_stagnation_turns = max(2, int(args.retrieval_stagnation_turns))
    retrieval_stagnation_action = str(args.stagnation_action).strip().lower()
    run_provenance["lane_policy"] = args.lane_policy
    run_provenance["fallback_models"] = fallback_models
    run_provenance["finalization_fallback_models"] = finalization_fallback_models
    run_provenance["forced_final_max_attempts"] = forced_final_max_attempts
    run_provenance["forced_final_circuit_breaker_threshold_requested"] = (
        forced_final_circuit_breaker_threshold_requested
    )
    run_provenance["forced_final_circuit_breaker_threshold"] = forced_final_circuit_breaker_threshold
    run_provenance["retrieval_stagnation_turns"] = retrieval_stagnation_turns
    run_provenance["retrieval_stagnation_action"] = retrieval_stagnation_action
    run_provenance["suppress_control_loop_calls"] = bool(args.suppress_control_loop_calls)
    run_provenance["force_submit_retry_on_max_tool_calls"] = bool(args.force_submit_retry_on_max_tool_calls)
    run_provenance["accept_forced_answer_on_max_tool_calls"] = bool(args.accept_forced_answer_on_max_tool_calls)
    run_provenance["fail_on_fallback_use"] = bool(args.fail_on_fallback_use)
    run_provenance["question_timeout"] = args.timeout
    run_provenance["question_timeout_enabled"] = bool(args.timeout > 0)
    run_provenance["turn_timeout"] = args.turn_timeout
    run_provenance["turn_timeout_enabled"] = bool(args.turn_timeout > 0)
    total_llm_em: int | None = None
    n_done = len(results)
    feature_profile = {
        "name": "benchmark_strict",
        "features": {
            "experiment_context": True,
            "provenance": True,
            "tool_reasoning": True,
        },
    }

    for r in results:
        total_em += r["em"]
        total_f1 += r["f1"]
        total_cost += r.get("cost", 0.0)
        if judge_model and r.get("llm_em") is not None:
            if total_llm_em is None:
                total_llm_em = 0
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
    question_timeout_label = "off" if args.timeout <= 0 else f"{args.timeout}s"
    turn_timeout_label = "off" if args.turn_timeout <= 0 else f"{args.turn_timeout}s"
    print(
        f"Model: {args.model} ({backend}, "
        f"question_timeout={question_timeout_label}, turn_timeout={turn_timeout_label})"
    )
    if _is_codex_model(args.model):
        print(f"Codex profile: {effective_codex_profile} (benchmark_mode={benchmark_mode})")
    if requested_model and requested_model != args.model:
        print(f"Requested model: {requested_model}")
    print(f"Mode: {args.mode}" + (f" (requested: {requested_mode})" if requested_mode != args.mode else ""))
    if args.backend != "mcp" or not _is_agent_sdk_model(args.model):
        print(f"Temperature: {args.temperature}")
    print(f"Lane policy: {args.lane_policy}")
    print(f"Fallback models: {fallback_models if fallback_models else 'none'}")
    print(
        "Forced-final fallback models: "
        f"{finalization_fallback_models if finalization_fallback_models else 'none'} "
        f"(max_attempts={forced_final_max_attempts}, breaker={forced_final_circuit_breaker_threshold})"
    )
    print(
        "Retrieval stagnation policy: "
        f"{retrieval_stagnation_turns} consecutive evidence turns -> {retrieval_stagnation_action}"
    )
    print(f"Suppress control-loop calls: {bool(args.suppress_control_loop_calls)}")
    print(
        "Budget-exhaustion submit policy: "
        f"retry={bool(args.force_submit_retry_on_max_tool_calls)}, "
        f"accept_forced_answer={bool(args.accept_forced_answer_on_max_tool_calls)}"
    )
    print(f"Fail on fallback use: {bool(args.fail_on_fallback_use)}")
    if effective_embed_model:
        print(f"Embedding model override: {effective_embed_model}")
    print(f"Post-run deterministic checks: {args.post_det_checks}")
    if not _is_disabled_token(args.post_review_rubric):
        print(
            "Post-run review: "
            f"rubric={args.post_review_rubric} "
            f"model={(args.post_review_model or 'default')} "
            f"max_items={(args.post_review_max_items if args.post_review_max_items > 0 else 'all')}"
        )
    if post_gate_policy_effective:
        gate_policy_label = (
            "dataset default"
            if post_gate_policy_source == "dataset_default"
            else "explicit"
        )
        print(
            "Post-run gate policy: "
            f"{post_gate_policy_effective[:120]}"
            f"{'...' if len(post_gate_policy_effective) > 120 else ''}"
            f" ({gate_policy_label})"
        )
    if not _is_agent_sdk_model(args.model):
        print(f"Tool-call budget (retrieval only; submit_answer exempt): {args.max_tool_calls}")
    print(f"Progress heartbeat: {'off' if args.heartbeat_secs <= 0 else f'every {args.heartbeat_secs}s'}")

    parallel = max(1, args.parallel)
    if parallel > 1 and _is_agent_sdk_model(args.model):
        print(f"WARNING: --parallel ignored for agent SDK models (each spawns its own servers)")
        parallel = 1

    print(f"\n{'='*70}")
    print(f"AGENT BENCHMARK: {args.dataset} ({len(questions)} questions, parallel={parallel})")
    print(f"{'='*70}\n")

    # Register experiment run in llm_client observability
    _experiment_run_id = llm_start_run(
        dataset=args.dataset,
        model=args.model,
        task="digimon.benchmark",
        config={
            "backend": args.backend,
            "mode": args.mode,
            "requested_mode": requested_mode,
            "tool_mode_boundaries": _TOOL_MODE_BOUNDARIES,
            "timeout": args.timeout,
            "question_timeout": args.timeout,
            "question_timeout_enabled": bool(args.timeout > 0),
            "turn_timeout": args.turn_timeout,
            "turn_timeout_enabled": bool(args.turn_timeout > 0),
            "max_tool_calls": args.max_tool_calls,
            "require_tool_reasoning": True,
            "max_turns_fuse": args.max_turns,
            "parallel": parallel, "judge_model": judge_model or None,
            "lane_policy": args.lane_policy,
            "fallback_models": fallback_models,
            "finalization_fallback_models": finalization_fallback_models,
            "num_retries": args.num_retries,
            "forced_final_max_attempts": forced_final_max_attempts,
            "forced_final_circuit_breaker_threshold": forced_final_circuit_breaker_threshold,
            "retrieval_stagnation_turns": retrieval_stagnation_turns,
            "retrieval_stagnation_action": retrieval_stagnation_action,
            "suppress_control_loop_calls": bool(args.suppress_control_loop_calls),
            "force_submit_retry_on_max_tool_calls": bool(args.force_submit_retry_on_max_tool_calls),
            "accept_forced_answer_on_max_tool_calls": bool(args.accept_forced_answer_on_max_tool_calls),
            "fail_on_fallback_use": bool(args.fail_on_fallback_use),
            "temperature": args.temperature,
            "heartbeat_secs": args.heartbeat_secs,
            "embed_model": (args.embed_model or "").strip() or None,
            "effective_embed_model": effective_embed_model or None,
            "embed_dimensions": args.embed_dimensions,
            "disable_embedding_tools": bool(args.disable_embedding_tools),
            "post_det_checks": args.post_det_checks,
            "post_review_rubric": None if _is_disabled_token(args.post_review_rubric) else (args.post_review_rubric or "").strip(),
            "post_review_model": None if _is_disabled_token(args.post_review_model) else (args.post_review_model or "").strip(),
            "post_review_max_items": args.post_review_max_items,
            "post_gate_policy": post_gate_policy_effective or None,
            "post_gate_policy_source": post_gate_policy_source,
            "post_gate_fail_exit_code": bool(args.post_gate_fail_exit_code),
        },
        provenance=run_provenance,
        feature_profile=feature_profile,
        agent_spec=agent_spec_value,
        allow_missing_agent_spec=bool(args.allow_missing_agent_spec),
        missing_agent_spec_reason=(args.missing_agent_spec_reason or "").strip() or None,
        condition_id=getattr(args, "condition", None) or args.mode,
        metrics_schema=["em", "f1", "llm_em"],
        project="Digimon_for_KG_application",
    )

    # --- Per-question processing (shared between sequential and parallel) ---

    # Lock protects running totals, results list, log_file, and incremental saves
    output_lock = asyncio.Lock()

    def _score_and_record(
        q: dict,
        agent_result: dict,
        llm_em_val: int | None = None,
        trace_id: str | None = None,
    ) -> dict:
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
        tool_mode_trace = _extract_tool_mode_trace(tool_calls)
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cached_tokens = usage.get("cached_tokens", 0)
        cache_read = usage.get("cached_tokens", 0)  # same field, kept for output compat
        cache_create = usage.get("cache_creation_tokens", 0)
        duration_ms = usage.get("duration_ms", 0)
        duration_api_ms = usage.get("duration_api_ms", 0)
        num_turns = usage.get("num_turns", 0)
        composability = _build_composability_diagnostics(
            tool_calls=tool_calls,
            tool_contract_rejections=agent_result.get("tool_contract_rejections"),
            rejected_missing_reasoning_calls=agent_result.get("rejected_missing_reasoning_calls"),
            control_loop_suppressed_calls=agent_result.get("control_loop_suppressed_calls"),
            tool_contract_violation_events=agent_result.get("tool_contract_violation_events"),
            available_artifacts_final=agent_result.get("available_artifacts_final"),
        )
        warnings_list = list(agent_result.get("warnings") or [])
        model_fallback_used = any(
            isinstance(w, str) and w.startswith("FALLBACK:")
            for w in warnings_list
        )
        fallback_used_any = bool(agent_result.get("finalization_fallback_used")) or model_fallback_used

        return {
            "id": q_id,
            "question": question,
            "gold": gold,
            "predicted": predicted,
            "trace_id": trace_id,
            "reasoning": reasoning,
            "full_response": agent_result.get("full_response"),
            "type": q_type,
            "em": em,
            "llm_em": llm_em_val,
            "f1": f1,
            "latency_s": elapsed,
            "cost": cost,
            "n_tool_calls": len(tool_calls),
            "n_tool_mode_boundary_calls": len(tool_mode_trace),
            "n_budgeted_tool_calls": agent_result.get("budgeted_tool_calls_used"),
            "n_rejected_missing_reasoning_calls": agent_result.get("rejected_missing_reasoning_calls"),
            "n_control_loop_suppressed_calls": agent_result.get("control_loop_suppressed_calls"),
            "n_tool_contract_rejections": agent_result.get("tool_contract_rejections"),
            "n_tool_arg_coercions": agent_result.get("tool_arg_coercions"),
            "n_tool_arg_coercion_calls": agent_result.get("tool_arg_coercion_calls"),
            "n_tool_arg_validation_rejections": agent_result.get("tool_arg_validation_rejections"),
            "n_tool_call_errors": composability.get("n_errors", 0),
            "n_tool_unavailable_errors": composability.get("error_categories", {}).get("tool_unavailable", 0),
            "n_tool_interface_mismatch_errors": composability.get("error_categories", {}).get("tool_interface_mismatch", 0),
            "n_tool_missing_prerequisite_errors": composability.get("error_categories", {}).get("missing_prerequisite", 0),
            "available_artifacts_final": agent_result.get("available_artifacts_final"),
            "available_capabilities_final": agent_result.get("available_capabilities_final"),
            "tool_contract_violation_events": agent_result.get("tool_contract_violation_events"),
            "artifact_timeline": agent_result.get("artifact_timeline"),
            "primary_failure_class": agent_result.get("primary_failure_class"),
            "secondary_failure_classes": agent_result.get("secondary_failure_classes"),
            "first_terminal_failure_event_code": agent_result.get("first_terminal_failure_event_code"),
            "failure_event_codes": agent_result.get("failure_event_codes"),
            "failure_event_code_counts": agent_result.get("failure_event_code_counts"),
            "no_legal_noncontrol_turns": agent_result.get("no_legal_noncontrol_turns"),
            "retrieval_no_hits_count": agent_result.get("retrieval_no_hits_count"),
            "submit_validation_reason_counts": agent_result.get("submit_validation_reason_counts"),
            "hard_bindings_hash": agent_result.get("hard_bindings_hash"),
            "full_bindings_hash": agent_result.get("full_bindings_hash"),
            "run_config_hash": agent_result.get("run_config_hash"),
            "lane_closure_analysis": agent_result.get("lane_closure_analysis"),
            "lane_policy": agent_result.get("lane_policy"),
            "tool_disclosure_repair_suggestions": agent_result.get("tool_disclosure_repair_suggestions"),
            "model_fallback_used": model_fallback_used,
            "fallback_used_any": fallback_used_any,
            "finalization_fallback_used": agent_result.get("finalization_fallback_used"),
            "finalization_fallback_succeeded": agent_result.get("finalization_fallback_succeeded"),
            "forced_final_attempts": agent_result.get("forced_final_attempts"),
            "forced_final_circuit_breaker_opened": agent_result.get("forced_final_circuit_breaker_opened"),
            "finalization_events": agent_result.get("finalization_events"),
            "retrieval_stagnation_triggered": agent_result.get("retrieval_stagnation_triggered"),
            "retrieval_stagnation_turn": agent_result.get("retrieval_stagnation_turn"),
            "retrieval_stagnation_streak_max": agent_result.get("retrieval_stagnation_streak_max"),
            "evidence_digest_change_count": agent_result.get("evidence_digest_change_count"),
            "evidence_turns_total": agent_result.get("evidence_turns_total"),
            "evidence_turns_with_new_evidence": agent_result.get("evidence_turns_with_new_evidence"),
            "evidence_turns_without_new_evidence": agent_result.get("evidence_turns_without_new_evidence"),
            "evidence_pointer_count": agent_result.get("evidence_pointer_count"),
            "evidence_digest_basis": agent_result.get("evidence_digest_basis"),
            "context_tool_result_clearings": agent_result.get("context_tool_result_clearings"),
            "context_tool_results_cleared": agent_result.get("context_tool_results_cleared"),
            "context_tool_result_cleared_chars": agent_result.get("context_tool_result_cleared_chars"),
            "requires_submit_answer": agent_result.get("requires_submit_answer"),
            "submit_answer_call_count": agent_result.get("submit_answer_call_count"),
            "submit_answer_attempted": agent_result.get("submit_answer_attempted"),
            "submit_answer_succeeded": agent_result.get("submit_answer_succeeded"),
            "submit_validator_accepted": agent_result.get("submit_validator_accepted"),
            "required_submit_missing": agent_result.get("required_submit_missing"),
            "submit_forced_retry_on_budget_exhaustion": agent_result.get("submit_forced_retry_on_budget_exhaustion"),
            "submit_forced_accept_on_budget_exhaustion": agent_result.get("submit_forced_accept_on_budget_exhaustion"),
            "submit_completion_mode": agent_result.get("submit_completion_mode"),
            "composability": composability,
            "tool_calls": tool_names,
            "tool_details": tool_calls,
            "tool_mode_trace": tool_mode_trace,
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
            "warnings": warnings_list,
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
        budgeted_calls = record.get("n_budgeted_tool_calls")
        rejected_reasoning = record.get("n_rejected_missing_reasoning_calls")
        contract_rejections = record.get("n_tool_contract_rejections")
        primary_failure_class = record.get("primary_failure_class")
        first_terminal = record.get("first_terminal_failure_event_code")
        submit_completion_mode = record.get("submit_completion_mode")
        fallback_used = bool(record.get("fallback_used_any"))
        finalization_fallback_used = bool(record.get("finalization_fallback_used"))
        fallback_succeeded = bool(record.get("finalization_fallback_succeeded"))
        retrieval_stagnation = bool(record.get("retrieval_stagnation_triggered"))
        if budgeted_calls is None:
            lines.append(f"  Tools: {record['n_tool_calls']} calls {record['tool_calls']}")
        else:
            suffix_parts: list[str] = []
            if isinstance(rejected_reasoning, int) and rejected_reasoning > 0:
                suffix_parts.append(f"{rejected_reasoning} rejected-missing-reasoning")
            if isinstance(contract_rejections, int) and contract_rejections > 0:
                suffix_parts.append(f"{contract_rejections} rejected-contract")
            if isinstance(primary_failure_class, str) and primary_failure_class and primary_failure_class != "none":
                suffix_parts.append(f"primary_failure={primary_failure_class}")
            if isinstance(first_terminal, str) and first_terminal:
                suffix_parts.append(f"first_terminal={first_terminal}")
            if (
                isinstance(submit_completion_mode, str)
                and submit_completion_mode
                and submit_completion_mode != "grounded_submit"
            ):
                suffix_parts.append(f"submit_mode={submit_completion_mode}")
            if fallback_used:
                if finalization_fallback_used:
                    suffix_parts.append(
                        "finalization_fallback="
                        + ("success" if fallback_succeeded else "used")
                    )
                else:
                    suffix_parts.append("model_fallback=used")
            if retrieval_stagnation:
                suffix_parts.append("retrieval_stagnation")
            suffix = ""
            if suffix_parts:
                suffix = ", " + ", ".join(suffix_parts)
            lines.append(
                f"  Tools: {record['n_tool_calls']} calls ({budgeted_calls} budgeted{suffix}) {record['tool_calls']}"
            )
        comp = record.get("composability") or {}
        if comp:
            cat = comp.get("error_categories") or {}
            lines.append(
                "  Composability: "
                f"status={comp.get('status', 'unknown')} "
                f"errors={comp.get('n_errors', 0)} "
                f"unavailable={cat.get('tool_unavailable', 0)} "
                f"interface={cat.get('tool_interface_mismatch', 0)} "
                f"prereq={cat.get('missing_prerequisite', 0)} "
                f"contract={comp.get('n_contract_rejections', 0)} "
                f"suppressed={comp.get('n_control_loop_suppressed', 0)}"
            )
            error_tools = comp.get("error_tools") or {}
            if error_tools:
                top_tools = ", ".join(f"{k}:{v}" for k, v in list(error_tools.items())[:5])
                lines.append(f"  ComposabilityTools: {top_tools}")
            unknown_tools = comp.get("unknown_tools") or []
            if unknown_tools:
                lines.append(f"  ComposabilityUnknownTools: {', '.join(unknown_tools)}")
        arg_coercions = int(record.get("n_tool_arg_coercions") or 0)
        arg_coercion_calls = int(record.get("n_tool_arg_coercion_calls") or 0)
        arg_validation_rejections = int(record.get("n_tool_arg_validation_rejections") or 0)
        if arg_coercions or arg_validation_rejections:
            lines.append(
                "  ToolArgs: "
                f"coercions={arg_coercions} across {arg_coercion_calls} calls, "
                f"validation_rejections={arg_validation_rejections}"
            )
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
        comp_errors = int(record.get("n_tool_call_errors") or 0)
        interface_errors = int(record.get("n_tool_interface_mismatch_errors") or 0)
        arg_validation_rejections = int(record.get("n_tool_arg_validation_rejections") or 0)
        comp = ""
        if comp_errors > 0:
            comp = f" C{comp_errors}"
            if interface_errors > 0:
                comp += f"/I{interface_errors}"
        if arg_validation_rejections > 0:
            comp += f" A{arg_validation_rejections}"
        if record.get("fallback_used_any"):
            comp += " Ff"
        if record.get("retrieval_stagnation_triggered"):
            comp += " Rs"
        running_em = 100 * total_em_now / n_done_now
        running_llm = f" LLM={100*total_llm_em_now/n_done_now:.0f}%" if total_llm_em_now is not None else ""
        return (f"[{n_done_now:3d}/{n_total}] {q_id:5s} {em_icon}{llm_em_icon} "
                f"F1={record['f1']:.2f} {record['n_tool_calls']:2d}t {record['latency_s']:5.1f}s "
                f"${record['cost']:.4f}{err}{warn}{comp}  "
                f"| EM={running_em:.1f}%{running_llm} ${total_cost_now:.2f}")

    async def _process_question(q: dict, session_pool: object) -> dict:
        """Run agent on one question, then score + log under lock."""
        nonlocal n_done, total_em, total_f1, total_cost, total_llm_em

        q_id = q.get("id", "unknown")
        q_hash = md5(q["question"].encode()).hexdigest()[:8]
        trace_id = f"digimon.benchmark.{args.dataset}.{q_id}.{q_hash}"
        started_at = time.monotonic()
        heartbeat_task: asyncio.Task[None] | None = None
        heartbeat_enabled = args.heartbeat_secs > 0 and parallel <= 1

        if heartbeat_enabled:
            print(f"START [{q_id}] trace={trace_id}", flush=True)

            async def _heartbeat() -> None:
                while True:
                    await asyncio.sleep(args.heartbeat_secs)
                    elapsed = time.monotonic() - started_at
                    print(
                        f"HEARTBEAT [{q_id}] running {elapsed:.1f}s "
                        f"(question_timeout={question_timeout_label}, turn_timeout={turn_timeout_label})",
                        flush=True,
                    )

            heartbeat_task = asyncio.create_task(_heartbeat())

        try:
            with llm_activate_feature_profile(feature_profile), llm_activate_experiment_run(_experiment_run_id):
                agent_result = await run_agent(
                    q["question"], args.dataset,
                    timeout=args.timeout,
                    turn_timeout=args.turn_timeout,
                    model=args.model,
                    reasoning_effort=args.effort,
                    max_turns=args.max_turns,
                    max_tool_calls=args.max_tool_calls,
                    mcp_session_pool=session_pool,
                    mode=args.mode,
                    backend=args.backend,
                    python_tools=DIRECT_TOOLS if args.backend == "direct" else None,
                    temperature=args.temperature,
                    fallback_models=fallback_models,
                    finalization_fallback_models=finalization_fallback_models,
                    num_retries=args.num_retries,
                    forced_final_max_attempts=forced_final_max_attempts,
                    forced_final_circuit_breaker_threshold=forced_final_circuit_breaker_threshold,
                    retrieval_stagnation_turns=retrieval_stagnation_turns,
                    retrieval_stagnation_action=retrieval_stagnation_action,
                    suppress_control_loop_calls=bool(args.suppress_control_loop_calls),
                    force_submit_retry_on_max_tool_calls=bool(args.force_submit_retry_on_max_tool_calls),
                    accept_forced_answer_on_max_tool_calls=bool(args.accept_forced_answer_on_max_tool_calls),
                    lane_policy=args.lane_policy,
                    trace_id=trace_id,
                    codex_profile=effective_codex_profile,
                )

                # LLM judge (runs before lock — it's an independent LLM call)
                llm_em_val: int | None = None
                if judge_model and agent_result["answer"]:
                    judged = await llm_judge(
                        q["question"], agent_result["answer"], q["answer"],
                        model=judge_model,
                    )
                    if judged is not None:
                        llm_em_val = int(judged)
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

        record = _score_and_record(q, agent_result, llm_em_val=llm_em_val, trace_id=trace_id)

        # Log to centralized experiment tracking (thread-safe, never raises)
        llm_log_item(
            run_id=_experiment_run_id, item_id=record["id"],
            metrics={"em": record["em"], "f1": record["f1"], "llm_em": record.get("llm_em")},
            predicted=record["predicted"], gold=record["gold"],
            latency_s=record["latency_s"], cost=record["cost"],
            n_tool_calls=record["n_tool_calls"], error=record.get("error"),
            trace_id=trace_id,
            extra={
                "tool_calls": record["tool_calls"],
                "tool_details": record.get("tool_details"),
                "conversation_trace": record.get("conversation_trace"),
                "composability": record.get("composability"),
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
            if llm_em_val is not None:
                if total_llm_em is None:
                    total_llm_em = 0
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
                          n_done, total_em, total_f1, total_cost, results,
                          run_provenance=run_provenance)

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
            question_delay = getattr(args, "question_delay", 2.0)
            for qi, q in enumerate(pending):
                if qi > 0 and question_delay > 0:
                    await asyncio.sleep(question_delay)
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

    # Finalize centralized experiment log (timing auto-captured by llm_client)
    run_status = "completed" if n_done == len(questions) else "interrupted"
    run_record = llm_finish_run(run_id=_experiment_run_id, status=run_status)
    post_run_eval: dict[str, object] = {}
    exit_code = 0

    # Final summary
    if n_done > 0:
        avg_tools = sum(r["n_tool_calls"] for r in results) / n_done
        avg_latency = sum(r["latency_s"] for r in results) / n_done
        total_input = sum(r.get("input_tokens", 0) for r in results)
        total_output = sum(r.get("output_tokens", 0) for r in results)
        n_errors = sum(1 for r in results if r.get("error"))
        n_completed_success = max(0, n_done - n_errors)
        completion_rate = (100.0 * n_completed_success / n_done) if n_done else 0.0
        provider_failures = sum(1 for r in results if (r.get("primary_failure_class") or "") == "provider")
        provider_failure_rate = (100.0 * provider_failures / n_done) if n_done else 0.0
        grounded_submit_count = sum(1 for r in results if bool(r.get("submit_validator_accepted")))
        forced_terminal_accept_count = sum(
            1 for r in results if bool(r.get("submit_forced_accept_on_budget_exhaustion"))
        )
        fallback_used_count = sum(1 for r in results if bool(r.get("fallback_used_any")))
        fallback_used_rate = (100.0 * fallback_used_count / n_done) if n_done else 0.0
        finalization_fallback_used_count = sum(1 for r in results if bool(r.get("finalization_fallback_used")))
        finalization_fallback_used_rate = (100.0 * finalization_fallback_used_count / n_done) if n_done else 0.0
        retrieval_stagnation_count = sum(1 for r in results if bool(r.get("retrieval_stagnation_triggered")))
        retrieval_stagnation_rate = (100.0 * retrieval_stagnation_count / n_done) if n_done else 0.0
        em_completed = (
            100.0 * sum(int(r.get("em") or 0) for r in results if not r.get("error")) / n_completed_success
            if n_completed_success else None
        )
        f1_completed = (
            100.0 * sum(float(r.get("f1") or 0.0) for r in results if not r.get("error")) / n_completed_success
            if n_completed_success else None
        )
        llm_completed_vals = [
            int(r.get("llm_em"))
            for r in results
            if (not r.get("error")) and r.get("llm_em") is not None
        ]
        llm_em_completed_judged = (
            100.0 * sum(llm_completed_vals) / len(llm_completed_vals)
            if llm_completed_vals else None
        )
        total_tool_call_errors = sum(int(r.get("n_tool_call_errors") or 0) for r in results)
        total_interface_errors = sum(int(r.get("n_tool_interface_mismatch_errors") or 0) for r in results)
        total_prereq_errors = sum(int(r.get("n_tool_missing_prerequisite_errors") or 0) for r in results)
        total_arg_coercions = sum(int(r.get("n_tool_arg_coercions") or 0) for r in results)
        total_arg_validation_rejections = sum(
            int(r.get("n_tool_arg_validation_rejections") or 0) for r in results
        )
        total_unavailable_errors = sum(
            int((r.get("composability") or {}).get("error_categories", {}).get("tool_unavailable", 0))
            for r in results
        )
        comp_affected_questions = sum(1 for r in results if int(r.get("n_tool_call_errors") or 0) > 0)

        print(f"\n{'='*70}")
        wall_time = float(run_record.get("wall_time_s") or 0.0)
        cpu_time = float(run_record.get("cpu_time_s") or 0.0)
        cpu_user = float(run_record.get("cpu_user_s") or 0.0)
        cpu_system = float(run_record.get("cpu_system_s") or 0.0)
        wall_per_q = (wall_time / n_done) if wall_time > 0 else 0.0
        cpu_wall = (cpu_time / wall_time) if wall_time > 0 else 0.0
        print(f"FINAL: {n_done}/{len(questions)} questions (parallel={parallel})")
        print(f"  EM:    {100*total_em/n_done:.1f}%")
        if total_llm_em is not None:
            print(f"  LLM_EM:{100*total_llm_em/n_done:.1f}%  (judge: {judge_model})")
        print(f"  F1:    {100*total_f1/n_done:.1f}%")
        print(f"  Cost:  ${total_cost:.2f}")
        print(
            f"  Completion: {completion_rate:.1f}% "
            f"({n_completed_success}/{n_done})"
        )
        if em_completed is not None:
            llm_conditional = (
                f", LLM_EM={llm_em_completed_judged:.1f}%"
                if llm_em_completed_judged is not None else ""
            )
            print(
                "  Conditional Accuracy (completed only): "
                f"EM={em_completed:.1f}%, F1={f1_completed:.1f}%{llm_conditional}"
            )
        print(
            f"  Provider failures: {provider_failures}/{n_done} ({provider_failure_rate:.1f}%)"
        )
        print(
            f"  Any fallback used: {fallback_used_count}/{n_done} ({fallback_used_rate:.1f}%)"
        )
        print(
            f"  Finalization fallback used: {finalization_fallback_used_count}/{n_done} "
            f"({finalization_fallback_used_rate:.1f}%)"
        )
        print(
            f"  Retrieval stagnation triggered: {retrieval_stagnation_count}/{n_done} ({retrieval_stagnation_rate:.1f}%)"
        )
        print(f"  Tools: {avg_tools:.1f} calls/question avg")
        print(
            f"  Composability: {total_tool_call_errors} tool-call errors "
            f"({total_unavailable_errors} unavailable, {total_interface_errors} interface, {total_prereq_errors} prereq) "
            f"across {comp_affected_questions}/{n_done} questions"
        )
        print(
            "  ToolArgs: "
            f"{total_arg_coercions} coercions, "
            f"{total_arg_validation_rejections} validation rejections"
        )
        print(f"  Wall:  {wall_time:.1f}s ({wall_per_q:.1f}s/q effective)")
        print(
            f"  CPU:   {cpu_time:.1f}s"
            f" (user={cpu_user:.1f}s, sys={cpu_system:.1f}s, cpu/wall={cpu_wall:.2f}x)"
        )

        # Post-run evaluation hooks (triage/checks/review/gates).
        run_items = llm_get_run_items(_experiment_run_id)
        if not run_items:
            run_items = [
                {
                    "item_id": r.get("id"),
                    "metrics": {
                        "em": r.get("em"),
                        "f1": r.get("f1"),
                        "llm_em": r.get("llm_em"),
                    },
                    "predicted": r.get("predicted"),
                    "gold": r.get("gold"),
                    "error": r.get("error"),
                    "trace_id": r.get("trace_id"),
                    "extra": {
                        "composability": r.get("composability"),
                        "warnings": r.get("warnings"),
                        "tool_calls": r.get("tool_calls"),
                    },
                }
                for r in results
            ]

        triage_report = triage_items(run_items)
        post_run_eval["triage"] = triage_report
        triage_counts = triage_report.get("category_counts") or {}
        triage_str = "  ".join(f"{k}={v}" for k, v in triage_counts.items())
        print(f"  PostEval Triage: {triage_str or '-'}")

        det_checks_raw = (args.post_det_checks or "").strip()
        deterministic_report = None
        if det_checks_raw.lower() not in {"", "none", "off", "0", "false"}:
            deterministic_report = run_deterministic_checks_for_items(
                run_items,
                checks=det_checks_raw,
            )
            post_run_eval["deterministic_checks"] = deterministic_report
            print(
                "  PostEval Checks: "
                f"pass_rate={deterministic_report.get('pass_rate')} "
                f"failed_items={deterministic_report.get('n_failed_items')}/"
                f"{deterministic_report.get('n_items')}"
            )

        review_report = None
        review_rubric = (args.post_review_rubric or "").strip()
        if not _is_disabled_token(review_rubric):
            review_report = review_items_with_rubric(
                run_items,
                rubric=review_rubric,
                judge_model=None if _is_disabled_token(args.post_review_model) else (args.post_review_model or "").strip() or None,
                task_prefix=f"digimon.benchmark.post_review.{_experiment_run_id}",
                max_items=args.post_review_max_items if args.post_review_max_items > 0 else None,
            )
            post_run_eval["review"] = review_report
            print(
                "  PostEval Review: "
                f"rubric={review_report.get('rubric')} "
                f"avg={review_report.get('avg_overall_score')} "
                f"scored={review_report.get('n_scored')}/"
                f"{review_report.get('n_items_considered')} "
                f"failed={review_report.get('n_failed')}"
            )

        gate_failed = False
        gate_policy_raw = (post_gate_policy_effective or "").strip()
        if gate_policy_raw:
            try:
                gate_policy = load_gate_policy(gate_policy_raw)
                gate_signals = build_gate_signals(
                    run_info=run_record,
                    items=run_items,
                    deterministic_report=deterministic_report,
                    review_report=review_report,
                )
                gate_result = evaluate_gate_policy(policy=gate_policy, signals=gate_signals)
                post_run_eval["gate_policy"] = gate_policy
                post_run_eval["gate_policy_source"] = post_gate_policy_source
                post_run_eval["gate_result"] = gate_result
                gate_failed = not bool(gate_result.get("passed", False))
                print(f"  PostEval Gate: {'PASS' if not gate_failed else 'FAIL'}")
            except Exception as exc:
                gate_failed = True
                post_run_eval["gate_policy_error"] = str(exc)
                print(f"  PostEval Gate: FAIL ({exc})")

        if gate_failed:
            run_status = "failed_gate"
            run_record = llm_finish_run(run_id=_experiment_run_id, status=run_status)
            if args.post_gate_fail_exit_code:
                exit_code = 2

        if args.fail_on_fallback_use and fallback_used_count > 0:
            post_run_eval["fallback_policy_failed"] = True
            post_run_eval["fallback_policy"] = {
                "fail_on_fallback_use": True,
                "n_any_fallback_used": fallback_used_count,
                "n_finalization_fallback_used": finalization_fallback_used_count,
            }
            print(
                "  Fallback Policy: FAIL "
                f"(any_fallback_used={fallback_used_count}/{n_done})"
            )
            run_status = "failed_fallback_policy"
            run_record = llm_finish_run(run_id=_experiment_run_id, status=run_status)
            exit_code = 2

        print(f"{'='*70}")
        print(f"Results saved to {output_path}")

        if args.write_failing_ids:
            failing_ids = sorted(
                _collect_failing_ids(
                    results,
                    metric=args.failure_metric,
                    threshold=args.failure_threshold,
                )
            )
            failing_path = Path(args.write_failing_ids)
            failing_path.parent.mkdir(parents=True, exist_ok=True)
            payload = "\n".join(failing_ids)
            if payload:
                payload += "\n"
            failing_path.write_text(payload)
            resolved_threshold = _resolve_failure_threshold(args.failure_metric, args.failure_threshold)
            print(
                f"Failing IDs written to {failing_path} "
                f"(count={len(failing_ids)}, metric={args.failure_metric}, threshold={resolved_threshold})"
            )

        # Persist post-run evaluation bundle into the benchmark JSON artifact.
        _save_results(
            output_path, args.dataset, args.model, len(questions),
            n_done, total_em, total_f1, total_cost, results,
            run_provenance=run_provenance,
            post_run_eval=post_run_eval,
        )

    print(f"Experiment logged to llm_client observability (run_id={_experiment_run_id})")

    # Best-effort async client/loop teardown to reduce noisy SSL transport
    # errors during asyncio.run() shutdown.
    import litellm
    with contextlib.suppress(Exception):
        await litellm.close_litellm_async_clients()
    with contextlib.suppress(Exception):
        await asyncio.sleep(0.05)
    with contextlib.suppress(Exception):
        loop = asyncio.get_running_loop()
        await loop.shutdown_asyncgens()
    with contextlib.suppress(Exception):
        await asyncio.sleep(0.2)
    if exit_code:
        raise SystemExit(exit_code)


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
    run_provenance: dict[str, object] | None = None,
    post_run_eval: dict[str, object] | None = None,
) -> None:
    """Save results JSON incrementally."""
    avg_tools = sum(r["n_tool_calls"] for r in results) / len(results) if results else 0
    avg_latency = sum(r["latency_s"] for r in results) / len(results) if results else 0
    total_input = sum(r.get("input_tokens", 0) for r in results)
    total_output = sum(r.get("output_tokens", 0) for r in results)
    comp_total_errors = sum(int(r.get("n_tool_call_errors") or 0) for r in results)
    comp_total_interface = sum(int(r.get("n_tool_interface_mismatch_errors") or 0) for r in results)
    comp_total_prereq = sum(int(r.get("n_tool_missing_prerequisite_errors") or 0) for r in results)
    comp_total_arg_coercions = sum(int(r.get("n_tool_arg_coercions") or 0) for r in results)
    comp_total_arg_validation_rejections = sum(
        int(r.get("n_tool_arg_validation_rejections") or 0) for r in results
    )
    comp_total_unavailable = sum(
        int((r.get("composability") or {}).get("error_categories", {}).get("tool_unavailable", 0))
        for r in results
    )
    comp_affected_questions = sum(1 for r in results if int(r.get("n_tool_call_errors") or 0) > 0)
    comp_top_question_ids = [
        r.get("id")
        for r in sorted(
            results,
            key=lambda rec: int(rec.get("n_tool_call_errors") or 0),
            reverse=True,
        )
        if int(r.get("n_tool_call_errors") or 0) > 0
    ][:10]

    # Compute LLM EM in two forms:
    # - avg_llm_em: across all completed questions (None treated as 0/fail)
    # - avg_llm_em_judged: across only judged rows (llm_em is 0/1)
    llm_em_judged = [int(r["llm_em"]) for r in results if r.get("llm_em") is not None]
    if llm_em_judged:
        llm_em_all = [int(r.get("llm_em") or 0) for r in results]
        avg_llm_em = (100 * sum(llm_em_all) / n_done) if n_done else None
        avg_llm_em_judged = 100 * sum(llm_em_judged) / len(llm_em_judged)
    else:
        avg_llm_em = None
        avg_llm_em_judged = None

    n_errors = sum(1 for r in results if r.get("error"))
    n_completed_success = max(0, n_done - n_errors)
    completion_rate = (100.0 * n_completed_success / n_done) if n_done else 0.0
    provider_failures = sum(1 for r in results if (r.get("primary_failure_class") or "") == "provider")
    provider_failure_rate = (100.0 * provider_failures / n_done) if n_done else 0.0
    grounded_submit_count = sum(1 for r in results if bool(r.get("submit_validator_accepted")))
    forced_terminal_accept_count = sum(
        1 for r in results if bool(r.get("submit_forced_accept_on_budget_exhaustion"))
    )
    fallback_used_any = sum(1 for r in results if bool(r.get("fallback_used_any")))
    fallback_used_any_rate = (100.0 * fallback_used_any / n_done) if n_done else 0.0
    finalization_fallback_used = sum(1 for r in results if bool(r.get("finalization_fallback_used")))
    finalization_fallback_usage_rate = (100.0 * finalization_fallback_used / n_done) if n_done else 0.0
    retrieval_stagnation_count = sum(1 for r in results if bool(r.get("retrieval_stagnation_triggered")))
    retrieval_stagnation_rate = (100.0 * retrieval_stagnation_count / n_done) if n_done else 0.0
    avg_em_completed = (
        100.0 * sum(int(r.get("em") or 0) for r in results if not r.get("error")) / n_completed_success
        if n_completed_success else None
    )
    avg_f1_completed = (
        100.0 * sum(float(r.get("f1") or 0.0) for r in results if not r.get("error")) / n_completed_success
        if n_completed_success else None
    )
    llm_completed_vals = [
        int(r.get("llm_em"))
        for r in results
        if (not r.get("error")) and r.get("llm_em") is not None
    ]
    avg_llm_em_completed_judged = (
        100.0 * sum(llm_completed_vals) / len(llm_completed_vals)
        if llm_completed_vals else None
    )

    with open(output_path, "w") as f:
        json.dump({
            "dataset": dataset,
            "model": model,
            "run_provenance": run_provenance or {},
            "n_questions": n_questions,
            "n_completed": n_done,
            "n_errors": n_errors,
            "completion_rate": completion_rate,
            "avg_em": 100 * total_em / n_done if n_done else 0,
            "avg_em_completed": avg_em_completed,
            "avg_llm_em": avg_llm_em,
            "avg_llm_em_judged": avg_llm_em_judged,
            "avg_llm_em_completed_judged": avg_llm_em_completed_judged,
            "n_llm_judged": len(llm_em_judged),
            "avg_f1": 100 * total_f1 / n_done if n_done else 0,
            "avg_f1_completed": avg_f1_completed,
            "n_provider_failures": provider_failures,
            "provider_failure_rate": provider_failure_rate,
            "n_grounded_submit_accepted": grounded_submit_count,
            "n_forced_terminal_accept": forced_terminal_accept_count,
            "n_fallback_used_any": fallback_used_any,
            "fallback_usage_rate_any": fallback_used_any_rate,
            "n_finalization_fallback_used": finalization_fallback_used,
            "finalization_fallback_usage_rate": finalization_fallback_usage_rate,
            "n_retrieval_stagnation": retrieval_stagnation_count,
            "retrieval_stagnation_rate": retrieval_stagnation_rate,
            "total_cost": round(total_cost, 4),
            "avg_tool_calls": round(avg_tools, 1),
            "avg_latency_s": round(avg_latency, 1),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "composability_summary": {
                "total_tool_call_errors": comp_total_errors,
                "total_unavailable_tool_errors": comp_total_unavailable,
                "total_interface_mismatch_errors": comp_total_interface,
                "total_missing_prerequisite_errors": comp_total_prereq,
                "total_tool_arg_coercions": comp_total_arg_coercions,
                "total_tool_arg_validation_rejections": comp_total_arg_validation_rejections,
                "questions_with_composability_errors": comp_affected_questions,
                "top_error_question_ids": comp_top_question_ids,
            },
            "post_run_eval": post_run_eval or {},
            "results": results,
        }, f, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
