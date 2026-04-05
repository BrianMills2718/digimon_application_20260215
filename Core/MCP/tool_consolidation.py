"""Consolidated tool surface for DIGIMON benchmark agents.

Reduces 46 MCP tools to 10 consolidated tools with method arguments.
Each consolidated tool dispatches to existing operator implementations.
No operator code is changed — this is a thin adapter layer.

Usage:
    Set DIGIMON_CONSOLIDATED_TOOLS=1 to expose consolidated tools
    instead of individual operator tools in benchmark mode.

Consolidation mapping:
    entity_search(method=semantic|string|tfidf)     → entity_vdb_search, entity_string_search, entity_tfidf
    entity_traverse(method=onehop|ppr|neighborhood|link) → entity_onehop, entity_ppr, entity_neighborhood, entity_link
    entity_info(method=profile|resolve)              → entity_profile, entity_resolve_names_to_ids
    relationship_search(method=graph|semantic|score)  → relationship_onehop, relationship_vdb_search, relationship_score_aggregator
    chunk_retrieve(method=text|semantic|relationships|cooccurrence|by_ids|by_entities) → chunk_text_search, chunk_vdb_search, chunk_from_relationships, chunk_occurrence, chunk_get_text_by_chunk_ids, chunk_get_text_by_entity_ids
    subgraph_extract(method=khop|steiner|pcst)       → subgraph_khop_paths, subgraph_steiner_tree, meta_pcst_optimize
    community_search(method=from_entities|from_level) → community_detect_from_entities, community_get_layer
    reason(method=answer|decompose|synthesize|extract) → meta_generate_answer, meta_decompose_question, meta_synthesize_answers, meta_extract_entities
    submit_answer                                     → unchanged
    resources                                         → list_available_resources
"""

from __future__ import annotations

import json as _json
import logging
import time as _time
import uuid as _uuid
from contextvars import ContextVar
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Operator timing observability
# Set these context vars from the benchmark runner before calling acall_llm
# so tool call timings are correlated with the LLM trace.
# ---------------------------------------------------------------------------

#: Set to the current benchmark trace_id before invoking the agent loop.
CURRENT_TRACE_ID: ContextVar[str] = ContextVar("digimon_trace_id", default="")
#: Set to the current task label (defaults to "digimon.benchmark").
CURRENT_TASK: ContextVar[str] = ContextVar("digimon_task", default="digimon.benchmark")


async def _timed_call(coro, *, tool_name: str, method: str, query_json: dict | None = None) -> str:
    """Await *coro* and log operator timing to llm_client observability DB.

    Failure never propagates from the logging side — if log_tool_call raises,
    the operator result is still returned normally.
    """
    call_id = _uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = _time.perf_counter()
    status = "succeeded"
    error_type: str | None = None
    error_message: str | None = None
    raw: str = "{}"
    try:
        raw = await coro
        return raw
    except Exception as exc:
        status = "failed"
        error_type = type(exc).__name__
        error_message = str(exc)[:300]
        raise
    finally:
        duration_ms = int((_time.perf_counter() - t0) * 1000)
        ended_at = datetime.now(timezone.utc).isoformat()
        trace_id = CURRENT_TRACE_ID.get() or None
        task = CURRENT_TASK.get() or "digimon.benchmark"
        try:
            from llm_client.observability import ToolCallResult, log_tool_call
            log_tool_call(ToolCallResult(
                call_id=call_id,
                tool_name=tool_name,
                operation=method,
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                task=task,
                trace_id=trace_id,
                error_type=error_type,
                error_message=error_message,
                query_json=query_json,
            ))
        except Exception:
            pass  # observability must never break the tool


# Consolidated tool names and their methods
CONSOLIDATED_TOOLS: dict[str, list[str]] = {
    "entity_search": ["semantic", "string", "tfidf", "agent"],
    "entity_traverse": ["onehop", "ppr", "neighborhood", "link"],
    "entity_info": ["profile", "resolve"],
    "relationship_search": ["graph", "semantic", "score", "agent"],
    "chunk_retrieve": ["text", "semantic", "relationships", "cooccurrence", "by_ids", "by_entities", "ppr_weighted"],
    "subgraph_extract": ["khop", "steiner", "pcst", "agent"],
    "community_search": ["from_entities", "from_level"],
    "reason": ["answer", "decompose", "synthesize", "extract"],
    "submit_answer": [],  # no method param
    "resources": [],  # no method param
}

# Map consolidated tool + method → original tool function name
DISPATCH_MAP: dict[tuple[str, str], str] = {
    ("entity_search", "semantic"): "entity_vdb_search",
    ("entity_search", "string"): "entity_string_search",
    ("entity_search", "tfidf"): "entity_tfidf",
    ("entity_search", "agent"): "entity_agent",
    ("entity_traverse", "onehop"): "entity_onehop",
    ("entity_traverse", "ppr"): "entity_ppr",
    ("entity_traverse", "neighborhood"): "entity_neighborhood",
    ("entity_traverse", "link"): "entity_link",
    ("entity_info", "profile"): "entity_profile",
    ("entity_info", "resolve"): "entity_resolve_names_to_ids",
    ("relationship_search", "graph"): "relationship_onehop",
    ("relationship_search", "semantic"): "relationship_vdb_search",
    ("relationship_search", "score"): "relationship_score_aggregator",
    ("relationship_search", "agent"): "relationship_agent",
    ("chunk_retrieve", "text"): "chunk_text_search",
    ("chunk_retrieve", "semantic"): "chunk_vdb_search",
    ("chunk_retrieve", "relationships"): "chunk_from_relationships",
    ("chunk_retrieve", "cooccurrence"): "chunk_occurrence",
    ("chunk_retrieve", "by_ids"): "chunk_get_text_by_chunk_ids",
    ("chunk_retrieve", "by_entities"): "chunk_get_text_by_entity_ids",
    ("chunk_retrieve", "ppr_weighted"): "chunk_aggregator",
    ("subgraph_extract", "khop"): "subgraph_khop_paths",
    ("subgraph_extract", "steiner"): "subgraph_steiner_tree",
    ("subgraph_extract", "pcst"): "meta_pcst_optimize",
    ("subgraph_extract", "agent"): "subgraph_agent_path",
    ("community_search", "from_entities"): "community_detect_from_entities",
    ("community_search", "from_level"): "community_get_layer",
    ("reason", "answer"): "meta_generate_answer",
    ("reason", "decompose"): "meta_decompose_question",
    ("reason", "synthesize"): "meta_synthesize_answers",
    ("reason", "extract"): "meta_extract_entities",
}


from typing import Any

_HOOK_LOGGER = logging.getLogger("digimon.tool_consolidation")


def get_original_tool_name(consolidated_name: str, method: str) -> str:
    """Resolve a consolidated tool + method to the original tool function name.

    Raises ValueError with clear message if method is invalid.
    """
    key = (consolidated_name, method)
    if key not in DISPATCH_MAP:
        valid = CONSOLIDATED_TOOLS.get(consolidated_name, [])
        raise ValueError(
            f"Invalid method '{method}' for tool '{consolidated_name}'. "
            f"Valid methods: {valid}"
        )
    return DISPATCH_MAP[key]


# Benchmark tool contracts for consolidated tools (replaces _BENCHMARK_TOOL_CONTRACTS)
CONSOLIDATED_BENCHMARK_CONTRACTS: dict[str, dict[str, object]] = {
    "entity_search": {
        "requires_any": ["QUERY_TEXT", "ENTITY_SET", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "methods": ["semantic", "string", "tfidf", "agent"],
        "description": "Find entities by query. Use 'semantic' for meaning-based search, 'string' for exact/fuzzy name match, 'tfidf' for IDF-weighted ranking of known candidates.",
    },
    "entity_traverse": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "methods": ["onehop", "ppr", "neighborhood", "link"],
        "description": "Explore the graph from known entities. Use 'onehop' for direct neighbors, 'ppr' for Personalized PageRank spreading (best for multi-hop), 'neighborhood' for multi-hop subgraph, 'link' for entity linking via embedding similarity.",
    },
    "entity_info": {
        "requires_any": ["QUERY_TEXT", {"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "methods": ["profile", "resolve"],
        "description": "Get entity details. Use 'profile' for a compact summary of an entity, 'resolve' to canonicalize entity name strings to graph IDs.",
    },
    "relationship_search": {
        "requires_any": ["ENTITY_SET", "QUERY_TEXT"],
        "produces": ["RELATIONSHIP_SET"],
        "methods": ["graph", "semantic", "score", "agent"],
        "description": "Find relationships. Use 'graph' for direct edges from entities, 'semantic' for meaning-based relationship search, 'score' for aggregated relationship scoring.",
    },
    "chunk_retrieve": {
        "requires_any": ["QUERY_TEXT", "ENTITY_SET", "RELATIONSHIP_SET", "CHUNK_SET"],
        "produces": [
            {"kind": "CHUNK_SET", "ref_type": "id"},
            {"kind": "CHUNK_SET", "ref_type": "fulltext"},
        ],
        "methods": ["text", "semantic", "relationships", "cooccurrence", "by_ids", "by_entities", "ppr_weighted"],
        "description": "Get text evidence. Use 'text' for keyword search, 'semantic' for embedding search, 'relationships' for chunks containing specific relationships, 'cooccurrence' for chunks where entities co-occur, 'by_ids' to fetch specific chunks, 'by_entities' to get chunks mentioning specific entities.",
    },
    "subgraph_extract": {
        "requires_all": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "produces": ["SUBGRAPH"],
        "methods": ["khop", "steiner", "pcst", "agent"],
        "description": "Extract subgraph structure. Use 'khop' for k-hop paths between entities, 'steiner' for minimum spanning tree connecting entities, 'pcst' for prize-collecting Steiner tree optimization.",
    },
    "community_search": {
        "requires_any": ["ENTITY_SET", "COMMUNITY_SET"],
        "produces": ["COMMUNITY_SET"],
        "methods": ["from_entities", "from_level"],
        "description": "Community-based retrieval. Use 'from_entities' to find communities containing entities, 'from_level' to get community hierarchy at a specific level.",
    },
    "reason": {
        "requires_any": ["QUERY_TEXT", "CHUNK_SET"],
        "produces": [{"kind": "ENTITY_SET", "ref_type": "id"}],
        "methods": ["answer", "decompose", "synthesize", "extract"],
        "description": "LLM reasoning. Use 'answer' to generate an answer from context, 'decompose' to break a multi-hop question into sub-questions, 'synthesize' to combine sub-answers, 'extract' to extract entity mentions from text.",
    },
    "submit_answer": {
        "artifact_prereqs": "none",
        "requires_any": ["QUERY_TEXT"],
        "produces": [],
        "description": "Submit your final answer. Call this when you have enough evidence to answer the question.",
    },
    "resources": {
        "artifact_prereqs": "none",
        "requires_any": [],
        "produces": [],
        "description": "List available graphs, VDBs, and other resources in the current session.",
    },
}


# TEMPORARY: This project-local logging should migrate to llm_client shared
# tool call observability when it ships. See:
# ~/projects/PROJECTS_DEFERRED/tool_call_observability.md
# The pattern (raw_size vs processed_size, data-loss detection) should
# become fields on a shared ToolCallResult dataclass.
def _log_linearization(raw: str, summary: str, tool_name: str, method: str, logger) -> None:
    """Log linearization metrics and warn on data loss."""
    import json as _json
    import os
    import time

    raw_len = len(raw)
    summary_len = len(summary)
    compression = 1.0 - (summary_len / max(raw_len, 1))

    # Detect data loss: raw has substantial content but summary says empty/not found
    empty_indicators = ["no chunks found", "no relationships found", "no entities found",
                        ": []", "found 0"]
    summary_says_empty = any(ind in summary.lower() for ind in empty_indicators)
    raw_has_content = raw_len > 50 and raw.strip() not in ('{}', '[]', 'null', '')

    if summary_says_empty and raw_has_content:
        logger.warning(
            "LINEARIZATION_DATA_LOSS tool=%s method=%s raw_len=%d summary='%s' — "
            "raw has content but linearized says empty. Check _linearize parsing.",
            tool_name, method, raw_len, summary[:100],
        )

    # Log to JSONL for analysis
    try:
        entry = _json.dumps({
            "ts": time.time(),
            "tool": tool_name,
            "method": method,
            "raw_len": raw_len,
            "summary_len": summary_len,
            "compression": round(compression, 3),
            "data_loss_warning": summary_says_empty and raw_has_content,
        })
        os.makedirs("results", exist_ok=True)
        with open("results/.linearization_log.jsonl", "a") as f:
            f.write(entry + "\n")
    except OSError:
        pass


def _linearize(raw_json: str, tool_name: str, method: str = "") -> str:
    """Wrapper that adds observability to linearization."""
    import logging
    summary = _linearize_inner(raw_json, tool_name, method)
    _log_linearization(raw_json, summary, tool_name, method, logging.getLogger("digimon.linearize"))
    return summary


def _attach_hook_context(raw_json: str, **context: Any) -> str:
    """Attach wrapper execution context for atom-completion hooks.

    Raw MCP payloads often omit the dataset, graph, or original query that the
    consolidated wrapper already knows. Bridge probes and atom advancement rely
    on that context, so preserve it here before the hook runs.
    """
    try:
        payload = _json.loads(raw_json)
    except Exception:
        return raw_json
    if not isinstance(payload, dict):
        return raw_json

    normalized = {
        key: value
        for key, value in context.items()
        if value not in ("", None, [], {})
    }
    if not normalized:
        return raw_json

    requested = {k: v for k, v in normalized.items() if k.startswith("requested_")}
    if requested:
        hook_context = payload.get("hook_context")
        if not isinstance(hook_context, dict):
            hook_context = {}
        for key, value in requested.items():
            hook_context.setdefault(key, value)
        payload["hook_context"] = hook_context

    for key, value in normalized.items():
        payload.setdefault(key, value)
    return _json.dumps(payload)


async def _run_atom_completion_hook(dms: Any, raw: str, *, tool_name: str, method: str) -> str:
    """Let the MCP server auto-complete atoms from retrieval results when possible."""
    hook = getattr(dms, "_maybe_complete_active_atom_from_payload", None)
    setattr(dms, "_last_atom_update", None)
    if not callable(hook):
        return raw
    try:
        payload = _json.loads(raw)
    except Exception:
        return raw
    if not isinstance(payload, dict):
        return raw
    try:
        atom_update = await hook(payload, tool_name=tool_name, method=method)
    except Exception:
        _HOOK_LOGGER.exception(
            "Atom-completion hook failed for %s(%s)",
            tool_name,
            method,
        )
        return raw
    if isinstance(atom_update, dict):
        setattr(dms, "_last_atom_update", atom_update)
        payload["atom_update"] = atom_update
        status_fn = getattr(dms, "_todo_status_line", None)
        if callable(status_fn):
            try:
                payload["todo_status_line"] = str(status_fn() or "")
            except Exception:
                pass
        return _json.dumps(payload)
    return raw


def _format_query_contract(data: dict[str, Any]) -> str:
    """Render query-rewrite metadata into a short natural-language prefix."""
    query_contract = data.get("query_contract")
    if not isinstance(query_contract, dict):
        return ""
    effective = str(query_contract.get("effective_query") or "").strip()
    requested = str(query_contract.get("requested_query") or "").strip()
    atom_id = str(query_contract.get("active_atom_id") or "").strip()
    deps = query_contract.get("dependency_values_used") or []
    dep_text = ""
    if isinstance(deps, list) and deps:
        dep_text = f" using {', '.join(str(dep) for dep in deps[:2])}"
    if effective and str(query_contract.get("rewritten") or "").lower() in {"true", "1"}:
        label = atom_id or "current atom"
        return f"Query rewritten for {label}{dep_text}: {effective}\n"
    if effective and atom_id and _normalize_whitespace(effective) != _normalize_whitespace(requested):
        return f"Active atom {atom_id} query{dep_text}: {effective}\n"
    return ""


_RECOVERY_HINT_ENFORCE_MIN_CONFIDENCE = 0.75


def _normalize_recovery_tool_name(tool_name: str) -> str:
    """Map tool names to the consolidated retrieval family used by recovery hints."""
    normalized = str(tool_name or "").strip().lower()
    aliases = {
        "entity_vdb_search": "entity_search",
        "entity_string_search": "entity_search",
        "entity_tfidf": "entity_search",
        "entity_agent": "entity_search",
        "entity_profile": "entity_info",
        "entity_resolve_names_to_ids": "entity_info",
        "relationship_onehop": "relationship_search",
        "relationship_vdb_search": "relationship_search",
        "relationship_score_aggregator": "relationship_search",
        "relationship_agent": "relationship_search",
        "chunk_text_search": "chunk_retrieve",
        "chunk_vdb_search": "chunk_retrieve",
        "chunk_from_relationships": "chunk_retrieve",
        "chunk_occurrence": "chunk_retrieve",
        "chunk_get_text_by_chunk_ids": "chunk_retrieve",
        "chunk_get_text_by_entity_ids": "chunk_retrieve",
        "chunk_aggregator": "chunk_retrieve",
    }
    return aliases.get(normalized, normalized)


def _active_recovery_hint(dms: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the active atom plus its public recovery hint, if any."""
    active_fn = getattr(dms, "_active_semantic_plan_atom", None)
    if not callable(active_fn):
        return None, None
    atom, _todo = active_fn()
    if not isinstance(atom, dict):
        return None, None
    atom_id = str(atom.get("atom_id") or "").strip()
    if not atom_id:
        return atom, None
    getter = getattr(dms, "_public_atom_recovery_hint", None)
    if callable(getter):
        hint = getter(atom_id)
        return atom, hint if isinstance(hint, dict) else None
    raw_hints = getattr(dms, "_atom_recovery_hints", {})
    if isinstance(raw_hints, dict):
        raw_hint = raw_hints.get(atom_id)
        if isinstance(raw_hint, dict):
            return atom, {k: v for k, v in raw_hint.items() if k != "fingerprint"}
    return atom, None


def _maybe_block_off_target_retrieval_call(
    dms: Any,
    *,
    tool_name: str,
    method: str,
    requested_query: str = "",
) -> str | None:
    """Return a policy block when a reflected recovery hint requires a different retrieval surface."""
    atom, recovery_hint = _active_recovery_hint(dms)
    if not isinstance(atom, dict) or not isinstance(recovery_hint, dict):
        return None
    confidence = float(recovery_hint.get("confidence") or 0.0)
    if confidence < _RECOVERY_HINT_ENFORCE_MIN_CONFIDENCE:
        return None

    target_tool = _normalize_recovery_tool_name(str(recovery_hint.get("target_tool_name") or ""))
    if not target_tool or target_tool == "none":
        return None
    if target_tool not in {"entity_search", "entity_info", "relationship_search"}:
        return None
    current_tool = _normalize_recovery_tool_name(tool_name)
    if current_tool == target_tool:
        return None

    target_method = str(recovery_hint.get("target_method") or "").strip()
    suggested_query = str(recovery_hint.get("suggested_query") or requested_query or "").strip()
    next_action = str(recovery_hint.get("next_action") or "").strip()
    atom_id = str(atom.get("atom_id") or "").strip()
    tool_display = f"{target_tool}({target_method})" if target_method else target_tool

    return _json.dumps(
        {
            "policy_status": "blocked",
            "policy_code": "RECOVERY_HINT_TOOL_MISMATCH",
            "message": (
                f"Active atom {atom_id} currently has a high-confidence recovery hint preferring "
                f"{tool_display}, but this call used {tool_name}({method}). Follow the hinted "
                "surface before spending more retrieval budget on off-target calls."
            ),
            "suggested_next_actions": [
                f"Call {tool_display} next with query '{suggested_query}'.".strip(),
                next_action,
            ],
            "query_contract": {
                "active_atom_id": atom_id,
                "requested_query": requested_query,
                "effective_query": suggested_query,
                "rewritten": bool(suggested_query and _normalize_whitespace(suggested_query) != _normalize_whitespace(requested_query)),
                "rewrite_reason": ["atom_reflection_tool_guard"],
                "recovery_hint": recovery_hint,
            },
            "recovery_hint": recovery_hint,
        }
    )


def _format_entity_scope_contract(data: dict[str, Any]) -> str:
    """Render entity-scope rewrites into a short natural-language prefix."""
    scope = data.get("entity_scope_contract")
    if not isinstance(scope, dict):
        return ""
    effective = scope.get("effective_entities") or []
    requested = scope.get("requested_entities") or []
    atom_id = str(scope.get("active_atom_id") or "").strip()
    if not isinstance(effective, list) or not effective:
        return ""
    effective_text = ", ".join(str(value) for value in effective[:2])
    requested_text = ", ".join(str(value) for value in requested[:2]) if isinstance(requested, list) else ""
    if bool(scope.get("rewritten")):
        label = atom_id or "current atom"
        if requested_text:
            return f"Entity scope rewritten for {label}: {requested_text} -> {effective_text}\n"
        return f"Entity scope rewritten for {label}: {effective_text}\n"
    return ""


def _format_atom_update(data: dict[str, Any]) -> str:
    """Render atom lifecycle updates into a short natural-language prefix."""
    atom_update = data.get("atom_update")
    if not isinstance(atom_update, dict):
        return ""
    event = str(atom_update.get("event") or "").strip()
    atom_id = str(atom_update.get("atom_id") or "").strip()
    evidence_refs = atom_update.get("evidence_refs") or []
    evidence_text = ""
    if isinstance(evidence_refs, list) and evidence_refs:
        evidence_text = f" Evidence refs: {', '.join(str(ref) for ref in evidence_refs[:4])}."
    if event == "atom_completed":
        resolved = str(atom_update.get("resolved_value") or "").strip()
        next_atom = str(atom_update.get("next_atom") or "").strip()
        if next_atom:
            return f"Atom {atom_id} completed: {resolved}.{evidence_text} Advancing to {next_atom}.\n"
        return f"Atom {atom_id} completed: {resolved}.{evidence_text}\n"
    if event == "atom_judged_unresolved":
        rationale = str(atom_update.get("rationale") or "").strip()
        next_action = str(atom_update.get("next_action") or "").strip()
        if rationale:
            suffix = f" Next: {next_action}" if next_action else ""
            return f"Atom {atom_id} remains unresolved: {rationale}{suffix}\n"
    if event == "atom_promoted":
        sub_question = str(atom_update.get("sub_question") or "").strip()
        return f"Next active atom {atom_id}: {sub_question}\n"
    return ""


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace for compact text comparisons."""
    return " ".join((text or "").split())


def _format_graph_neighbor_map(neighbors: dict[str, Any], *, label: str) -> str:
    """Summarize one-hop neighbor maps into compact natural language."""
    if not isinstance(neighbors, dict) or not neighbors:
        return f"{label}: No entities found."

    lines: list[str] = []
    total_neighbors = 0
    for src, raw_items in list(neighbors.items())[:3]:
        if not isinstance(raw_items, list) or not raw_items:
            continue
        preview: list[str] = []
        for item in raw_items[:6]:
            if isinstance(item, dict):
                name = str(
                    item.get("entity_name")
                    or item.get("entity_id")
                    or item.get("canonical_name")
                    or "?"
                )
                coarse_type = str(item.get("coarse_type") or item.get("entity_type") or "").strip()
                score = item.get("score")
                bits = [f"'{name}'"]
                if coarse_type:
                    bits.append(f"({coarse_type})")
                if isinstance(score, (int, float)):
                    bits.append(f"score={score:.2f}")
                preview.append(" ".join(bits))
            else:
                preview.append(str(item))
        total_neighbors += len(raw_items)
        lines.append(f"  - {src}: {', '.join(preview)}")

    if not lines:
        return f"{label}: No entities found."
    return f"{label}: Found {total_neighbors} neighboring entities:\n" + "\n".join(lines)


def _format_relationship_items(rels: list[Any], *, label: str) -> str:
    """Summarize relationship payloads, including one-hop graph edges."""
    if not isinstance(rels, list) or not rels:
        return f"{label}: No relationships found."

    items: list[str] = []
    for rel_item in rels[:10]:
        if not isinstance(rel_item, dict):
            items.append(str(rel_item))
            continue
        src = str(
            rel_item.get("src_id")
            or rel_item.get("source_node_id")
            or rel_item.get("source")
            or "?"
        )
        tgt = str(
            rel_item.get("tgt_id")
            or rel_item.get("target_node_id")
            or rel_item.get("target")
            or "?"
        )
        relation = str(
            rel_item.get("relation_name")
            or rel_item.get("type")
            or rel_item.get("relation")
            or "related_to"
        )
        desc = _normalize_whitespace(str(rel_item.get("description") or ""))
        attrs = rel_item.get("attributes")
        source_ref = ""
        if isinstance(attrs, dict):
            source_ref = str(attrs.get("source_id") or "").strip()

        line = f"'{src}' →[{relation}]→ '{tgt}'"
        extras: list[str] = []
        if desc and desc.casefold() not in {relation.casefold(), f"{src} {relation} {tgt}".casefold()}:
            extras.append(desc[:140])
        weight = rel_item.get("weight")
        if isinstance(weight, (int, float)):
            extras.append(f"weight={weight:.2f}")
        if source_ref:
            extras.append(source_ref)
        if extras:
            line += " — " + "; ".join(extras)
        items.append(line)

    return f"{label}: Found {len(rels)} relationships:\n" + "\n".join(f"  - {item}" for item in items)


def _linearize_inner(raw_json: str, tool_name: str, method: str = "") -> str:
    """Linearize structured tool output into compact NL summary.

    Converts raw JSON into 2-5 line natural language summary for LLM context.
    Full JSON written to results/.last_tool_result.json for inspection.
    Per StructGPT IRR principle: LLMs reason better on linearized summaries
    than raw structured data.

    Observability: logs raw vs linearized size to results/.linearization_log.jsonl
    and warns if linearization produces empty result from non-empty raw data.
    """
    import json as _json
    import os
    import logging
    import time

    _lin_logger = logging.getLogger("digimon.linearize")

    # Write full data to file for agent inspection if needed
    try:
        os.makedirs("results", exist_ok=True)
        with open("results/.last_tool_result.json", "w") as f:
            f.write(raw_json)
    except OSError:
        pass

    try:
        data = _json.loads(raw_json)
    except (_json.JSONDecodeError, TypeError):
        return raw_json  # Not JSON, return as-is

    if isinstance(data, dict) and str(data.get("policy_status") or "").strip().lower() == "blocked":
        query_prefix = _format_query_contract(data)
        message = str(data.get("message") or "Blocked by controller policy.").strip()
        actions = data.get("suggested_next_actions") or []
        action_lines = [
            f"  - {str(action).strip()}"
            for action in actions
            if str(action).strip()
        ]
        summary = f"Blocked by controller policy: {message}"
        if action_lines:
            summary += "\nSuggested next actions:\n" + "\n".join(action_lines)
        return query_prefix + summary

    # Error results pass through
    if isinstance(data, dict) and "error" in data:
        message = str(data.get("message") or "").strip()
        if message:
            return f"Error: {data['error']} — {message}"
        return f"Error: {data['error']}"

    label = f"{tool_name}({method})" if method else tool_name
    query_prefix = _format_query_contract(data) if isinstance(data, dict) else ""
    entity_scope_prefix = _format_entity_scope_contract(data) if isinstance(data, dict) else ""
    atom_prefix = _format_atom_update(data) if isinstance(data, dict) else ""
    todo_prefix = ""
    if isinstance(data, dict):
        todo_status_line = str(data.get("todo_status_line") or "").strip()
        if todo_status_line:
            todo_prefix = f"{todo_status_line}\n"

    # Entity results
    if tool_name in ("entity_search", "entity_traverse", "entity_info"):
        entities = data if isinstance(data, list) else (
            data.get("similar_entities")
            or data.get("matches")
            or data.get("resolved_entities")
            or data.get("ranked_entities")
            or data.get("entities")
            or data.get("neighbors")
            or []
        )
        if isinstance(entities, list) and entities:
            items = []
            for e in entities[:8]:
                if isinstance(e, dict):
                    name = e.get(
                        "resolved_entity_name",
                        e.get("canonical_name", e.get("entity_name", e.get("name", "?"))),
                    )
                    etype = e.get("entity_type", "")
                    score = e.get("score", e.get("similarity_score", e.get("match_score", "")))
                    desc = (e.get("description", "") or "")
                    match_type = str(e.get("match_type") or e.get("resolution_mode") or "").strip()
                    parts = [f"'{name}'"]
                    if etype:
                        parts.append(f"({etype})")
                    if match_type:
                        parts.append(f"[{match_type}]")
                    if score:
                        parts.append(f"score={score:.2f}" if isinstance(score, float) else f"score={score}")
                    if desc:
                        parts.append(f"— {desc}")
                    items.append(" ".join(parts))
                elif isinstance(e, list) and len(e) >= 2:
                    items.append(f"'{e[0]}' (score={e[1]:.2f})" if isinstance(e[1], float) else str(e))
            total = len(entities)
            shown = min(8, total)
            summary = f"{label}: Found {total} entities"
            if shown < total:
                summary += f" (showing top {shown})"
            summary += ":\n" + "\n".join(f"  - {item}" for item in items)
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + summary
        if isinstance(entities, dict) and entities:
            summary = _format_graph_neighbor_map(entities, label=label)
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + summary
        # Profile/resolve results
        if isinstance(data, dict) and (
            "entity_name" in data or "description" in data or "canonical_name" in data or "entity_id" in data
        ):
            name = data.get("canonical_name", data.get("entity_name", data.get("entity_id", "?")))
            etype = data.get("entity_type", data.get("coarse_type", ""))
            desc = (data.get("description", data.get("short_description", "")) or "")
            edge_count = data.get("edge_count")
            relationship_types = data.get("relationship_types") or []
            connected_entities = data.get("connected_entities") or []
            summary = f"{label}: '{name}' ({etype}). {desc}"
            if edge_count:
                summary += f" edge_count={edge_count}."
            if relationship_types:
                summary += " relation_types=" + ", ".join(str(rt) for rt in relationship_types[:4]) + "."
            if isinstance(connected_entities, list) and connected_entities:
                preview = []
                for item in connected_entities[:5]:
                    if isinstance(item, dict):
                        preview.append(str(item.get("entity_name") or item.get("entity_id") or "?"))
                    else:
                        preview.append(str(item))
                summary += " connected_entities=" + ", ".join(preview) + "."
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + summary
        return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"{label}: {str(data)[:300]}"

    # Relationship results
    if tool_name == "relationship_search":
        rels = data if isinstance(data, list) else (
            data.get("relationships")
            or data.get("edges")
            or data.get("one_hop_relationships")
            or []
        )
        summary = _format_relationship_items(rels, label=label)
        return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + summary

    # Chunk results
    if tool_name == "chunk_retrieve":
        chunks = data if isinstance(data, list) else data.get("chunks") or data.get("retrieved_chunks") or data.get("results") or []
        if isinstance(chunks, list) and chunks:
            items = []
            for c in chunks:
                if isinstance(c, dict):
                    text = (c.get("content", c.get("text", c.get("chunk_text", c.get("text_content", "")))) or "")
                    cid = c.get("chunk_id", c.get("id", ""))
                    items.append(f"[{cid}]: {text}")
                elif isinstance(c, str):
                    items.append(c)
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"{label}: Retrieved {len(chunks)} chunks:\n" + "\n".join(f"  - {item}" for item in items)
        return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"{label}: No chunks found."

    # Reason results
    if tool_name == "reason":
        if method == "decompose":
            subs = data if isinstance(data, list) else data.get("sub_questions") or []
            if isinstance(subs, list) and subs:
                items = []
                for i, s in enumerate(subs, 1):
                    q = s.get("entity_name", s.get("sub_question", str(s)))[:80] if isinstance(s, dict) else str(s)[:80]
                    items.append(f"  {i}. {q}")
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"Decomposed into {len(subs)} sub-questions:\n" + "\n".join(items)
        if method == "answer":
            answer = data.get("answer", str(data)[:200]) if isinstance(data, dict) else str(data)[:200]
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"Generated answer: {answer}"
        if method == "synthesize":
            answer = data.get("synthesis", data.get("answer", str(data)[:200])) if isinstance(data, dict) else str(data)[:200]
            return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"Synthesized answer: {answer}"

    # Default: truncate
    text = str(data)[:400]
    return atom_prefix + query_prefix + entity_scope_prefix + todo_prefix + f"{label}: {text}"


def _normalize_scope_value(value: Any) -> str:
    """Normalize entity-scope terms for dependency-overlap checks."""
    return " ".join(str(value or "").casefold().split())


def _entity_scope_list(value: list[str] | str | None) -> list[str]:
    """Coerce one-or-many entity scope values into a compact string list."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _rewrite_entity_scope_for_active_atom(
    dms: Any,
    *,
    tool_name: str,
    entity_names: list[str] | str | None = None,
    entity_ids: list[str] | str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Forward resolved dependency entities into downstream entity-scoped tools."""
    active_atom_fn = getattr(dms, "_active_semantic_plan_atom", None)
    dependency_fn = getattr(dms, "_resolved_dependency_values", None)
    if not callable(active_atom_fn) or not callable(dependency_fn):
        return _entity_scope_list(entity_names) or _entity_scope_list(entity_ids), {}

    atom, _todo = active_atom_fn()
    if not isinstance(atom, dict):
        return _entity_scope_list(entity_names) or _entity_scope_list(entity_ids), {}

    dependency_values = dependency_fn(atom)
    if not isinstance(dependency_values, list) or not dependency_values:
        return _entity_scope_list(entity_names) or _entity_scope_list(entity_ids), {}

    requested_entities = _entity_scope_list(entity_names) or _entity_scope_list(entity_ids)
    dependency_norms = {_normalize_scope_value(value) for value in dependency_values if _normalize_scope_value(value)}
    requested_norms = {_normalize_scope_value(value) for value in requested_entities if _normalize_scope_value(value)}
    if requested_norms and any(
        requested == dep or requested in dep or dep in requested
        for requested in requested_norms
        for dep in dependency_norms
    ):
        return requested_entities, {
            "tool_name": tool_name,
            "active_atom_id": str(atom.get("atom_id") or "").strip(),
            "requested_entities": requested_entities,
            "effective_entities": requested_entities,
            "dependency_values_used": dependency_values,
            "rewritten": False,
            "rewrite_reason": [],
        }

    effective_entities = [str(value).strip() for value in dependency_values if str(value).strip()][:2]
    if not effective_entities:
        return requested_entities, {}

    return effective_entities, {
        "tool_name": tool_name,
        "active_atom_id": str(atom.get("atom_id") or "").strip(),
        "requested_entities": requested_entities,
        "effective_entities": effective_entities,
        "dependency_values_used": dependency_values,
        "rewritten": True,
        "rewrite_reason": ["dependency_entity_scope_forwarded"],
    }


def build_consolidated_tools(dms: Any) -> list:
    """Build consolidated tool functions that dispatch to the MCP server module.

    Args:
        dms: The imported digimon_mcp_stdio_server module.

    Returns:
        List of async callables ready for llm_client python_tools= parameter.
    """
    async def entity_search(
        query: str,
        method: str = "semantic",
        dataset_name: str = "",
        top_k: int = 5,
        graph_reference_id: str = "",
        vdb_reference_id: str = "",
        candidate_entity_ids: list[str] | str | None = None,
    ) -> str:
        """Find entities by query.

        Methods:
        - "semantic": Meaning-based vector search over entity embeddings. Best for finding entities related to a concept.
        - "string": Exact/fuzzy substring match on entity names. Best when you know part of the entity name.
        - "tfidf": IDF-weighted ranking of known candidate entities. Best for scoring already-retrieved candidates by relevance.

        Args:
            method: One of "semantic", "string", "tfidf".
            query: The search query text.
            dataset_name: Dataset to search in (optional, auto-resolved).
            top_k: Max results to return.
            graph_reference_id: Graph ID for string/tfidf methods.
            vdb_reference_id: VDB ID for semantic method.
            candidate_entity_ids: Pre-existing candidate IDs to re-rank (tfidf only).
        """
        blocked = _maybe_block_off_target_retrieval_call(
            dms,
            tool_name="entity_search",
            method=method,
            requested_query=query,
        )
        if blocked is not None:
            return _linearize(blocked, "entity_search", method)
        if method == "semantic":
            raw = await _timed_call(
                dms.entity_vdb_search(
                    query_text=query, query=query, dataset_name=dataset_name,
                    top_k=top_k, vdb_reference_id=vdb_reference_id,
                ),
                tool_name="entity_search", method="semantic",
                query_json={"query": query, "top_k": top_k},
            )
        elif method == "string":
            raw = await _timed_call(
                dms.entity_string_search(
                    query=query, dataset_name=dataset_name, top_k=top_k,
                    graph_reference_id=graph_reference_id,
                ),
                tool_name="entity_search", method="string",
                query_json={"query": query, "top_k": top_k},
            )
        elif method == "tfidf":
            raw = await _timed_call(
                dms.entity_tfidf(
                    query_text=query, graph_reference_id=graph_reference_id,
                    top_k=top_k, candidate_entity_ids=candidate_entity_ids,
                ),
                tool_name="entity_search", method="tfidf",
                query_json={"query": query, "top_k": top_k},
            )
        elif method == "agent":
            raw = await _timed_call(
                dms.entity_agent(
                    query_text=query, text_context=query,
                    max_entities=top_k,
                ),
                tool_name="entity_search", method="agent",
                query_json={"query": query, "top_k": top_k},
            )
        else:
            return _json.dumps({"error": f"Invalid method '{method}'. Use: semantic, string, tfidf, agent"})
        raw = _attach_hook_context(
            raw,
            requested_query=query,
            resolved_dataset_name=dataset_name,
            resolved_graph_reference_id=graph_reference_id,
            resolved_vdb_reference_id=vdb_reference_id,
        )
        raw = await _run_atom_completion_hook(dms, raw, tool_name="entity_search", method=method)
        return _linearize(raw, "entity_search", method)

    async def entity_traverse(
        method: str = "onehop",
        entity_ids: list[str] | str | None = None,
        entity_names: list[str] | str | None = None,
        graph_reference_id: str = "",
        dataset_name: str = "",
        top_k: int = 10,
        hops: int = 1,
        max_nodes: int = 50,
        similarity_threshold: float = 0.8,
        vdb_reference_id: str = "",
    ) -> str:
        """Explore the graph from known entities.

        Methods:
        - "onehop": Direct neighbors in the graph. Fast, exact.
        - "ppr": Personalized PageRank spreading activation. Best for multi-hop reasoning — finds entities connected through chains.
        - "neighborhood": Multi-hop subgraph around entities (configurable depth via 'hops').
        - "link": Entity linking via embedding similarity. Finds graph entities matching text mentions.

        Args:
            method: One of "onehop", "ppr", "neighborhood", "link".
            entity_ids: Entity IDs to start from (onehop, ppr).
            entity_names: Entity names to start from (neighborhood, link).
            graph_reference_id: Which graph to traverse.
            dataset_name: Dataset name (optional, auto-resolved).
            top_k: Max results.
            hops: Number of hops for neighborhood method (1-3).
            max_nodes: Max nodes for neighborhood method.
            similarity_threshold: Threshold for link method.
            vdb_reference_id: VDB ID for link method.
        """
        if method == "onehop":
            raw = await _timed_call(
                dms.entity_onehop(
                    entity_ids=entity_ids, entity_name=None,
                    graph_reference_id=graph_reference_id, dataset_name=dataset_name,
                    top_k=top_k,
                ),
                tool_name="entity_traverse", method="onehop",
            )
        elif method == "ppr":
            seeds = entity_ids if isinstance(entity_ids, list) else [entity_ids] if entity_ids else []
            raw = await _timed_call(
                dms.entity_ppr(
                    graph_reference_id=graph_reference_id,
                    seed_entity_ids=seeds, top_k=top_k,
                ),
                tool_name="entity_traverse", method="ppr",
            )
        elif method == "neighborhood":
            names = entity_names or entity_ids or []
            raw = await _timed_call(
                dms.entity_neighborhood(
                    entity_names=names, graph_reference_id=graph_reference_id,
                    dataset_name=dataset_name, hops=hops, max_nodes=max_nodes,
                ),
                tool_name="entity_traverse", method="neighborhood",
            )
        elif method == "link":
            names = entity_names or entity_ids or []
            raw = await _timed_call(
                dms.entity_link(
                    source_entities=None, entity_names=names,
                    vdb_reference_id=vdb_reference_id, dataset_name=dataset_name,
                    similarity_threshold=similarity_threshold,
                ),
                tool_name="entity_traverse", method="link",
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: onehop, ppr, neighborhood, link"})
        raw = _attach_hook_context(
            raw,
            resolved_dataset_name=dataset_name,
            resolved_graph_reference_id=graph_reference_id,
            resolved_vdb_reference_id=vdb_reference_id,
            requested_entity_ids=entity_ids,
            requested_entity_names=entity_names,
        )
        raw = await _run_atom_completion_hook(dms, raw, tool_name="entity_traverse", method=method)
        return _linearize(raw, "entity_traverse", method)

    async def entity_info(
        method: str,
        entity_name: str = "",
        entity_id: str = "",
        entity_names: list[str] | str | None = None,
        graph_reference_id: str = "",
        dataset_name: str = "",
        vdb_reference_id: str = "",
        top_k_per_name: int = 3,
    ) -> str:
        """Get entity details or resolve names to graph IDs.

        Methods:
        - "profile": Compact summary of an entity (type, description, connections).
        - "resolve": Canonicalize entity name strings to graph node IDs.

        Args:
            method: One of "profile", "resolve".
            entity_name: Single entity name (profile).
            entity_id: Entity ID (profile).
            entity_names: List of names to resolve (resolve).
            graph_reference_id: Graph to look up in.
            dataset_name: Dataset name (optional).
            vdb_reference_id: VDB for resolve method.
            top_k_per_name: Candidates per name for resolve.
        """
        blocked = _maybe_block_off_target_retrieval_call(
            dms,
            tool_name="entity_info",
            method=method,
            requested_query=entity_name,
        )
        if blocked is not None:
            return _linearize(blocked, "entity_info", method)
        effective_scope: list[str] = []
        entity_scope_contract: dict[str, Any] = {}
        effective_entity_name = entity_name
        if method == "profile":
            effective_scope, entity_scope_contract = _rewrite_entity_scope_for_active_atom(
                dms,
                tool_name="entity_info",
                entity_names=entity_name,
                entity_ids=entity_id,
            )
            if effective_scope:
                effective_entity_name = effective_scope[0]
                entity_id = ""
        if method == "profile":
            raw = await _timed_call(
                dms.entity_profile(
                    entity_id=entity_id, entity_name=effective_entity_name,
                    graph_reference_id=graph_reference_id, dataset_name=dataset_name,
                ),
                tool_name="entity_info", method="profile",
                query_json={"entity_name": entity_name},
            )
        elif method == "resolve":
            resolved_names = entity_names
            if not resolved_names and entity_name:
                resolved_names = [entity_name]
            raw = await _timed_call(
                dms.entity_resolve_names_to_ids(
                    entity_names=resolved_names, vdb_reference_id=vdb_reference_id,
                    dataset_name=dataset_name, top_k_per_name=top_k_per_name,
                ),
                tool_name="entity_info", method="resolve",
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: profile, resolve"})
        raw = _attach_hook_context(
            raw,
            resolved_dataset_name=dataset_name,
            resolved_graph_reference_id=graph_reference_id,
            resolved_vdb_reference_id=vdb_reference_id,
            requested_entity_name=entity_name,
            requested_entity_id=entity_id,
            requested_entity_names=entity_names,
            entity_scope_contract=entity_scope_contract,
        )
        raw = await _run_atom_completion_hook(dms, raw, tool_name="entity_info", method=method)
        return _linearize(raw, "entity_info", method)

    async def relationship_search(
        method: str = "graph",
        entity_ids: list[str] | str | None = None,
        graph_reference_id: str = "",
        query_text: str = "",
        vdb_reference_id: str = "",
        top_k: int = 10,
        entity_scores: dict | None = None,
    ) -> str:
        """Find relationships between entities.

        Methods:
        - "graph": Direct edges from entities in the knowledge graph. Returns typed relationships.
        - "semantic": Meaning-based search over relationship embeddings.
        - "score": Aggregate and rank relationships by entity importance scores.

        Args:
            method: One of "graph", "semantic", "score".
            entity_ids: Entity IDs to get relationships for (graph).
            graph_reference_id: Graph to search.
            query_text: Query for semantic search.
            vdb_reference_id: VDB for semantic method.
            top_k: Max results.
            entity_scores: Entity importance scores for score method.
        """
        blocked = _maybe_block_off_target_retrieval_call(
            dms,
            tool_name="relationship_search",
            method=method,
            requested_query=query_text,
        )
        if blocked is not None:
            return _linearize(blocked, "relationship_search", method)
        effective_entity_ids = entity_ids
        entity_scope_contract: dict[str, Any] = {}
        if method == "graph":
            scope, entity_scope_contract = _rewrite_entity_scope_for_active_atom(
                dms,
                tool_name="relationship_search",
                entity_ids=entity_ids,
            )
            if scope:
                effective_entity_ids = scope
        if method == "graph":
            raw = await _timed_call(
                dms.relationship_onehop(
                    entity_ids=effective_entity_ids, graph_reference_id=graph_reference_id,
                ),
                tool_name="relationship_search", method="graph",
            )
        elif method == "semantic":
            raw = await _timed_call(
                dms.relationship_vdb_search(
                    query_text=query_text, vdb_reference_id=vdb_reference_id,
                    top_k=top_k,
                ),
                tool_name="relationship_search", method="semantic",
                query_json={"query": query_text, "top_k": top_k},
            )
        elif method == "score":
            raw = await _timed_call(
                dms.relationship_score_aggregator(
                    graph_reference_id=graph_reference_id,
                    entity_scores=entity_scores, top_k=top_k,
                ),
                tool_name="relationship_search", method="score",
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: graph, semantic, score"})
        raw = _attach_hook_context(
            raw,
            requested_query=query_text,
            requested_entity_ids=entity_ids,
            resolved_graph_reference_id=graph_reference_id,
            resolved_vdb_reference_id=vdb_reference_id,
            entity_scope_contract=entity_scope_contract,
        )
        raw = await _run_atom_completion_hook(dms, raw, tool_name="relationship_search", method=method)
        return _linearize(raw, "relationship_search", method)

    async def chunk_retrieve(
        method: str = "text",
        query_text: str = "",
        dataset_name: str = "",
        top_k: int = 5,
        entity_names: list[str] | str | None = None,
        entity_ids: list[str] | str | None = None,
        target_relationships: list[str] | None = None,
        chunk_ids: list[str] | str | None = None,
        document_collection_id: str = "",
        graph_reference_id: str = "",
    ) -> str:
        """Get text evidence from the corpus.

        Methods:
        - "text": Keyword/TF-IDF search over chunk text. Fast, good for known phrases.
        - "semantic": Embedding-based search over chunks. Best for meaning-based retrieval.
        - "relationships": Get chunks that contain specific relationships (requires relationship IDs from relationship_search).
        - "cooccurrence": Get chunks where specific entities co-occur. Good for finding evidence of entity connections.
        - "by_ids": Fetch specific chunks by their IDs.
        - "by_entities": Get chunks that mention specific entities.

        Args:
            method: One of "text", "semantic", "relationships", "cooccurrence", "by_ids", "by_entities".
            query_text: Search query (text, semantic).
            dataset_name: Dataset name (optional, auto-resolved).
            top_k: Max results.
            entity_names: Entity names for cooccurrence/by_entities.
            entity_ids: Entity IDs for by_entities.
            target_relationships: Relationship strings for relationships method (format: "source->target").
            chunk_ids: Chunk IDs for by_ids method.
            document_collection_id: Document collection for relationships/cooccurrence.
            graph_reference_id: Graph reference for by_entities.
        """
        blocked = _maybe_block_off_target_retrieval_call(
            dms,
            tool_name="chunk_retrieve",
            method=method,
            requested_query=query_text,
        )
        if blocked is not None:
            return _linearize(blocked, "chunk_retrieve", method)
        effective_entity_names = entity_names
        effective_entity_ids = entity_ids
        entity_scope_contract: dict[str, Any] = {}
        if method == "by_entities":
            scope, entity_scope_contract = _rewrite_entity_scope_for_active_atom(
                dms,
                tool_name="chunk_retrieve",
                entity_names=entity_names,
                entity_ids=entity_ids,
            )
            if scope:
                effective_entity_names = scope
                effective_entity_ids = []
        if method == "text":
            raw = await _timed_call(
                dms.chunk_text_search(
                    query_text=query_text, dataset_name=dataset_name,
                    top_k=top_k, entity_names=entity_names,
                ),
                tool_name="chunk_retrieve", method="text",
                query_json={"query": query_text, "top_k": top_k},
            )
        elif method == "semantic":
            raw = await _timed_call(
                dms.chunk_vdb_search(
                    query_text=query_text, dataset_name=dataset_name,
                    top_k=top_k, entity_names=entity_names,
                ),
                tool_name="chunk_retrieve", method="semantic",
                query_json={"query": query_text, "top_k": top_k},
            )
        elif method == "relationships":
            raw = await _timed_call(
                dms.chunk_from_relationships(
                    target_relationships=target_relationships or [],
                    document_collection_id=document_collection_id,
                    dataset_name=dataset_name, top_k=top_k,
                ),
                tool_name="chunk_retrieve", method="relationships",
            )
        elif method == "cooccurrence":
            raw = await _timed_call(
                dms.chunk_occurrence(
                    entity_names=entity_names, dataset_name=dataset_name,
                    document_collection_id=document_collection_id, top_k=top_k,
                ),
                tool_name="chunk_retrieve", method="cooccurrence",
            )
        elif method == "by_ids":
            raw = await _timed_call(
                dms.chunk_get_text_by_chunk_ids(
                    chunk_ids=chunk_ids, dataset_name=dataset_name,
                ),
                tool_name="chunk_retrieve", method="by_ids",
            )
        elif method == "by_entities":
            raw = await _timed_call(
                dms.chunk_get_text_by_entity_ids(
                    entity_ids=effective_entity_ids, entity_names=effective_entity_names,
                    graph_reference_id=graph_reference_id, dataset_name=dataset_name,
                ),
                tool_name="chunk_retrieve", method="by_entities",
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: text, semantic, relationships, cooccurrence, by_ids, by_entities"})
        raw = _attach_hook_context(
            raw,
            requested_query=query_text,
            requested_entity_names=entity_names,
            requested_entity_ids=entity_ids,
            requested_chunk_ids=chunk_ids,
            resolved_dataset_name=dataset_name,
            resolved_graph_reference_id=graph_reference_id,
            entity_scope_contract=entity_scope_contract,
        )
        raw = await _run_atom_completion_hook(dms, raw, tool_name="chunk_retrieve", method=method)
        return _linearize(raw, "chunk_retrieve", method)

    async def subgraph_extract(
        method: str,
        graph_reference_id: str = "",
        entity_ids: list[str] | None = None,
        start_entity_ids: list[str] | None = None,
        end_entity_ids: list[str] | None = None,
        k_hops: int = 2,
        max_paths: int = 5,
        entity_scores: dict | None = None,
        relationship_triples: list[dict] | None = None,
    ) -> str:
        """Extract subgraph structure connecting entities.

        Methods:
        - "khop": Find k-hop paths between start and end entities.
        - "steiner": Minimum Steiner tree connecting terminal entities.
        - "pcst": Prize-collecting Steiner tree optimization using entity scores.

        Args:
            method: One of "khop", "steiner", "pcst".
            graph_reference_id: Graph to extract from.
            entity_ids: Terminal entity IDs (steiner, pcst).
            start_entity_ids: Start entities for khop.
            end_entity_ids: End entities for khop.
            k_hops: Max path length for khop.
            max_paths: Max paths to return for khop.
            entity_scores: Entity importance scores for pcst.
            relationship_triples: Relationship data for pcst.
        """
        if method == "khop":
            raw = await _timed_call(
                dms.subgraph_khop_paths(
                    graph_reference_id=graph_reference_id,
                    start_entity_ids=start_entity_ids or entity_ids or [],
                    end_entity_ids=end_entity_ids, k_hops=k_hops, max_paths=max_paths,
                ),
                tool_name="subgraph_extract", method="khop",
            )
        elif method == "steiner":
            raw = await _timed_call(
                dms.subgraph_steiner_tree(
                    graph_reference_id=graph_reference_id,
                    terminal_node_ids=entity_ids or [],
                ),
                tool_name="subgraph_extract", method="steiner",
            )
        elif method == "pcst":
            raw = await _timed_call(
                dms.meta_pcst_optimize(
                    entity_ids=entity_ids or [], entity_scores=entity_scores or {},
                    relationship_triples=relationship_triples or [],
                    graph_reference_id=graph_reference_id,
                ),
                tool_name="subgraph_extract", method="pcst",
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: khop, steiner, pcst"})

        return _linearize(raw, "subgraph_extract", method)

    async def community_search(
        method: str,
        graph_reference_id: str = "",
        community_hierarchy_reference_id: str = "",
        seed_entity_ids: list[str] | None = None,
        max_communities: int = 5,
        max_layer_depth: int = 2,
    ) -> str:
        """Community-based retrieval.

        Methods:
        - "from_entities": Find communities containing specific entities.
        - "from_level": Get community hierarchy at a specific level.

        Args:
            method: One of "from_entities", "from_level".
            graph_reference_id: Graph for from_entities.
            community_hierarchy_reference_id: Hierarchy ref for from_level.
            seed_entity_ids: Entity IDs to find communities for.
            max_communities: Max communities to return.
            max_layer_depth: Max hierarchy depth for from_level.
        """
        if method == "from_entities":
            raw = await _timed_call(
                dms.community_detect_from_entities(
                    graph_reference_id=graph_reference_id,
                    seed_entity_ids=seed_entity_ids or [], max_communities=max_communities,
                ),
                tool_name="community_search", method="from_entities",
            )
        elif method == "from_level":
            raw = await _timed_call(
                dms.community_get_layer(
                    community_hierarchy_reference_id=community_hierarchy_reference_id,
                    max_layer_depth=max_layer_depth,
                ),
                tool_name="community_search", method="from_level",
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: from_entities, from_level"})

        return _linearize(raw, "community_search", method)

    async def reason(
        method: str = "answer",
        query_text: str = "",
        context_chunks: list[str] | None = None,
        sub_answers: list[str] | None = None,
        max_questions: int = 4,
        synthesis_style: str = "chain",
    ) -> str:
        """LLM reasoning operations for question answering.

        Methods:
        - "answer": Generate an answer from retrieved context chunks. Call after retrieving evidence.
        - "decompose": Break a multi-hop question into simpler sub-questions. Call FIRST for complex questions.
        - "synthesize": Combine answers to sub-questions into a final answer.
        - "extract": Extract entity mentions from the question text (for entity linking).

        Args:
            method: One of "answer", "decompose", "synthesize", "extract".
            query_text: The question or text to process.
            context_chunks: Retrieved text evidence (answer method).
            sub_answers: Answers to sub-questions (synthesize method).
            max_questions: Max sub-questions to generate (decompose method).
            synthesis_style: How to combine sub-answers (synthesize method).
        """
        if method == "answer":
            raw = await _timed_call(
                dms.meta_generate_answer(
                    query_text=query_text, context_chunks=context_chunks or [],
                ),
                tool_name="reason", method="answer",
                query_json={"query": query_text},
            )
        elif method == "decompose":
            raw = await _timed_call(
                dms.meta_decompose_question(
                    query_text=query_text, max_questions=max_questions,
                ),
                tool_name="reason", method="decompose",
                query_json={"query": query_text},
            )
        elif method == "synthesize":
            raw = await _timed_call(
                dms.meta_synthesize_answers(
                    query_text=query_text, sub_answers=sub_answers or [],
                    synthesis_style=synthesis_style,
                ),
                tool_name="reason", method="synthesize",
                query_json={"query": query_text},
            )
        elif method == "extract":
            raw = await _timed_call(
                dms.meta_extract_entities(query_text=query_text),
                tool_name="reason", method="extract",
                query_json={"query": query_text},
            )
        else:

            return _json.dumps({"error": f"Invalid method '{method}'. Use: answer, decompose, synthesize, extract"})

        return _linearize(raw, "reason", method)

    async def resources() -> str:
        """List available graphs, VDBs, and other resources in the current session."""
        return await dms.list_available_resources()

    # Return the consolidated tool list
    tools = [
        entity_search,
        entity_traverse,
        entity_info,
        relationship_search,
        chunk_retrieve,
        subgraph_extract,
        community_search,
        reason,
        resources,
    ]

    # submit_answer with plan-completion enforcement.
    # If the agent has a todo list with incomplete atoms, reject the submission
    # and tell the agent to complete remaining atoms first.
    _original_submit = dms.submit_answer if hasattr(dms, "submit_answer") else None

    async def submit_answer(reasoning: str, answer: str) -> str:
        """Submit your final answer. Call once with your best answer.

        Submit as soon as you have an answer, even if some todo atoms are still pending.
        An imperfect answer is better than no answer — do not loop endlessly searching.
        If you have been searching for 4+ tool calls without completing all atoms, submit now.
        """
        if _original_submit:
            return await _original_submit(reasoning=reasoning, answer=answer)
        else:
            dms._reset_chunk_dedup()
            return _json.dumps({"status": "submitted", "answer": answer})

    tools.append(submit_answer)

    # Planning tools: semantic_plan (typed decomposition) and todo_write
    # (persistent progress tracking) give the agent working memory.
    # bridge_disambiguate helps with entity resolution ambiguity.
    for maybe_tool in ("semantic_plan", "todo_write", "bridge_disambiguate"):
        if hasattr(dms, maybe_tool):
            tools.append(getattr(dms, maybe_tool))

    return tools
