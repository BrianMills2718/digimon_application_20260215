#!/usr/bin/env python3
"""
DIGIMON MCP Server (stdio) for Claude Code

Exposes DIGIMON's KG-RAG tools via the official MCP protocol (stdio transport).
This allows Claude Code to act as the agent, calling tools directly.

Usage:
    python digimon_mcp_stdio_server.py

Add to ~/.claude/mcp_servers.json to use with Claude Code.
"""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
import os
import pickle
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# === MCP STDIO SAFETY: prevent ALL non-JSONRPC stdout writes ===
# litellm prints colored INFO/WARNING/ERROR to stdout via Python logging,
# direct print() calls, and Rich console handlers. This corrupts MCP stdio
# transport (JSONRPC over stdout). Must be done BEFORE any imports touch litellm.
#
# Fixed: 2026-02-15 — overnight benchmark failed because litellm's Gemini 429
# error body was printed line-by-line to stdout, creating 260K JSONRPC parse errors.

# 1. Force all Python logging to stderr at WARNING+ level
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, force=True)

# 2. Env vars to suppress litellm's own output mechanisms
os.environ["LITELLM_LOG"] = "ERROR"

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# 3. Import litellm early and suppress every output channel
try:
    import litellm
    litellm.suppress_debug_info = True  # Kills "Give Feedback" banner
    litellm.set_verbose = False         # Kills print_verbose() calls
    # Redirect all litellm-related Python loggers to stderr
    for logger_name in ("LiteLLM", "LiteLLM Proxy", "LiteLLM Router"):
        _ll = logging.getLogger(logger_name)
        _ll.handlers.clear()
        _handler = logging.StreamHandler(sys.stderr)
        _handler.setLevel(logging.ERROR)
        _ll.addHandler(_handler)
        _ll.propagate = False
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP
from Core.Common.entity_name_hygiene import classify_entity_name, score_entity_candidate
from Core.MCP.progressive_disclosure import (
    ALWAYS_LOADED_TOOLS,
    EXECUTE_CHAIN_TOOL_NAME,
    SEARCH_TOOL_NAME,
    DeferredToolRegistry,
    search_available_tools_impl,
    should_defer_tool,
)

logger = logging.getLogger(__name__)

# Benchmark mode levels:
#   0 / unset: all tools exposed (including build, pipeline shortcuts, etc.)
#   1+: prune non-retrieval tools (graph build, corpus_prepare, graph_analyze,
#        build_sparse_matrices, etc.)
#        — agent must compose operators individually
_bm_raw = os.environ.get("DIGIMON_BENCHMARK_MODE", "").strip().lower()
if _bm_raw in ("2",):
    BENCHMARK_MODE = 2
elif _bm_raw in ("1", "true", "yes"):
    BENCHMARK_MODE = 1
else:
    BENCHMARK_MODE = 0

# Progressive disclosure mode: only expose core tools + search, defer the rest.
# Activated via DIGIMON_PROGRESSIVE_DISCLOSURE=1. Without it, all tools exposed as today.
_pd_raw = os.environ.get("DIGIMON_PROGRESSIVE_DISCLOSURE", "").strip().lower()
PROGRESSIVE_DISCLOSURE = _pd_raw in ("1", "true", "yes")

# Singleton deferred tool registry — populated at entry point when disclosure is active.
_deferred_registry = DeferredToolRegistry()

# Tools hidden in benchmark mode. In benchmark, only retrieval + submit_answer are exposed.
# This list is checked after MCP server init to remove unnecessary tools.
_BENCHMARK_HIDDEN_TOOLS: set[str] = {
    # Community (no communities built for QA benchmarks)
    "community_detect_from_entities", "community_get_layer",
    # LLM wrapper agents (outer agent IS an LLM — these are redundant and waste budget)
    "entity_agent", "relationship_agent", "subgraph_agent_path",
    # Meta LLM wrappers (agent should reason directly, not delegate to inner LLM)
    "meta_extract_entities", "meta_generate_answer",
    "meta_decompose_question", "meta_synthesize_answers",
    # Config / discovery (redundant with prompt)
    "get_config", "set_agentic_model", "list_operators", "get_compatible_successors",
    "list_graph_types",
    # Cross-modal (not relevant for QA)
    "convert_modality", "validate_conversion", "select_analysis_mode",
    "list_modality_conversions",
    # Explicit wrappers are used in benchmark mode to avoid multi-mode ambiguity.
    "chunk_get_text",
}

# Additional aggressive pruning used by Codex compact benchmark profile.
# Keep only core retrieval/traversal + submit_answer path in this mode.
_BENCHMARK_HIDDEN_TOOLS_LEVEL2: set[str] = {
    "chunk_vdb_search",
    "relationship_vdb_search",
    "semantic_plan",
    "todo_write",
    "bridge_disambiguate",
    "entity_ppr",
    "relationship_score_aggregator",
    "chunk_occurrence",
    "chunk_aggregator",
    "subgraph_khop_paths",
    "subgraph_steiner_tree",
    "meta_pcst_optimize",
}

# Short descriptions for benchmark mode — the system prompt already explains
# tool usage in detail, so verbose docstrings in the schema are redundant tokens.
_BENCHMARK_SHORT_DESCS: dict[str, str] = {
    "entity_vdb_search": "Semantic vector search over entities.",
    "entity_onehop": "Get all neighbor entities of a given entity.",
    "entity_ppr": "Personalized PageRank from seed entities.",
    "entity_link": "Match entity names to graph nodes.",
    "entity_resolve_names_to_ids": "Resolve free-form entity names to canonical graph IDs.",
    "entity_profile": "Get canonical name, aliases, type, and evidence refs for one entity.",
    "entity_tfidf": "Find entities by TF-IDF keyword matching.",
    "relationship_onehop": "Get typed relationships for an entity.",
    "relationship_score_aggregator": "Aggregate entity scores into relationship scores.",
    "relationship_vdb_search": "Semantic vector search over relationships.",
    "chunk_from_relationships": "Get text chunks for given relationships.",
    "chunk_occurrence": "Find chunks where two entities co-occur.",
    "chunk_get_text_by_chunk_ids": "Get source text by explicit chunk IDs only.",
    "chunk_get_text_by_entity_ids": "Get source text for explicit entity IDs.",
    "extract_date_mentions": "Extract normalized date mentions with evidence refs from chunk text.",
    "chunk_text_search": "Keyword search over source text chunks.",
    "chunk_vdb_search": "Semantic vector search over source text chunks.",
    "entity_select_candidate": "Select canonical entity IDs from candidates (optional expected_coarse_types filter).",
    "search_then_expand_onehop": "Composite search->candidate->onehop expansion with bounded output.",
    "chunk_aggregator": "Score chunks by relationship/PPR scores via sparse matrices.",
    "subgraph_khop_paths": "Find all paths between entities within k hops.",
    "subgraph_steiner_tree": "Minimal subgraph connecting a set of entities.",
    "meta_pcst_optimize": "Prize-collecting Steiner tree optimization (algorithmic).",
    "list_available_resources": "List loaded graphs, VDBs, and sparse matrices.",
    "todo_write": "Replace full TODO list. Each item: id, content, status; done atoms need explicit answer/result and supporting evidence.",
    "semantic_plan": "Build typed semantic decomposition (atoms/dependencies/composition).",
    "bridge_disambiguate": "Choose best bridge entity from ambiguous candidates using downstream evidence.",
    "submit_answer": "Submit your final answer. Call once with your best answer.",
}

_ATOM_BRIDGE_MIN_CONFIDENCE = float(
    os.environ.get("DIGIMON_ATOM_BRIDGE_MIN_CONFIDENCE", "0.72")
)
_ATOM_BRIDGE_PROBE_MIN_TOTAL_SCORE = float(
    os.environ.get("DIGIMON_ATOM_BRIDGE_PROBE_MIN_TOTAL_SCORE", "6.0")
)
_ATOM_BRIDGE_PROBE_MIN_DOWNSTREAM_SCORE = float(
    os.environ.get("DIGIMON_ATOM_BRIDGE_PROBE_MIN_DOWNSTREAM_SCORE", "3.0")
)
_ATOM_BRIDGE_PROBE_MIN_SUBJECT_SCORE = float(
    os.environ.get("DIGIMON_ATOM_BRIDGE_PROBE_MIN_SUBJECT_SCORE", "2.0")
)
_ATOM_BRIDGE_PROBE_MIN_SCORE_GAP = float(
    os.environ.get("DIGIMON_ATOM_BRIDGE_PROBE_MIN_SCORE_GAP", "0.5")
)
_ATOM_BRIDGE_MAX_CANDIDATES = max(
    2, int(os.environ.get("DIGIMON_ATOM_BRIDGE_MAX_CANDIDATES", "6"))
)
_ENTITY_SUBJECT_AUTO_PROFILE_MIN_SCORE = float(
    os.environ.get("DIGIMON_ENTITY_SUBJECT_AUTO_PROFILE_MIN_SCORE", "90")
)
_QUERY_CONTRACT_BYPASS_REASON: ContextVar[str] = ContextVar(
    "digimon_query_contract_bypass_reason",
    default="",
)


@contextmanager
def _query_contract_bypass(reason: str) -> Any:
    """Temporarily disable active-atom query rewriting for internal probes."""
    token = _QUERY_CONTRACT_BYPASS_REASON.set(str(reason or "").strip())
    try:
        yield
    finally:
        _QUERY_CONTRACT_BYPASS_REASON.reset(token)


def _compact_tool_schemas() -> None:
    """Strip verbose descriptions and Pydantic title noise from tool schemas.

    Called in benchmark mode to cut tool definition tokens ~46%.
    """
    for tool in mcp._tool_manager._tools.values():
        # Replace verbose docstring with one-liner
        short = _BENCHMARK_SHORT_DESCS.get(tool.name)
        if short is not None:
            tool.description = short
        # Strip title fields from parameter schema
        params = tool.parameters
        if isinstance(params, dict):
            params.pop("title", None)
            for prop in params.get("properties", {}).values():
                if isinstance(prop, dict):
                    prop.pop("title", None)


async def _benchmark_visible_mcp_tool_names_for_current_env() -> tuple[list[str], str | None, list[str], list[str]]:
    """Compute the benchmark MCP tool surface for the current environment.

    Returns the visible tool names after benchmark pruning, manifest/runtime
    applicability filtering, and benchmark-mode-specific whitelists. This does
    not mutate the live MCP registry, so tests can compare the computed surface
    against other backends without starting a stdio server process.
    """

    from Core.Common.benchmark_tool_modes import filter_tool_names_for_benchmark_mode

    tool_names = [
        tool_name
        for tool_name in mcp._tool_manager._tools.keys()
        if tool_name not in _BENCHMARK_HIDDEN_TOOLS
    ]
    if BENCHMARK_MODE >= 2:
        tool_names = [
            tool_name
            for tool_name in tool_names
            if tool_name not in _BENCHMARK_HIDDEN_TOOLS_LEVEL2
        ]

    applicability_label: str | None = None
    unavailable_tool_names: list[str] = []
    degraded_tool_names: list[str] = []
    dataset_name = os.environ.get("DIGIMON_PRELOAD_DATASET", "").strip()
    if dataset_name:
        await _ensure_initialized()
        from eval.graph_manifest import (
            build_runtime_resource_snapshot_from_operator_context,
            evaluate_tool_names_by_graph_manifest,
            load_required_graph_manifest,
        )
        from Core.Common.tool_applicability import ToolApplicabilityStatus

        config = _state["config"]
        graph_type = getattr(getattr(config, "graph", None), "type", "er_graph")
        working_dir = str(getattr(config, "working_dir", "./results"))
        manifest = load_required_graph_manifest(
            dataset_name=dataset_name,
            graph_type=graph_type,
            working_dir=working_dir,
        )
        operator_ctx = await _build_operator_context_for_dataset(dataset_name)
        runtime_resources = build_runtime_resource_snapshot_from_operator_context(
            operator_ctx
        )
        decisions = evaluate_tool_names_by_graph_manifest(
            tool_names,
            manifest,
            runtime_resources,
        )
        unavailable_tool_names = [
            decision.tool_name
            for decision in decisions
            if decision.status is ToolApplicabilityStatus.UNAVAILABLE
        ]
        degraded_tool_names = [
            decision.tool_name
            for decision in decisions
            if decision.status is ToolApplicabilityStatus.DEGRADED
        ]
        tool_names = [
            tool_name for tool_name in tool_names if tool_name not in unavailable_tool_names
        ]
        applicability_label = f"{manifest.graph_type}/{manifest.graph_profile.value}"

    mode_name = os.environ.get("DIGIMON_BENCHMARK_MODE_NAME", "").strip()
    tool_names = filter_tool_names_for_benchmark_mode(tool_names, mode_name)
    return tool_names, applicability_label, unavailable_tool_names, degraded_tool_names


# Explicit mode boundaries for chunk_get_text to avoid silent branch selection.
_CHUNK_GET_TEXT_MODE_AUTO = "auto"
_CHUNK_GET_TEXT_MODE_BY_CHUNK_IDS = "chunk_ids"
_CHUNK_GET_TEXT_MODE_BY_ENTITY_IDS = "entity_ids"
_CHUNK_GET_TEXT_VALID_MODES = {
    _CHUNK_GET_TEXT_MODE_AUTO,
    _CHUNK_GET_TEXT_MODE_BY_CHUNK_IDS,
    _CHUNK_GET_TEXT_MODE_BY_ENTITY_IDS,
}


# --- Initialize MCP Server ---
mcp = FastMCP("digimon-kgrag", instructions="""
DIGIMON KG-RAG Tools: Build knowledge graphs from documents and query them.

## Core: 26 Typed Operators

DIGIMON's core value is 26 composable operators across 6 categories:
entity (7), relationship (4), chunk (3), subgraph (3), community (2), meta (7).
Each operator has typed I/O slots, cost tiers, and prerequisite flags.
Call `list_operators` for the full catalog, `get_compatible_successors` to explore chains.

## Operator Composition

Call operators directly to build custom retrieval DAGs. Use `list_operators` +
`get_compatible_successors` to discover valid chains. Typical flow:
corpus_prepare → graph_build_er → entity_vdb_build → entity_vdb_search →
relationship_onehop → chunk_occurrence → meta_generate_answer

The agent decides what to call based on the question and intermediate results.
There are no fixed pipelines — compose operators freely.

## Config

Two model roles: `llm.model` (graph building, cheap) vs `agentic_model`
(mid-pipeline reasoning — entity extraction, answer generation, iterative steps).
- `get_config` — inspect current models, paths
- `set_agentic_model` — override the reasoning model at runtime

## Graph Types (call list_graph_types for details)
- **er**: General-purpose entity-relationship graph.
- **rk**: Keyword-enriched relationships.
- **tree/tree_balanced**: Hierarchical clustering for summarization.
- **passage**: Passage-level nodes for document-centric retrieval.

## Cross-Modal Analysis
Convert between graph, table, and vector representations:
- `list_modality_conversions` — discover all 15 conversion paths
- `convert_modality` — convert data between modalities (graph/table/vector)
- `validate_conversion` — measure round-trip preservation quality
- `select_analysis_mode` — LLM recommends best modality for a research question

## Tips
- Call `list_available_resources` to see what graphs and VDBs exist.
- Graph building auto-prepares corpus if you pass `input_directory` (supports .txt, .md, .json, .jsonl, .csv, .pdf).
  Or call `corpus_prepare` manually first. VDB building requires a graph.
- Default graph build uses single-step extraction (entity types + descriptions).

State is maintained between calls via GraphRAGContext.
""")

# --- Global state (initialized lazily) ---
_state: Dict[str, Any] = {}


def _get_project_root() -> str:
    return str(Path(__file__).parent)


def _ensure_embedding_provider_initialized(reason: str = "") -> Any:
    """Initialize embedding provider on demand and attach it to shared context."""
    existing = _state.get("encoder")
    if existing is not None:
        return existing

    config = _state.get("config")
    context = _state.get("context")
    if config is None or context is None:
        raise RuntimeError("DIGIMON state must be initialized before embedding provider init.")

    from Core.Index.EmbeddingFactory import get_rag_embedding

    encoder = get_rag_embedding(config=config)
    _state["encoder"] = encoder
    context.embedding_provider = encoder

    if reason:
        logger.info("Initialized embedding provider on demand (%s)", reason)
    else:
        logger.info("Initialized embedding provider on demand")
    return encoder


async def _ensure_initialized():
    """Lazy initialization of DIGIMON components."""
    if "initialized" in _state:
        return

    project_root = _get_project_root()
    os.chdir(project_root)

    from Option.Config2 import Config
    from Core.Provider.LLMClientAdapter import LLMClientAdapter
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentSchema.context import GraphRAGContext

    config_path = os.path.join(project_root, "Option", "Config2.yaml")
    config = Config.from_yaml_file(config_path)

    # Optional runtime embedding overrides for benchmark stability/cost control.
    embed_model_override = os.environ.get("DIGIMON_EMBED_MODEL", "").strip()
    if embed_model_override:
        logger.warning(
            "Overriding embedding model via DIGIMON_EMBED_MODEL: %s -> %s",
            getattr(config.embedding, "model", None),
            embed_model_override,
        )
        config.embedding.model = embed_model_override

    embed_dims_override = os.environ.get("DIGIMON_EMBED_DIMENSIONS", "").strip()
    if embed_dims_override:
        try:
            parsed_dims = int(embed_dims_override)
            if parsed_dims > 0:
                logger.warning(
                    "Overriding embedding dimensions via DIGIMON_EMBED_DIMENSIONS: %s -> %d",
                    getattr(config.embedding, "dimensions", None),
                    parsed_dims,
                )
                config.embedding.dimensions = parsed_dims
        except ValueError:
            logger.warning(
                "Invalid DIGIMON_EMBED_DIMENSIONS=%r (expected positive integer). Ignoring override.",
                embed_dims_override,
            )

    fallback = getattr(config.llm, 'fallback_models', None) or []
    llm = LLMClientAdapter(
        config.llm.model,
        fallback_models=fallback,
        num_retries=3,
    )
    chunk_factory = ChunkFactory(config)

    context = GraphRAGContext(
        target_dataset_name="mcp_session",
        main_config=config,
        llm_provider=llm,
        embedding_provider=None,
        chunk_storage_manager=chunk_factory,
    )

    _state["config"] = config
    _state["llm"] = llm
    _state["encoder"] = None
    _state["chunk_factory"] = chunk_factory
    _state["context"] = context

    # Optional: create agentic LLM via llm_client for meta operators
    # Env var override: DIGIMON_AGENTIC_MODEL (useful for benchmarks to avoid recursive agent spawning)
    agentic_model = os.environ.get("DIGIMON_AGENTIC_MODEL") or getattr(config, "agentic_model", None)
    if agentic_model:
        config.agentic_model = agentic_model
        try:
            from Core.Provider.LLMClientAdapter import LLMClientAdapter
            _state["agentic_llm"] = LLMClientAdapter(agentic_model)
            logger.info(f"Agentic LLM initialized: {agentic_model}")
        except ImportError:
            logger.warning("llm_client not available — agentic_model ignored, using default LLM")

    _state["initialized"] = True

    # Auto-preload graph and VDB when running in benchmark mode.
    # Set DIGIMON_PRELOAD_DATASET=<dataset_name> to load pre-built artifacts on startup.
    preload_dataset = os.environ.get("DIGIMON_PRELOAD_DATASET", "").strip()
    if preload_dataset:
        logger.info(f"Pre-loading graph and VDB for dataset '{preload_dataset}'")
        try:
            await graph_build_er(preload_dataset)
            graph_id = f"{preload_dataset}_ERGraph"
            vdb_name = f"{preload_dataset}_entities"
            skip_vdb_preload = os.environ.get("DIGIMON_SKIP_VDB_PRELOAD", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if skip_vdb_preload:
                logger.warning(
                    "Skipping VDB preload/build due to DIGIMON_SKIP_VDB_PRELOAD=1 "
                    "(graph remains loaded)."
                )
                return

            # Load VDBs from disk if they exist, rebuild only if needed
            from Core.Index.FaissIndex import FaissIndex
            from Core.AgentTools.index_config_helper import create_faiss_index_config
            _ensure_embedding_provider_initialized(
                reason=f"benchmark preload for dataset '{preload_dataset}'"
            )
            target_dim = getattr(context.embedding_provider, "dimensions", None)

            for vdb_id in [vdb_name, f"{preload_dataset}_chunks"]:
                should_rebuild = False
                vdb_path = Path(f"storage/vdb/{vdb_id}")
                if vdb_path.exists() and any(vdb_path.iterdir()):
                    try:
                        cfg = create_faiss_index_config(
                            persist_path=str(vdb_path),
                            embed_model=context.embedding_provider,
                            name=vdb_id,
                        )
                        vdb = FaissIndex(cfg)
                        loaded = await vdb.load()
                        if loaded:
                            loaded_dim = _vdb_index_dimension(vdb)
                            if (
                                isinstance(target_dim, int)
                                and target_dim > 0
                                and isinstance(loaded_dim, int)
                                and loaded_dim > 0
                                and loaded_dim != target_dim
                            ):
                                should_rebuild = True
                                logger.warning(
                                    "VDB dim mismatch for %s: index_dim=%s, embed_dim=%s. Rebuilding.",
                                    vdb_id,
                                    loaded_dim,
                                    target_dim,
                                )
                            else:
                                context.add_vdb_instance(vdb_id, vdb)
                                logger.info(f"Pre-loaded VDB from disk: {vdb_id}")
                                continue
                    except Exception as ve:
                        logger.warning(f"VDB disk load failed for {vdb_id}: {ve}")
                        should_rebuild = True

                # Rebuild if disk load failed or didn't exist
                if "entities" in vdb_id:
                    await entity_vdb_build(graph_id, vdb_id, force_rebuild=should_rebuild)
                elif "chunks" in vdb_id:
                    await chunk_vdb_build(
                        preload_dataset,
                        vdb_collection_name=vdb_id,
                        force_rebuild=should_rebuild,
                    )

            logger.info(f"Pre-loaded: graph={graph_id}, VDBs loaded from disk")
        except Exception as e:
            logger.warning(f"Pre-load failed for '{preload_dataset}': {e}")


def _format_result(result: Any) -> str:
    """Convert tool output to readable string, deduplicating chunk text."""
    if hasattr(result, "model_dump"):
        d = result.model_dump(exclude_none=True, exclude={"graph_instance"})
    elif isinstance(result, dict):
        d = result
    else:
        return str(result)

    # Walk the dict and dedup any chunk-like entries
    _dedup_chunks_in_dict(d)
    return json.dumps(d, indent=2, default=str)


_COOCCURRENCE_CAP_PER_ENTITY = 8
"""Max cooccurrence edges shown per entity in compact relationship output."""

_DATE_NUMBER_TARGET_RE = re.compile(
    r"^(?:\d{3,4}|(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b.*|\d+(?:st|nd|rd|th)\b.*)$",
    flags=re.IGNORECASE,
)


def _cooc_snippet(chunk_ref: str, src: str, tgt: str) -> str:
    """Extract a short context snippet around a cooccurrence target from cached chunk text.

    For date/number cooccurrence targets, shows the sentence containing the target
    so the model can understand what the date/number means in context.
    """
    text = _seen_chunk_text.get(chunk_ref, "")
    if not text:
        return ""
    tgt_lower = tgt.lower()
    text_lower = text.lower()
    idx = text_lower.find(tgt_lower)
    if idx < 0:
        return ""
    # Find sentence boundaries around the target mention
    start = max(0, text.rfind(".", 0, idx) + 1)
    end = text.find(".", idx + len(tgt))
    if end < 0:
        end = min(len(text), idx + 120)
    else:
        end = min(end + 1, len(text))
    snippet = text[start:end].strip()
    if len(snippet) > 150:
        snippet = snippet[:147] + "..."
    return snippet


def _format_relationship_onehop(result: Any) -> str:
    """Compact formatter for relationship_onehop results.

    Groups edges by source entity, sorts extracted relations (high weight,
    with descriptions) before cooccurrence edges, and caps low-signal
    cooccurrence at _COOCCURRENCE_CAP_PER_ENTITY per entity.

    For cooccurrence edges to date/number targets, includes a context snippet
    from the source chunk so the model can interpret the relationship.

    Typical reduction: 20-50K chars → 1-3K chars (10-20x).
    """
    if hasattr(result, "model_dump"):
        d = result.model_dump(exclude_none=True, exclude={"graph_instance"})
    elif isinstance(result, dict):
        d = result
    else:
        return str(result)

    edges = d.get("one_hop_relationships")
    if not isinstance(edges, list) or not edges:
        return json.dumps(d, indent=2, default=str)

    # Group by source entity
    by_src: Dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        src = str(e.get("src_id", "?"))
        by_src.setdefault(src, []).append(e)

    lines: list[str] = []
    for src, group in by_src.items():
        # Extracted relations first (high weight), then cooccurrence
        group.sort(key=lambda e: (-e.get("weight", 0), e.get("tgt_id", "")))
        lines.append(f"[{src}]")
        cooc_count = 0
        cooc_total = sum(
            1 for e in group
            if e.get("relation_name") == "chunk_cooccurrence"
        )
        for e in group:
            tgt = str(e.get("tgt_id", "?"))
            desc = (e.get("description") or "").strip()
            weight = e.get("weight", 0)
            is_cooc = e.get("relation_name") == "chunk_cooccurrence"
            chunk_ref = ""
            attrs = e.get("attributes")
            if isinstance(attrs, dict):
                chunk_ref = str(attrs.get("source_id", ""))
            if is_cooc:
                cooc_count += 1
                if cooc_count > _COOCCURRENCE_CAP_PER_ENTITY:
                    continue
            ref_part = f" [{chunk_ref}]" if chunk_ref else ""
            # For cooccurrence edges to date/number targets, add context snippet
            # or flag so the model knows to investigate
            snippet_part = ""
            if is_cooc and _DATE_NUMBER_TARGET_RE.match(tgt) and chunk_ref:
                snippet = _cooc_snippet(chunk_ref, src, tgt)
                if snippet:
                    snippet_part = f" ctx=\"{snippet}\""
                else:
                    snippet_part = f" ⚑date/number — check {chunk_ref}"
            if desc:
                lines.append(f"  → {tgt} (w={weight}) \"{desc}\"{ref_part}")
            elif weight > 0.5:
                lines.append(f"  → {tgt} (w={weight}){ref_part}")
            else:
                lines.append(f"  → {tgt}{ref_part}{snippet_part}")
        omitted = cooc_total - min(cooc_total, _COOCCURRENCE_CAP_PER_ENTITY)
        if omitted > 0:
            lines.append(f"  ... +{omitted} more cooccurrence edges")

    return "\n".join(lines)


def _dedup_chunks_in_dict(d: dict) -> None:
    """In-place dedup of chunk text in a result dict.

    Looks for lists of dicts containing chunk_id + text/content fields
    and replaces repeated text with a reference.
    """
    TEXT_KEYS = ("text", "text_content", "content")
    for key, value in d.items():
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            chunk_id = item.get("chunk_id")
            if not chunk_id:
                continue
            for tk in TEXT_KEYS:
                if tk in item and item[tk]:
                    is_new, text = _dedup_chunk(chunk_id, item[tk])
                    item[tk] = text
                    break


# ---------------------------------------------------------------------------
# Session-scoped chunk dedup — avoids repeating full text for chunks the agent
# has already seen in this conversation.
# ---------------------------------------------------------------------------

_seen_chunks: dict[str, str] = {}  # chunk_id -> first 80 chars (for reference)
_seen_chunk_text: dict[str, str] = {}  # chunk_id -> full text (for evidence validation)
_chunk_entity_index_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}
_latest_entity_candidates_by_chunk: dict[str, list[dict[str, Any]]] = {}
_latest_entity_candidates_flat: list[dict[str, Any]] = []
_todos: list[dict[str, Any]] = []  # question-local TODOs in benchmark mode
_current_question: str = ""
_current_expected_answer_kind: str = ""
_current_semantic_plan: dict[str, Any] = {}
_current_semantic_plan_question: str = ""
_atom_lifecycle_events: list[dict[str, Any]] = []
_atom_validation_payloads: dict[str, list[dict[str, Any]]] = {}
_QUERY_LEADIN_RE = re.compile(
    r"^\s*(?:find|identify|determine|lookup|look up|resolve|show me|tell me|"
    r"what(?:'s| is| was)?|who(?:'s| is| was)?|when(?:'s| is| was| did)?|"
    r"where(?:'s| is| was)?|which)\b[:\s-]*",
    flags=re.IGNORECASE,
)
_QUERY_PLACEHOLDER_RE = re.compile(
    r"\b(?:that|this|these|those|it|its|their|his|her|them|there|then)\b",
    flags=re.IGNORECASE,
)
_QUERY_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/-]*")
_QUERY_STOPWORDS = {
    "a", "an", "and", "at", "by", "for", "from", "how", "in", "into", "of",
    "on", "or", "the", "to", "was", "were", "when", "where", "which", "who",
}

def _dedup_chunk(chunk_id: str, text: str) -> tuple[bool, str]:
    """Track a chunk. Returns (is_new, text_or_reference).

    If the chunk was already returned in this session, returns a short reference
    instead of the full text so the agent knows it exists but doesn't waste
    context window on repeated content.
    """
    if chunk_id in _seen_chunks:
        preview = _seen_chunks[chunk_id]
        return False, (
            f"[DUPLICATE — you already have this chunk. "
            f"Content: {preview!r}... "
            f"DO NOT search again. Try entity_onehop or entity_vdb_search instead, "
            f"or submit your answer.]"
        )
    _seen_chunks[chunk_id] = text[:80]
    _seen_chunk_text[chunk_id] = text or ""
    return True, text


def _compact_chunk_text_for_prompt(text: str, *, max_chars: int = 1200) -> tuple[str, bool]:
    """Return bounded chunk text for prompt efficiency while retaining full cache."""
    if not isinstance(text, str):
        return str(text), False
    if text.startswith("[DUPLICATE"):
        return text, False
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    compact = text[:max_chars].rstrip()
    return (
        compact + " ... [truncated; use chunk_get_text_by_chunk_ids for full text]",
        True,
    )


def _reset_chunk_dedup() -> None:
    """Reset seen chunks and per-question state — call between questions."""
    global _latest_entity_candidates_flat
    _seen_chunks.clear()
    _seen_chunk_text.clear()
    _latest_entity_candidates_by_chunk.clear()
    _latest_entity_candidates_flat = []
    # Reset submit_answer warning flag for next question
    if BENCHMARK_MODE and hasattr(globals().get("submit_answer", None), "_warned_once"):
        submit_answer._warned_once = False  # type: ignore[attr-defined]
    _reset_todos()
    _clear_semantic_plan()


def _reset_todos() -> None:
    """Reset TODO state — call between questions."""
    global _current_question, _current_expected_answer_kind
    _todos.clear()
    _atom_lifecycle_events.clear()
    _atom_validation_payloads.clear()
    _current_question = ""
    _current_expected_answer_kind = ""


def _clear_semantic_plan() -> None:
    """Clear semantic-plan contract state for current question."""
    global _current_semantic_plan_question
    _current_semantic_plan.clear()
    _current_semantic_plan_question = ""


def _todo_summary() -> dict[str, int]:
    """Return TODO counts by status."""
    counts = {"pending": 0, "in_progress": 0, "blocked": 0, "done": 0}
    for item in _todos:
        st = item.get("status")
        if st in counts:
            counts[st] += 1
    return counts


def _pending_todo_ids_for_submit() -> list[str]:
    """Return semantic-plan TODO IDs that still block final answer submission."""
    pending_ids: list[str] = []
    for item in _todos:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        if status not in {"pending", "in_progress", "blocked"}:
            continue
        todo_id = str(item.get("id") or "").strip()
        if todo_id:
            pending_ids.append(todo_id)
    return pending_ids


def _semantic_plan_atom_by_id(atom_id: str) -> dict[str, Any] | None:
    """Lookup semantic-plan atom by atom_id."""
    aid = (atom_id or "").strip()
    if not aid:
        return None
    atoms = _current_semantic_plan.get("atoms")
    if not isinstance(atoms, list):
        return None
    for atom in atoms:
        if isinstance(atom, dict) and (atom.get("atom_id") or "").strip() == aid:
            return atom
    return None


def _todo_item_by_id(todo_id: str) -> dict[str, Any] | None:
    """Return the current TODO item for a given ID, if present."""
    tid = (todo_id or "").strip()
    if not tid:
        return None
    for item in _todos:
        if isinstance(item, dict) and (item.get("id") or "").strip() == tid:
            return item
    return None


def _normalize_query_compare_text(text: str) -> str:
    """Normalize a query string for token-overlap comparisons."""
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _query_token_overlap(left: str, right: str) -> float:
    """Return Jaccard overlap between normalized token sets."""
    left_tokens = set(_normalize_query_compare_text(left).split())
    right_tokens = set(_normalize_query_compare_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens.intersection(right_tokens)) / len(left_tokens.union(right_tokens))


def _compact_search_query(text: str) -> str:
    """Strip question wrappers so retrieval queries focus on informative terms."""
    candidate = _QUERY_LEADIN_RE.sub("", (text or "").strip())
    candidate = _QUERY_PLACEHOLDER_RE.sub(" ", candidate)
    candidate = re.sub(r"[^\w\s'/-]+", " ", candidate)
    tokens = [token.strip() for token in candidate.split() if token.strip()]
    filtered = [token for token in tokens if token.lower() not in _QUERY_STOPWORDS]
    compact = " ".join(filtered or tokens)
    return re.sub(r"\s+", " ", compact).strip(" ?.-")


def _extract_todo_result_value(item: dict[str, Any] | None) -> str:
    """Extract a compact resolved value from a completed TODO item."""
    if not isinstance(item, dict):
        return ""
    for key in ("answer", "result", "resolved_value", "value", "output"):
        raw = item.get(key)
        if isinstance(raw, (list, tuple)):
            value = ", ".join(str(part).strip() for part in raw if str(part).strip())
        else:
            value = str(raw or "").strip()
        if value:
            return value

    content = str(item.get("content") or item.get("task") or "").strip()
    for pattern in (
        r"(?:=>|->|=)\s*(?P<value>[^|;]+)$",
        r":\s*(?P<value>[A-Z0-9][^|;]+)$",
    ):
        match = re.search(pattern, content)
        if not match:
            continue
        value = match.group("value").strip()
        if value:
            return value
    return ""


def _active_semantic_plan_atom() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the active semantic-plan atom and its TODO item."""
    atoms = _current_semantic_plan.get("atoms")
    if not isinstance(atoms, list) or not atoms:
        return None, None

    for status in ("in_progress", "pending"):
        for todo in _todos:
            if not isinstance(todo, dict) or todo.get("status") != status:
                continue
            atom = _semantic_plan_atom_by_id(str(todo.get("id") or ""))
            if atom is not None:
                return atom, todo

    done_ids = {
        str(todo.get("id") or "").strip()
        for todo in _todos
        if isinstance(todo, dict) and todo.get("status") == "done"
    }
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        atom_id = str(atom.get("atom_id") or "").strip()
        if atom_id and atom_id not in done_ids:
            return atom, _todo_item_by_id(atom_id)
    return None, None


def _resolved_dependency_values(atom: dict[str, Any] | None) -> list[str]:
    """Collect resolved values for dependencies of the active atom."""
    if not isinstance(atom, dict):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for dep_id in atom.get("depends_on") or []:
        todo = _todo_item_by_id(str(dep_id))
        if not todo or todo.get("status") != "done":
            continue
        value = _extract_todo_result_value(todo)
        if not value:
            continue
        norm = value.casefold()
        if norm in seen:
            continue
        seen.add(norm)
        values.append(value)
    return values


def _normalize_resolved_value(value: Any) -> str:
    """Normalize short factual spans for equality checks."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def _store_atom_validation_payload(
    atom: dict[str, Any] | None,
    payload: dict[str, Any],
    *,
    tool_name: str,
    method: str,
) -> None:
    """Store compact recent evidence for later manual TODO validation."""
    if not isinstance(atom, dict) or not isinstance(payload, dict):
        return
    atom_id = str(atom.get("atom_id") or "").strip()
    if not atom_id:
        return

    stored: dict[str, Any] = {
        "tool_name": tool_name,
        "method": method,
    }
    for key in (
        "query_contract",
        "canonical_name",
        "entity_id",
        "resolved_graph_reference_id",
        "resolved_dataset_name",
        "entity_scope_contract",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            stored[key] = value

    refs = _extract_evidence_refs(payload)
    if refs:
        stored["evidence_refs"] = refs

    chunks = payload.get("chunks")
    if isinstance(chunks, list):
        compact_chunks: list[dict[str, Any]] = []
        for chunk in chunks[:5]:
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get("text") or chunk.get("text_content") or chunk.get("content") or "").strip()
            compact_chunks.append(
                {
                    "chunk_id": str(chunk.get("chunk_id") or "").strip(),
                    "text": text,
                }
            )
        if compact_chunks:
            stored["chunks"] = compact_chunks

    relationships = payload.get("relationships")
    if not isinstance(relationships, list):
        relationships = payload.get("one_hop_relationships")
    if isinstance(relationships, list):
        compact_relationships: list[dict[str, Any]] = []
        for rel in relationships[:8]:
            if not isinstance(rel, dict):
                continue
            compact_relationships.append(
                {
                    "src_id": rel.get("src_id") or rel.get("source") or rel.get("source_id"),
                    "tgt_id": rel.get("tgt_id") or rel.get("target") or rel.get("target_id"),
                    "description": rel.get("description") or rel.get("relationship_description") or rel.get("text") or "",
                }
            )
        if compact_relationships:
            stored["relationships"] = compact_relationships

    for key in ("matches", "resolved_entities", "similar_entities", "connected_entities", "neighbors", "ranked_entities"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            stored[key] = value[:8]

    signature = json.dumps(stored, sort_keys=True, ensure_ascii=False, default=str)
    bucket = _atom_validation_payloads.setdefault(atom_id, [])
    for idx, existing in enumerate(bucket):
        existing_signature = json.dumps(existing, sort_keys=True, ensure_ascii=False, default=str)
        if existing_signature == signature:
            bucket.pop(idx)
            break
    bucket.append(stored)
    if len(bucket) > 6:
        del bucket[:-6]


def _fallback_manual_validation_payload(atom: dict[str, Any]) -> dict[str, Any] | None:
    """Build a chunk-focused payload when no structured atom payload was cached."""
    dependency_values = _resolved_dependency_values(atom)
    ranked_chunks: list[dict[str, Any]] = []
    for chunk_id, text in _seen_chunk_text.items():
        chunk = {"chunk_id": chunk_id, "text": text}
        ranked_chunks.append(chunk)
    ranked_chunks.sort(
        key=lambda chunk: -_chunk_relevance_score_for_atom(
            chunk,
            atom=atom,
            dependency_values=dependency_values,
        )
    )
    if not ranked_chunks:
        return None
    effective_query, query_contract = _build_retrieval_query_contract(
        str(atom.get("sub_question") or ""),
        tool_name="todo_write",
    )
    return {
        "tool_name": "todo_write",
        "method": "manual_fallback",
        "chunks": ranked_chunks[:5],
        "evidence_refs": [str(chunk.get("chunk_id") or "").strip() for chunk in ranked_chunks[:5] if str(chunk.get("chunk_id") or "").strip()],
        "query_contract": {
            **query_contract,
            "effective_query": effective_query,
        },
    }


def _next_dependent_atom(atom: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the next pending/in-progress atom that directly depends on this atom."""
    if not isinstance(atom, dict):
        return None
    atom_id = str(atom.get("atom_id") or "").strip()
    if not atom_id:
        return None
    atoms = _current_semantic_plan.get("atoms")
    if not isinstance(atoms, list):
        return None
    for candidate in atoms:
        if not isinstance(candidate, dict):
            continue
        depends_on = [str(dep).strip() for dep in (candidate.get("depends_on") or [])]
        if atom_id not in depends_on:
            continue
        todo = _todo_item_by_id(str(candidate.get("atom_id") or ""))
        if todo and todo.get("status") in {"pending", "in_progress"}:
            return candidate
    return None


def _bridge_candidate_names(payload: dict[str, Any], *, current_atom: dict[str, Any]) -> list[str]:
    """Extract candidate bridge entities from structured payload fields."""
    candidates: list[str] = []
    seen: set[str] = set()
    current_atom_text = " ".join(
        part.strip().casefold()
        for part in (
            str(current_atom.get("sub_question") or ""),
            str(payload.get("canonical_name") or ""),
            str(payload.get("entity_id") or ""),
        )
        if part and part.strip()
    )

    def _maybe_add(value: Any) -> None:
        candidate = str(value or "").strip()
        if not candidate:
            return
        lowered = candidate.casefold()
        if lowered in seen:
            return
        if lowered.startswith("chunk_") or lowered.startswith("passage_"):
            return
        if re.fullmatch(r"[0-9][0-9/ -]*", candidate):
            return
        if len(candidate) > 64:
            return
        if lowered and lowered in current_atom_text:
            return
        seen.add(lowered)
        candidates.append(candidate)

    for key in ("connected_entities", "neighbors"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _maybe_add(
                        item.get("canonical_name")
                        or item.get("resolved_entity_name")
                        or item.get("entity_name")
                        or item.get("entity_id")
                    )
                else:
                    _maybe_add(item)

    relationships = payload.get("relationships")
    if not isinstance(relationships, list):
        relationships = payload.get("one_hop_relationships")
    if isinstance(relationships, list):
        canonical_name = str(payload.get("canonical_name") or "").strip().casefold()
        entity_id = str(payload.get("entity_id") or "").strip().casefold()
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            src = str(rel.get("src_id") or rel.get("source") or rel.get("source_id") or "").strip()
            tgt = str(rel.get("tgt_id") or rel.get("target") or rel.get("target_id") or "").strip()
            for endpoint in (src, tgt):
                endpoint_norm = endpoint.casefold()
                if endpoint_norm and endpoint_norm not in {canonical_name, entity_id}:
                    _maybe_add(endpoint)

    return candidates[:_ATOM_BRIDGE_MAX_CANDIDATES]


def _best_entity_search_match(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the top structured entity-search match when present."""
    matches = payload.get("matches") or payload.get("resolved_entities") or payload.get("similar_entities")
    if not isinstance(matches, list) or not matches:
        return None
    best = matches[0]
    if not isinstance(best, dict):
        return None
    return best


def _ordered_subject_focus_tokens(atom: dict[str, Any] | None) -> list[str]:
    """Extract subject-bearing atom tokens while preserving question order."""
    if not isinstance(atom, dict):
        return []
    blocked = {
        "what",
        "when",
        "where",
        "which",
        "who",
        "whose",
        "birthplace",
        "born",
        "abolished",
        "identified",
        "entity",
        "place",
        "location",
    }
    tokens = _signal_tokens(str(atom.get("sub_question") or ""))
    return [token for token in tokens if token not in blocked]


def _subject_focus_tokens(atom: dict[str, Any] | None) -> set[str]:
    """Extract the subject-bearing tokens from an atom question."""
    return set(_ordered_subject_focus_tokens(atom))


def _best_entity_search_match_for_atom(
    payload: dict[str, Any],
    *,
    atom: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Prefer entity-search matches that align with the current atom's subject mention."""
    matches = payload.get("matches") or payload.get("resolved_entities") or payload.get("similar_entities")
    if not isinstance(matches, list) or not matches:
        return None

    subject_tokens = _subject_focus_tokens(atom)
    ranked: list[tuple[int, int, int, int, float, str, dict[str, Any]]] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("canonical_name")
            or item.get("entity_name")
            or item.get("resolved_entity_name")
            or item.get("entity_id")
            or ""
        ).strip()
        if not name:
            continue
        description = str(item.get("description") or item.get("short_description") or "").strip()
        name_tokens = _signal_tokens(name)
        description_tokens = _signal_tokens(description)
        overlap = len(subject_tokens.intersection(name_tokens))
        description_overlap = len(subject_tokens.intersection(description_tokens))
        exact_subject_match = int(bool(subject_tokens) and subject_tokens.issubset(name_tokens))
        nonempty_name = int(bool(name_tokens))
        base_score = float(item.get("match_score") or item.get("score") or 0.0)
        ranked.append(
            (
                exact_subject_match,
                overlap,
                description_overlap,
                nonempty_name,
                base_score,
                name,
                item,
            )
        )

    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], -item[4], item[5]))
    return ranked[0][6]


def _dataset_name_from_graph_reference(graph_reference_id: str) -> str:
    """Derive dataset name from the canonical graph reference ID."""
    dataset_name = str(graph_reference_id or "").strip()
    for suffix in ("_ERGraph", "_RKGraph", "_TreeGraphBalanced", "_TreeGraph", "_PassageGraph"):
        if dataset_name.endswith(suffix):
            return dataset_name[: -len(suffix)]
    return dataset_name


def _build_retrieval_query_contract(
    requested_query: str,
    *,
    tool_name: str,
) -> tuple[str, dict[str, Any]]:
    """Rewrite retrieval queries to the active atom and forward dependency values."""
    requested = (requested_query or "").strip()
    atom, todo = _active_semantic_plan_atom()
    contract: dict[str, Any] = {
        "tool_name": tool_name,
        "requested_query": requested,
        "effective_query": requested,
        "rewritten": False,
        "rewrite_reason": [],
        "active_atom_id": "",
        "active_atom_sub_question": "",
        "active_atom_status": "",
        "dependency_values_used": [],
    }
    if atom is None:
        return requested, contract

    bypass_reason = _QUERY_CONTRACT_BYPASS_REASON.get().strip()
    if bypass_reason:
        contract["rewrite_reason"] = [f"internal_bypass:{bypass_reason}"]
        return requested, contract

    atom_id = str(atom.get("atom_id") or "").strip()
    atom_query = str(atom.get("sub_question") or "").strip()
    active_status = str((todo or {}).get("status") or "").strip()
    dependency_values = _resolved_dependency_values(atom)
    contract.update(
        {
            "active_atom_id": atom_id,
            "active_atom_sub_question": atom_query,
            "active_atom_status": active_status,
            "dependency_values_used": dependency_values,
        }
    )

    effective = requested
    reasons: list[str] = []
    preserve_explicit_entity_query = (
        (tool_name == "entity_search" or tool_name.startswith("entity_"))
        and bool(requested)
        and _query_token_overlap(requested, _current_question) < 0.75
    )
    if atom_query and (not effective or _query_token_overlap(effective, _current_question) >= 0.75):
        effective = atom_query
        reasons.append("full_question_rewritten_to_active_atom")

    if not effective and atom_query:
        effective = atom_query
        reasons.append("empty_query_rewritten_to_active_atom")

    if atom_query and effective and _query_token_overlap(effective, atom_query) < 0.45 and not preserve_explicit_entity_query:
        effective = atom_query
        reasons.append("off_atom_query_rewritten_to_active_atom")

    if dependency_values:
        query_mentions_dependency = any(
            _normalize_query_compare_text(dep) in _normalize_query_compare_text(effective)
            for dep in dependency_values
        )
        if not query_mentions_dependency:
            focus = _compact_search_query(effective or atom_query or requested)
            dep_prefix = " ".join(dependency_values[:2])
            effective = f"{dep_prefix} {focus}".strip()
            reasons.append("dependency_values_forwarded")

    compact_effective = _compact_search_query(effective or atom_query or requested)
    if compact_effective and _normalize_query_compare_text(compact_effective) != _normalize_query_compare_text(effective):
        effective = compact_effective
        reasons.append("query_compacted_for_search")

    contract["effective_query"] = effective
    contract["rewrite_reason"] = reasons
    contract["rewritten"] = bool(
        reasons and _normalize_query_compare_text(effective) != _normalize_query_compare_text(requested)
    )
    return effective, contract


def _todo_status_line() -> str:
    """Compact one-line TODO status for state injection into agent context.

    Format: [TODO: 2/4 done] [x] a1: designer → Ralph | [>] a2: death city | [ ] a3: body of water
    """
    if not _todos:
        return "[TODO: no items]"
    done_count = sum(1 for t in _todos if t.get("status") == "done")
    total = len(_todos)
    parts: list[str] = []
    for t in _todos:
        status = t.get("status", "pending")
        tid = t.get("id", "?")
        content = (t.get("content") or t.get("task") or "").strip()
        if len(content) > 40:
            content = content[:37] + "..."
        resolved = _extract_todo_result_value(t)
        if status == "done" and resolved:
            resolved = resolved[:30] + "..." if len(resolved) > 33 else resolved
            content = f"{content} -> {resolved}"
        if status == "done":
            marker = "[x]"
        elif status == "in_progress":
            marker = "[>]"
        elif status == "blocked":
            marker = "[!]"
        else:
            marker = "[ ]"
        parts.append(f"{marker} {tid}: {content}")
    items = " | ".join(parts)
    return f"[TODO: {done_count}/{total} done] {items}"


def _record_atom_lifecycle_event(event: dict[str, Any]) -> None:
    """Append an atom lifecycle event and mirror it to a JSONL log."""
    payload = dict(event)
    payload.setdefault("question", _current_question)
    payload.setdefault("todo_status_line", _todo_status_line())
    _atom_lifecycle_events.append(payload)
    try:
        os.makedirs("results", exist_ok=True)
        with open("results/.atom_lifecycle_events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("Failed to persist atom lifecycle event", exc_info=True)


def _todo_dependencies_satisfied(atom: dict[str, Any] | None) -> bool:
    """Return True when all declared dependencies are marked done."""
    if not isinstance(atom, dict):
        return False
    for dep_id in atom.get("depends_on") or []:
        dep_todo = _todo_item_by_id(str(dep_id))
        if not dep_todo or dep_todo.get("status") != "done":
            return False
    return True


def _promote_next_ready_atom() -> dict[str, Any] | None:
    """Mark the next dependency-ready pending atom as in_progress."""
    atoms = _current_semantic_plan.get("atoms")
    if not isinstance(atoms, list):
        return None
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        atom_id = str(atom.get("atom_id") or "").strip()
        todo = _todo_item_by_id(atom_id)
        if not todo or todo.get("status") != "pending":
            continue
        if not _todo_dependencies_satisfied(atom):
            continue
        todo["status"] = "in_progress"
        event = {
            "event": "atom_promoted",
            "atom_id": atom_id,
            "sub_question": atom.get("sub_question"),
        }
        _record_atom_lifecycle_event(event)
        return event
    return None


def _extract_evidence_refs(payload: dict[str, Any]) -> list[str]:
    """Collect compact evidence references from a tool payload."""
    refs: list[str] = []
    seen: set[str] = set()

    def _maybe_add(value: Any) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        refs.append(text)

    for key in ("chunk_ids", "evidence_refs"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value[:5]:
                _maybe_add(item)

    for list_key in ("chunks", "relationships", "one_hop_relationships", "resolved_entities", "matches", "similar_entities"):
        items = payload.get(list_key)
        if not isinstance(items, list):
            continue
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            for key in ("chunk_id", "relationship_id", "resolved_entity_id", "entity_id", "entity_name"):
                if key in item:
                    _maybe_add(item.get(key))
    return refs[:5]


def _chunk_relevance_score_for_atom(
    chunk: dict[str, Any],
    *,
    atom: dict[str, Any] | None,
    dependency_values: list[str] | None,
) -> float:
    """Prioritize chunk evidence that matches the downstream predicate, not just the subject."""
    text = str(chunk.get("text") or chunk.get("text_content") or chunk.get("content") or "").lower()
    if not text:
        return 0.0

    score = 0.0
    for value in dependency_values or []:
        normalized = str(value or "").strip().lower()
        if normalized and normalized in text:
            score += 2.0

    atom_text = str((atom or {}).get("sub_question") or "").lower()
    if "abolish" in atom_text or "abolition" in atom_text or "dissolv" in atom_text:
        endpoint_markers = (
            "abolish",
            "abolition",
            "abolished",
            "ceased",
            "ended",
            "dissolved",
            "annexed",
            "authority",
            "deprived",
            "succeeded",
        )
        if any(marker in text for marker in endpoint_markers):
            score += 2.5

    if re.search(r"\b\d{3,4}\b", text):
        score += 1.5
    return score


def _build_atom_completion_evidence(
    payload: dict[str, Any],
    *,
    tool_name: str,
    method: str,
    atom: dict[str, Any] | None = None,
    dependency_values: list[str] | None = None,
) -> str:
    """Linearize a tool payload into compact evidence for atom completion."""
    lines: list[str] = []
    refs = _extract_evidence_refs(payload)
    if refs:
        lines.append(f"Evidence refs: {', '.join(refs)}")

    chunks = payload.get("chunks")
    if isinstance(chunks, list):
        ranked_chunks = sorted(
            [chunk for chunk in chunks if isinstance(chunk, dict)],
            key=lambda chunk: -_chunk_relevance_score_for_atom(
                chunk,
                atom=atom,
                dependency_values=dependency_values,
            ),
        )
        for chunk in ranked_chunks[:3]:
            if not isinstance(chunk, dict):
                continue
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            text = str(chunk.get("text") or chunk.get("text_content") or chunk.get("content") or "").strip()
            if text:
                lines.append(f"[{chunk_id or 'chunk'}] {text[:800]}")

    relationships = payload.get("relationships")
    if not isinstance(relationships, list):
        relationships = payload.get("one_hop_relationships")
    if isinstance(relationships, list):
        for rel in relationships[:8]:
            if not isinstance(rel, dict):
                continue
            src = rel.get("src_id") or rel.get("source") or rel.get("source_id")
            tgt = rel.get("tgt_id") or rel.get("target") or rel.get("target_id")
            desc = rel.get("description") or rel.get("relationship_description") or rel.get("text") or ""
            if src or tgt or desc:
                lines.append(f"REL {src} -> {tgt}: {desc}".strip())

    for key in ("resolved_entities", "matches", "similar_entities", "connected_entities", "neighbors", "ranked_entities"):
        value = payload.get(key)
        if isinstance(value, list):
            preview = []
            for item in value[:8]:
                if isinstance(item, dict):
                    name = (
                        item.get("resolved_entity_name")
                        or item.get("canonical_name")
                        or item.get("entity_name")
                        or item.get("entity_id")
                    )
                    desc = item.get("description") or item.get("short_description") or ""
                    preview.append(f"{name}: {desc}".strip(": "))
                else:
                    preview.append(str(item))
            if preview:
                lines.append(f"{key}: " + " | ".join(preview))
        elif isinstance(value, dict):
            preview = []
            for entity, neighbors in list(value.items())[:4]:
                preview.append(f"{entity}: {str(neighbors)[:300]}")
            if preview:
                lines.append(f"{key}: " + " | ".join(preview))

    if not lines:
        raw_preview = json.dumps(payload, ensure_ascii=False)[:1200]
        lines.append(f"{tool_name}/{method}: {raw_preview}")

    return "\n".join(lines[:12])


async def _infer_atom_completion_with_llm(
    atom: dict[str, Any],
    todo: dict[str, Any],
    payload: dict[str, Any],
    *,
    tool_name: str,
    method: str,
) -> dict[str, Any] | None:
    """Ask a small internal judge whether the current atom is fully resolved."""
    from pydantic import BaseModel, Field
    from llm_client import acall_llm_structured, render_prompt

    class AtomCompletionDecision(BaseModel):
        should_mark_done: bool = Field(
            description="True only if the evidence directly resolves the current atom."
        )
        resolved_value: str = Field(
            description="Shortest factual span answering the atom. Empty if unresolved."
        )
        confidence: float = Field(
            description="Confidence from 0 to 1 that the atom is directly resolved."
        )
        evidence_refs: list[str] = Field(
            description="Chunk IDs or entity IDs that best support the resolved value."
        )
        rationale: str = Field(
            description="Short explanation of why the atom is or is not resolved."
        )

    dependency_values = _resolved_dependency_values(atom)
    effective_atom_sub_question = str(atom.get("sub_question") or "")
    query_contract = payload.get("query_contract") or {}
    effective_query = str(query_contract.get("effective_query") or "").strip()
    if dependency_values and effective_query:
        effective_atom_sub_question = effective_query
    evidence_text = _build_atom_completion_evidence(
        payload,
        tool_name=tool_name,
        method=method,
        atom=atom,
        dependency_values=dependency_values,
    )
    if not evidence_text.strip():
        return None

    prompt_path = str(Path(__file__).parent / "prompts" / "atom_completion_guard.yaml")
    messages = render_prompt(
        prompt_path,
        question=_current_question or _current_semantic_plan_question or "",
        atom_id=str(atom.get("atom_id") or ""),
        atom_sub_question=str(atom.get("sub_question") or ""),
        effective_atom_sub_question=effective_atom_sub_question,
        answer_kind=_normalize_answer_kind(str(atom.get("answer_kind") or "")) or "entity",
        todo_content=str(todo.get("content") or ""),
        dependency_values=", ".join(dependency_values) if dependency_values else "(none)",
        tool_name=tool_name,
        method=method,
        effective_query=effective_query,
        evidence_text=evidence_text,
    )

    llm = _state.get("agentic_llm")
    model = llm.model if llm else _state["config"].llm.model
    trace_id = f"digimon.atom_completion.{tool_name}.{uuid.uuid4().hex[:8]}"
    try:
        decision, _meta = await acall_llm_structured(
            model,
            messages,
            response_model=AtomCompletionDecision,
            task="digimon.atom_completion",
            trace_id=trace_id,
            max_budget=0,
        )
    except Exception as exc:
        logger.warning("atom completion judge failed: %s", exc)
        return None

    resolved_value = str(decision.resolved_value or "").strip()
    if not decision.should_mark_done or not resolved_value:
        return {
            "event": "atom_judged_unresolved",
            "atom_id": str(atom.get("atom_id") or ""),
            "tool_name": tool_name,
            "method": method,
            "confidence": float(decision.confidence or 0.0),
            "rationale": decision.rationale,
        }

    return {
        "event": "atom_autocomplete",
        "atom_id": str(atom.get("atom_id") or ""),
        "resolved_value": resolved_value,
        "confidence": float(decision.confidence or 0.0),
        "evidence_refs": [str(ref).strip() for ref in (decision.evidence_refs or []) if str(ref).strip()],
        "rationale": decision.rationale,
        "tool_name": tool_name,
        "method": method,
    }


async def _validate_manual_todo_completion(
    atom: dict[str, Any],
    todo_item: dict[str, Any],
    *,
    previous_todo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject manual done transitions unless cached evidence supports them."""
    atom_id = str(atom.get("atom_id") or "").strip()
    proposed_value = _extract_todo_result_value(todo_item)
    if not proposed_value:
        raise ValueError(
            f"TODO '{atom_id}' cannot be marked done without an explicit answer/result value.",
        )
    if not _todo_dependencies_satisfied(atom):
        missing = [str(dep).strip() for dep in (atom.get("depends_on") or []) if str(dep).strip()]
        raise ValueError(
            f"TODO '{atom_id}' cannot be marked done before dependencies are done: {', '.join(missing)}.",
        )

    validation_payloads = list(_atom_validation_payloads.get(atom_id) or [])
    fallback_payload = _fallback_manual_validation_payload(atom)
    if fallback_payload:
        validation_payloads.append(fallback_payload)
    if not validation_payloads:
        _record_atom_lifecycle_event(
            {
                "event": "atom_manual_rejected",
                "atom_id": atom_id,
                "sub_question": atom.get("sub_question"),
                "proposed_value": proposed_value,
                "reason": "no_cached_evidence",
            }
        )
        raise ValueError(
            f"TODO '{atom_id}' cannot be marked done yet because no supporting evidence is cached. "
            "Retrieve supporting evidence first, then include the answer and evidence_refs.",
        )

    proposed_norm = _normalize_resolved_value(proposed_value)
    mismatch_update: dict[str, Any] | None = None
    last_unresolved: dict[str, Any] | None = None
    validation_todo = previous_todo or todo_item

    for payload in validation_payloads:
        tool_name = str(payload.get("tool_name") or "todo_write")
        method = str(payload.get("method") or "manual")
        update = await _infer_atom_completion_with_llm(
            atom,
            validation_todo,
            payload,
            tool_name=tool_name,
            method=method,
        )
        if not update:
            continue
        if update.get("event") != "atom_autocomplete":
            last_unresolved = update
            continue

        judged_value = str(update.get("resolved_value") or "").strip()
        judged_norm = _normalize_resolved_value(judged_value)
        if judged_norm != proposed_norm:
            mismatch_update = update
            continue

        merged_refs: list[str] = []
        for ref in (
            list(todo_item.get("evidence_refs") or [])
            + list(update.get("evidence_refs") or [])
            + list(payload.get("evidence_refs") or [])
        ):
            ref_text = str(ref or "").strip()
            if ref_text and ref_text not in merged_refs:
                merged_refs.append(ref_text)

        normalized_item = dict(todo_item)
        normalized_item.setdefault("answer", proposed_value)
        if merged_refs:
            normalized_item["evidence_refs"] = merged_refs
        _record_atom_lifecycle_event(
            {
                "event": "atom_manual_validated",
                "atom_id": atom_id,
                "sub_question": atom.get("sub_question"),
                "proposed_value": proposed_value,
                "tool_name": tool_name,
                "method": method,
                "evidence_refs": merged_refs,
                "rationale": str(update.get("rationale") or ""),
            }
        )
        return normalized_item

    if mismatch_update:
        supported_value = str(mismatch_update.get("resolved_value") or "").strip()
        _record_atom_lifecycle_event(
            {
                "event": "atom_manual_rejected",
                "atom_id": atom_id,
                "sub_question": atom.get("sub_question"),
                "proposed_value": proposed_value,
                "supported_value": supported_value,
                "reason": "value_mismatch",
                "rationale": str(mismatch_update.get("rationale") or ""),
            }
        )
        raise ValueError(
            f"TODO '{atom_id}' cannot be marked done with '{proposed_value}'. "
            f"Current evidence supports '{supported_value}' instead.",
        )

    unresolved_reason = str((last_unresolved or {}).get("rationale") or "").strip()
    _record_atom_lifecycle_event(
        {
            "event": "atom_manual_rejected",
            "atom_id": atom_id,
            "sub_question": atom.get("sub_question"),
            "proposed_value": proposed_value,
            "reason": "insufficient_evidence",
            "rationale": unresolved_reason,
        }
    )
    raise ValueError(
        f"TODO '{atom_id}' cannot be marked done yet because the current evidence does not directly resolve it."
        + (f" {unresolved_reason}" if unresolved_reason else ""),
    )


async def _probe_bridge_candidates_with_text(
    candidates: list[str],
    *,
    current_atom: dict[str, Any],
    payload: dict[str, Any],
    downstream_atom: dict[str, Any],
) -> list[dict[str, Any]]:
    """Probe bridge candidates with a lightweight downstream-focused text search."""
    if not candidates:
        return []

    dataset_name = str(payload.get("resolved_dataset_name") or "").strip()
    if not dataset_name:
        dataset_name = _dataset_name_from_graph_reference(str(payload.get("resolved_graph_reference_id") or ""))
    if not dataset_name:
        return []

    downstream_query = _compact_search_query(str(downstream_atom.get("sub_question") or ""))
    current_atom_tokens = _signal_tokens(str(current_atom.get("sub_question") or ""))
    canonical_tokens = _signal_tokens(str(payload.get("canonical_name") or ""))
    blocked_tokens = {
        "the",
        "when",
        "what",
        "where",
        "which",
        "entity",
        "identified",
        "birthplace",
        "location",
        "place",
        "that",
        "was",
        "were",
        "is",
        "are",
        "as",
        "born",
    }
    focus_tokens: list[str] = []
    seen_focus: set[str] = set()
    token_aliases = {
        "abolition": "abolished",
        "abolish": "abolished",
    }
    for raw_token in re.findall(r"[A-Za-z0-9_']+", downstream_query.lower()):
        token = token_aliases.get(raw_token.strip("'"), raw_token.strip("'"))
        if not token or "_" in token:
            continue
        if token in blocked_tokens or token in current_atom_tokens or token in canonical_tokens:
            continue
        if token in seen_focus:
            continue
        seen_focus.add(token)
        focus_tokens.append(token)
    if ("abolished" in downstream_query.lower() or "abolition" in downstream_query.lower()) and "abolished" not in seen_focus:
        focus_tokens.insert(0, "abolished")
    if not focus_tokens:
        return []
    focus_text = " ".join(focus_tokens[:2])
    canonical_subject_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", str(payload.get("canonical_name") or "").lower())
        if token and token not in _SIGNAL_STOPWORDS and token not in _QUERY_TITLE_TOKENS
    ]
    if canonical_subject_tokens:
        subject_tokens = canonical_subject_tokens
    else:
        subject_tokens = list(_ordered_subject_focus_tokens(current_atom))
    if not subject_tokens:
        return []
    subject_text = " ".join(subject_tokens[:2])

    probe_results: list[dict[str, Any]] = []
    for candidate in candidates[:4]:
        downstream_query = f"{candidate} {focus_text}".strip()
        subject_query = f"{candidate} {subject_text}".strip()

        async def _search(query_text: str) -> dict[str, Any] | None:
            seen_chunks_snapshot = dict(_seen_chunks)
            seen_chunk_text_snapshot = dict(_seen_chunk_text)
            try:
                with _query_contract_bypass("bridge_probe"):
                    raw = await chunk_text_search(query_text=query_text, dataset_name=dataset_name, top_k=2)
                probe_payload = json.loads(raw)
            except Exception:
                _seen_chunks.clear()
                _seen_chunks.update(seen_chunks_snapshot)
                _seen_chunk_text.clear()
                _seen_chunk_text.update(seen_chunk_text_snapshot)
                return None
            _seen_chunks.clear()
            _seen_chunks.update(seen_chunks_snapshot)
            _seen_chunk_text.clear()
            _seen_chunk_text.update(seen_chunk_text_snapshot)
            if not isinstance(probe_payload, dict):
                return None
            return probe_payload

        downstream_payload = await _search(downstream_query)
        subject_payload = await _search(subject_query)

        def _best_scored_chunk(
            probe_payload: dict[str, Any] | None,
            *,
            required_tokens: list[str],
            require_candidate: bool,
            reward_year: bool,
            reward_proximity: bool,
        ) -> tuple[float, dict[str, Any] | None]:
            if not isinstance(probe_payload, dict):
                return 0.0, None
            chunks = probe_payload.get("chunks")
            if not isinstance(chunks, list) or not chunks:
                return 0.0, None
            best_chunk = None
            best_score = 0.0
            for chunk in chunks[:2]:
                if not isinstance(chunk, dict):
                    continue
                text = str(chunk.get("text") or "").lower()
                candidate_present = candidate.lower() in text
                if require_candidate and not candidate_present:
                    continue
                score = 0.0
                if candidate_present:
                    score += 1.5
                if any(token.lower() in text for token in required_tokens):
                    score += 2.0
                if reward_year and re.search(r"\b\d{3,4}\b", text):
                    score += 1.5
                if reward_proximity and candidate_present and required_tokens:
                    candidate_count = text.count(candidate.lower())
                    if candidate_count > 1:
                        score += min(1.0, 0.5 * (candidate_count - 1))
                    words = re.findall(r"[a-z0-9']+", text)
                    candidate_head = candidate.lower().split()[0]
                    candidate_positions = [idx for idx, word in enumerate(words) if word == candidate_head]
                    token_positions = [
                        idx
                        for idx, word in enumerate(words)
                        if any(word == required.lower() for required in required_tokens)
                    ]
                    if candidate_positions and token_positions:
                        min_distance = min(abs(a - b) for a in candidate_positions for b in token_positions)
                        if min_distance <= 8:
                            score += 1.5
                        elif min_distance <= 20:
                            score += 0.75
                if score > best_score:
                    best_score = score
                    best_chunk = chunk
            return best_score, best_chunk

        downstream_score, downstream_chunk = _best_scored_chunk(
            downstream_payload,
            required_tokens=focus_tokens[:2],
            require_candidate=True,
            reward_year=True,
            reward_proximity=False,
        )
        subject_score, subject_chunk = _best_scored_chunk(
            subject_payload,
            required_tokens=subject_tokens[:2],
            require_candidate=True,
            reward_year=False,
            reward_proximity=True,
        )
        total_score = downstream_score + subject_score
        best_chunk = downstream_chunk or subject_chunk
        if best_chunk and total_score > 0:
            probe_results.append(
                {
                    "candidate": candidate,
                    "query": downstream_query,
                    "subject_query": subject_query,
                    "score": total_score,
                    "downstream_score": downstream_score,
                    "subject_score": subject_score,
                    "chunk_id": str(best_chunk.get("chunk_id") or ""),
                    "snippet": str(best_chunk.get("text") or "")[:400],
                }
            )

    probe_results.sort(key=lambda item: (-float(item.get("score") or 0.0), item.get("candidate") or ""))
    return probe_results


async def _infer_bridge_candidate_with_llm(
    atom: dict[str, Any],
    todo: dict[str, Any],
    payload: dict[str, Any],
    *,
    tool_name: str,
    method: str,
) -> dict[str, Any] | None:
    """Infer a provisional bridge entity when downstream clues strongly favor one candidate."""
    downstream_atom = _next_dependent_atom(atom)
    if downstream_atom is None:
        return None

    candidates = _bridge_candidate_names(payload, current_atom=atom)
    if len(candidates) < 2:
        return None

    probe_results = await _probe_bridge_candidates_with_text(
        candidates,
        current_atom=atom,
        payload=payload,
        downstream_atom=downstream_atom,
    )
    if probe_results:
        top_probe = probe_results[0]
        runner_up_score = float(probe_results[1].get("score") or 0.0) if len(probe_results) > 1 else 0.0
        top_score = float(top_probe.get("score") or 0.0)
        downstream_score = float(top_probe.get("downstream_score") or 0.0)
        subject_score = float(top_probe.get("subject_score") or 0.0)
        if (
            top_score >= _ATOM_BRIDGE_PROBE_MIN_TOTAL_SCORE
            and downstream_score >= _ATOM_BRIDGE_PROBE_MIN_DOWNSTREAM_SCORE
            and subject_score >= _ATOM_BRIDGE_PROBE_MIN_SUBJECT_SCORE
            and top_score >= runner_up_score + _ATOM_BRIDGE_PROBE_MIN_SCORE_GAP
        ):
            resolved_value = str(top_probe.get("candidate") or "").strip()
            chunk_id = str(top_probe.get("chunk_id") or "").strip()
            return {
                "event": "atom_autocomplete",
                "atom_id": str(atom.get("atom_id") or ""),
                "resolved_value": resolved_value,
                "confidence": min(0.9, 0.55 + 0.08 * top_score),
                "evidence_refs": [chunk_id] if chunk_id else [],
                "rationale": (
                    f"{resolved_value} is the only bridge candidate that surfaces the downstream clue "
                    f"'{str(downstream_atom.get('sub_question') or '').strip()}' in text evidence."
                ),
                "tool_name": tool_name,
                "method": method,
                "resolution_mode": "bridge_probe",
            }

    from pydantic import BaseModel, Field
    from llm_client import acall_llm_structured, render_prompt

    class BridgeDecision(BaseModel):
        should_advance: bool = Field(
            description="True only if one bridge candidate is clearly favored by the downstream clue."
        )
        bridge_value: str = Field(
            description="Chosen bridge entity value. Empty if no candidate is strong enough."
        )
        confidence: float = Field(
            description="Confidence from 0 to 1 that the chosen bridge should advance the plan."
        )
        rationale: str = Field(
            description="Short evidence-grounded explanation for the bridge choice or rejection."
        )
        evidence_refs: list[str] = Field(
            description="Chunk or entity refs supporting the bridge choice."
        )

    evidence_text = _build_atom_completion_evidence(payload, tool_name=tool_name, method=method)
    prompt_path = str(Path(__file__).parent / "prompts" / "atom_bridge_guard.yaml")
    messages = render_prompt(
        prompt_path,
        question=_current_question or _current_semantic_plan_question or "",
        atom_id=str(atom.get("atom_id") or ""),
        atom_sub_question=str(atom.get("sub_question") or ""),
        downstream_atom_id=str(downstream_atom.get("atom_id") or ""),
        downstream_sub_question=str(downstream_atom.get("sub_question") or ""),
        todo_content=str(todo.get("content") or ""),
        source_entity=str(payload.get("canonical_name") or payload.get("entity_id") or ""),
        candidates_json=json.dumps(candidates, ensure_ascii=False),
        evidence_text=evidence_text,
    )

    llm = _state.get("agentic_llm")
    model = llm.model if llm else _state["config"].llm.model
    trace_id = f"digimon.atom_bridge.{tool_name}.{uuid.uuid4().hex[:8]}"
    try:
        decision, _meta = await acall_llm_structured(
            model,
            messages,
            response_model=BridgeDecision,
            task="digimon.atom_bridge",
            trace_id=trace_id,
            max_budget=0,
        )
    except Exception as exc:
        logger.warning("atom bridge judge failed: %s", exc)
        return None

    bridge_value = str(decision.bridge_value or "").strip()
    confidence = float(decision.confidence or 0.0)
    if not decision.should_advance or not bridge_value or confidence < _ATOM_BRIDGE_MIN_CONFIDENCE:
        return {
            "event": "atom_judged_unresolved",
            "atom_id": str(atom.get("atom_id") or ""),
            "tool_name": tool_name,
            "method": method,
            "confidence": confidence,
            "rationale": str(decision.rationale or "").strip() or "Bridge evidence is still too weak to advance.",
        }

    return {
        "event": "atom_autocomplete",
        "atom_id": str(atom.get("atom_id") or ""),
        "resolved_value": bridge_value,
        "confidence": confidence,
        "evidence_refs": [str(ref).strip() for ref in (decision.evidence_refs or []) if str(ref).strip()],
        "rationale": str(decision.rationale or "").strip(),
        "tool_name": tool_name,
        "method": method,
        "resolution_mode": "bridge_inference",
    }


def _apply_atom_completion_update(atom: dict[str, Any], todo: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Persist an atom-completion decision into TODO state and advance the plan."""
    resolved_value = str(update.get("resolved_value") or "").strip()
    evidence_refs = [str(ref).strip() for ref in (update.get("evidence_refs") or []) if str(ref).strip()]
    todo["status"] = "done"
    todo["answer"] = resolved_value
    resolution_mode = str(update.get("resolution_mode") or "").strip()
    if resolution_mode:
        todo["resolution_mode"] = resolution_mode
    if evidence_refs:
        todo["evidence_refs"] = evidence_refs
    atom_update = {
        "event": "atom_completed",
        "atom_id": str(atom.get("atom_id") or ""),
        "sub_question": str(atom.get("sub_question") or ""),
        "resolved_value": resolved_value,
        "confidence": float(update.get("confidence") or 0.0),
        "evidence_refs": evidence_refs,
        "rationale": str(update.get("rationale") or ""),
        "tool_name": str(update.get("tool_name") or ""),
        "method": str(update.get("method") or ""),
    }
    if resolution_mode:
        atom_update["resolution_mode"] = resolution_mode
    _record_atom_lifecycle_event(atom_update)
    promoted = _promote_next_ready_atom()
    if promoted:
        atom_update["next_atom"] = promoted.get("atom_id")
    atom_update["todo_status_line"] = _todo_status_line()
    return atom_update


def _best_atom_autocomplete_update(
    updates: list[dict[str, Any]],
    *,
    answer_kind: str,
) -> dict[str, Any] | None:
    """Choose the best autocomplete update when multiple payloads compete."""
    if not updates:
        return None

    def _rank(update: dict[str, Any]) -> tuple[float, int, int]:
        confidence = float(update.get("confidence") or 0.0)
        tool_name = str(update.get("tool_name") or "")
        resolution_mode = str(update.get("resolution_mode") or "")
        bridge_priority = 1 if resolution_mode in {"bridge_probe", "bridge_inference"} else 0
        relationship_priority = 1 if tool_name == "relationship_search" else 0
        if answer_kind == "entity":
            return (confidence, bridge_priority + relationship_priority, len(update.get("evidence_refs") or []))
        return (confidence, relationship_priority, len(update.get("evidence_refs") or []))

    return max(updates, key=_rank)


async def _maybe_complete_active_atom_from_payload(
    payload: dict[str, Any],
    *,
    tool_name: str,
    method: str,
) -> dict[str, Any] | None:
    """Try to auto-complete the current atom from a retrieval payload."""
    atom, todo = _active_semantic_plan_atom()
    if atom is None or todo is None:
        return None
    if todo.get("status") == "done":
        return None
    _store_atom_validation_payload(atom, payload, tool_name=tool_name, method=method)
    answer_kind = _normalize_answer_kind(str(atom.get("answer_kind") or ""))
    if tool_name == "entity_search" and method == "string" and answer_kind == "entity":
        top_match = _best_entity_search_match_for_atom(payload, atom=atom)
        score = float((top_match or {}).get("match_score") or (top_match or {}).get("score") or 0.0)
        if top_match and score >= _ENTITY_SUBJECT_AUTO_PROFILE_MIN_SCORE:
            candidate_entity_id = str(
                top_match.get("entity_name")
                or top_match.get("entity_id")
                or top_match.get("resolved_entity_id")
                or ""
            ).strip()
            candidate_name = str(
                top_match.get("canonical_name")
                or top_match.get("entity_name")
                or top_match.get("resolved_entity_name")
                or ""
            ).strip()
            resolved_graph_id = str(payload.get("resolved_graph_reference_id") or "").strip()
            dataset_name = str(payload.get("dataset_name") or "").strip()
            if candidate_name and resolved_graph_id:
                candidate_updates: list[dict[str, Any]] = []
                try:
                    profile_raw = await entity_profile(
                        entity_name=candidate_name,
                        graph_reference_id=resolved_graph_id,
                        dataset_name=dataset_name,
                    )
                    profile_payload = json.loads(profile_raw)
                except Exception:
                    profile_payload = None
                relationship_payload = None
                if candidate_entity_id:
                    try:
                        relationship_raw = await relationship_onehop(
                            entity_ids=[candidate_entity_id],
                            graph_reference_id=resolved_graph_id,
                        )
                        relationship_payload = json.loads(relationship_raw)
                    except Exception:
                        relationship_payload = None
                for candidate_payload, candidate_tool, candidate_method in (
                    (profile_payload, "entity_info", "profile"),
                    (relationship_payload, "relationship_search", "graph"),
                ):
                    if not isinstance(candidate_payload, dict):
                        continue
                    candidate_payload.setdefault("resolved_graph_reference_id", resolved_graph_id)
                    candidate_payload.setdefault("resolved_dataset_name", dataset_name)
                    candidate_payload.setdefault("canonical_name", candidate_name)
                    if candidate_entity_id:
                        candidate_payload.setdefault("entity_id", candidate_entity_id)
                    update = await _infer_atom_completion_with_llm(
                        atom,
                        todo,
                        candidate_payload,
                        tool_name=candidate_tool,
                        method=candidate_method,
                    )
                    if update and update.get("event") == "atom_autocomplete":
                        candidate_updates.append(update)
                    bridge_update = await _infer_bridge_candidate_with_llm(
                        atom,
                        todo,
                        candidate_payload,
                        tool_name=candidate_tool,
                        method=candidate_method,
                    )
                    if bridge_update and bridge_update.get("event") == "atom_autocomplete":
                        candidate_updates.append(bridge_update)
                best_update = _best_atom_autocomplete_update(
                    candidate_updates,
                    answer_kind=answer_kind,
                )
                if best_update:
                    return _apply_atom_completion_update(atom, todo, best_update)
        return None

    if tool_name not in {"chunk_retrieve", "relationship_search", "entity_info"}:
        return None

    update = await _infer_atom_completion_with_llm(
        atom,
        todo,
        payload,
        tool_name=tool_name,
        method=method,
    )
    if not update:
        return None
    if update.get("event") != "atom_autocomplete":
        bridge_update: dict[str, Any] | None = None
        if answer_kind == "entity" and tool_name in {"entity_info", "relationship_search"}:
            bridge_update = await _infer_bridge_candidate_with_llm(
                atom,
                todo,
                payload,
                tool_name=tool_name,
                method=method,
            )
        if bridge_update and bridge_update.get("event") == "atom_autocomplete":
            return _apply_atom_completion_update(atom, todo, bridge_update)
        if bridge_update and bridge_update.get("event") == "atom_judged_unresolved":
            update = bridge_update
        if tool_name == "chunk_retrieve" and answer_kind == "entity":
            update["next_action"] = (
                "Switch surfaces: resolve the subject entity in the graph with "
                "entity_search(method='string'), then inspect entity_info(profile) "
                "or relationship_search(graph). Do not guess a bridge entity yet."
            )
        elif tool_name in {"entity_info", "relationship_search"} and answer_kind == "entity":
            update["next_action"] = (
                "If the graph exposes multiple connected places, choose the bridge entity "
                "that best fits the downstream atom before searching for the final date."
            )
        _record_atom_lifecycle_event(update)
        return update
    return _apply_atom_completion_update(atom, todo, update)


def _normalize_answer_kind(answer_kind: str) -> str:
    """Normalize answer type labels used by TODOs and submit checks."""
    kind = (answer_kind or "").strip().lower()
    aliases = {
        "": "",
        "date": "date",
        "time": "date",
        "year": "date",
        "month": "date",
        "number": "number",
        "numeric": "number",
        "count": "number",
        "quantity": "number",
        "yes_no": "yes_no",
        "yes/no": "yes_no",
        "boolean": "yes_no",
        "bool": "yes_no",
        "entity": "entity",
        "name": "entity",
        "person": "entity",
        "location": "entity",
        "span": "entity",
        "text": "entity",
    }
    return aliases.get(kind, "")


_ENTITY_HINT_RE = re.compile(
    r"(^\s*(who|whom|whose|where)\b)|"
    r"(\b(what(?:'s| is)?\s+(?:the\s+)?name of|which\s+(person|individual|player|actor|singer|author|city|country|region|company|river|state))\b)"
)
_DATE_HINT_RE = re.compile(
    r"\b("
    r"when|what year|which year|what month|which month|what date|which date|"
    r"date of birth|birth date|born|founded|created|signed|released|died|abolished"
    r")\b"
)
_NUMBER_HINT_RE = re.compile(r"\b(how many|how much|what number|what amount|population|count|total)\b")
_YESNO_HINT_RE = re.compile(r"^\s*(is|are|was|were|do|does|did|can|could|will|has|have|had)\b")
_CAPITALIZED_MENTION_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")
def _infer_answer_kind(text: str) -> str:
    """Infer expected answer kind from question/task language."""
    probe = (text or "").strip().lower()
    if not probe:
        return "entity"
    if _YESNO_HINT_RE.search(probe):
        return "yes_no"
    # Entity asks ("who", "name of", etc.) override date keywords in clauses
    # such as "who was born in ...".
    if _ENTITY_HINT_RE.search(probe):
        return "entity"
    if _DATE_HINT_RE.search(probe):
        return "date"
    if _NUMBER_HINT_RE.search(probe):
        return "number"
    return "entity"


def _normalize_coarse_type(value: str) -> str:
    """Normalize coarse entity types for lightweight compatibility checks."""
    raw = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return "unknown"
    aliases = {
        "location": "place",
        "geo": "place",
        "city": "place",
        "country": "place",
        "state": "place",
        "region": "place",
        "province": "place",
        "human": "person",
        "people": "person",
        "org": "organization",
        "company": "organization",
        "institution": "organization",
    }
    return aliases.get(raw, raw)


def _coarse_type_matches(candidate_type: str, expected_types: set[str]) -> bool:
    """Return True when candidate coarse type is compatible with expected types."""
    if not expected_types:
        return True
    norm = _normalize_coarse_type(candidate_type)
    if norm in expected_types:
        return True
    return any(norm in item or item in norm for item in expected_types)


def _infer_expected_coarse_types(text: str) -> set[str]:
    """Infer expected entity coarse types from natural-language query/task text."""
    probe = (text or "").strip().lower()
    if not probe:
        return set()
    expected: set[str] = set()
    if re.search(r"\b(birthplace|headquarter|headquarters|city|country|province|state|region|where|located)\b", probe):
        expected.add("place")
    if re.search(
        r"\b(founder|author|actor|player|person|individual|who|performer|singer|musician|artist|designer|architect|explorer)\b",
        probe,
    ):
        expected.add("person")
    if re.search(r"\b(company|organization|organisation|group|label|team|university|agency|government)\b", probe):
        expected.add("organization")
    return expected


def _extract_context_entity_mentions(text: str, *, limit: int = 8) -> list[str]:
    """Extract lightweight proper-noun mentions from chunk snippets."""
    if not text:
        return []
    blocked = {
        "It", "The", "A", "An", "In", "On", "At", "By", "Of", "And",
        "However", "Despite", "After", "Before", "During",
    }
    mentions: list[str] = []
    seen: set[str] = set()
    for match in _CAPITALIZED_MENTION_RE.findall(text):
        mention = (match or "").strip()
        if not mention or mention in blocked:
            continue
        if mention in seen:
            continue
        mentions.append(mention)
        seen.add(mention)
        if len(mentions) >= max(1, int(limit)):
            break
    return mentions


_GENERIC_ENTITY_CANDIDATE_NAMES = {
    "performer",
    "artist",
    "musician",
    "singer",
    "actor",
    "author",
    "designer",
    "architect",
    "founder",
    "player",
    "person",
    "individual",
    "the musical",
    "musical",
    "group",
    "company",
    "organization",
    "city",
    "country",
    "region",
}


def _lookup_entity_coarse_type(entity_id: str, dataset_name: str = "") -> str:
    """Resolve coarse entity type from graph node metadata when available."""
    resolved_graph_id = _resolve_graph_reference_id(dataset_name=dataset_name)
    if not resolved_graph_id:
        return "unknown"
    ctx = _state.get("context")
    graph_instance = (
        ctx.get_graph_instance(resolved_graph_id)
        if ctx is not None and hasattr(ctx, "get_graph_instance")
        else None
    )
    if not graph_instance or not hasattr(graph_instance, "_graph") or not hasattr(graph_instance._graph, "graph"):
        return "unknown"
    nx_graph = graph_instance._graph.graph
    if entity_id not in nx_graph:
        return "unknown"
    attrs = dict(nx_graph.nodes[entity_id] or {})
    coarse_type = str(attrs.get("entity_type") or attrs.get("type") or "").strip()
    return _normalize_coarse_type(coarse_type)


def _answer_matches_kind(answer: str, answer_kind: str) -> bool:
    """Heuristic answer-kind validator for benchmark submit contract.

    Intentionally lenient — the semantic_plan's answer_kind prediction is
    often wrong (e.g. 'date' for a count question). False rejections cause
    70+ retry loops that burn budget. Only reject clear mismatches.
    """
    value = (answer or "").strip()
    kind = _normalize_answer_kind(answer_kind) or "entity"
    if not value:
        return False
    if kind == "yes_no":
        return value.lower() in {"yes", "no"}
    if kind == "date":
        # Accept years, months, dates, AND plain numbers (plan may have misclassified)
        if _YEAR_RE.search(value) or _MONTH_RE.search(value):
            return True
        if re.search(r"\d", value):
            return True  # numbers are plausible dates/counts
        return False
    if kind == "number":
        if re.search(r"\d", value):
            return True
        return bool(re.fullmatch(r"[A-Za-z-]+(?:\s+[A-Za-z-]+){0,3}", value))
    return True


def _normalize_string_list(values: Any, *, split_commas: bool = False) -> list[str]:
    """Normalize scalar/list-like input into a de-duplicated string list."""
    if values is None:
        return []

    raw_items: list[Any]
    if isinstance(values, str):
        text = values.strip()
        if not text:
            return []
        parsed: Any = None
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
        if isinstance(parsed, list):
            raw_items = list(parsed)
        elif split_commas:
            raw_items = [p.strip() for p in re.split(r"[,\n;]", text) if p.strip()]
        else:
            raw_items = [text]
    elif isinstance(values, (list, tuple, set)):
        raw_items = list(values)
    else:
        raw_items = [values]

    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _normalize_alternatives_tested(alternatives_tested: Any) -> list[str]:
    """Normalize alternatives_tested into a clean list of meaningful candidate labels."""
    if alternatives_tested is None:
        return []

    values: list[str] = []
    raw = alternatives_tested

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        parsed: Any = None
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
        if isinstance(parsed, list):
            raw = parsed
        else:
            raw = [part.strip() for part in re.split(r"[;\n]|,(?=\s*[A-Za-z0-9])", text) if part.strip()]

    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            if item is None:
                continue
            text = item if isinstance(item, str) else str(item)
            values.append(text)
    else:
        values = [str(raw)]

    out: list[str] = []
    seen: set[str] = set()
    non_alt = {
        "none", "n/a", "na", "unknown", "not sure", "no alternative",
        "same", "same as answer", "none found",
    }

    for value in values:
        cleaned = re.sub(r"\s+", " ", (value or "").strip(" \t\r\n-•"))
        if len(cleaned) < 2:
            continue
        lowered = cleaned.lower()
        if lowered in non_alt:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(cleaned)
    return out


_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTH_RE = re.compile(r"\b(" + "|".join(_MONTH_NAMES) + r")\b", flags=re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:[1-9][0-9]{2,3}|20[0-9]{2})\b")
_QUERY_TITLE_TOKENS = {
    "mr", "mrs", "ms", "dr", "sir", "lady", "saint",
    "count", "countess", "duke", "duchess", "king", "queen",
}
_SIGNAL_STOPWORDS = {
    "a", "an", "the", "of", "for", "from", "by", "with", "without",
    "in", "on", "at", "to", "and", "or", "is", "are", "was", "were",
    "be", "been", "being", "as", "that", "this", "these", "those",
    "what", "which", "who", "whose", "when", "where", "how",
}
_GRAPH_SUFFIXES = (
    "_ERGraph", "_RKGraph", "_TreeGraph", "_TreeBalancedGraph", "_PassageGraph",
)
_DATASET_ALIAS_SUFFIXES = (
    "_entities", "_entity", "_relations", "_relation", "_chunks",
    "_ergraph", "_rkgraph", "_treegraph", "_treebalancedgraph", "_passagegraph",
)


def _signal_tokens(text: str) -> set[str]:
    """Tokenize text into content-bearing terms for overlap scoring."""
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: set[str] = set()
    for token in raw:
        if not token:
            continue
        if token in _SIGNAL_STOPWORDS:
            continue
        if token in _QUERY_TITLE_TOKENS:
            continue
        if len(token) <= 2 and not token.isdigit():
            continue
        out.add(token)
    return out


def _vdb_index_dimension(vdb_instance: Any) -> int | None:
    """Best-effort FAISS index dimensionality extraction."""
    probes = (
        "_index.vector_store._faiss_index.d",
        "_index.storage_context.vector_store._faiss_index.d",
        "_index.vector_store.faiss_index.d",
    )
    for probe in probes:
        try:
            target: Any = vdb_instance
            for part in probe.split("."):
                target = getattr(target, part)
            dim = int(target)
            if dim > 0:
                return dim
        except Exception:
            continue
    return None


def _strip_graph_suffix(graph_id: str) -> str:
    for suffix in _GRAPH_SUFFIXES:
        if graph_id.lower().endswith(suffix.lower()):
            return graph_id[: -len(suffix)]
    return graph_id


def _strip_dataset_alias_suffix(name: str) -> str:
    value = (name or "").strip()
    lowered = value.lower()
    changed = True
    while changed and value:
        changed = False
        for suffix in _DATASET_ALIAS_SUFFIXES:
            if lowered.endswith(suffix):
                value = value[: -len(suffix)].rstrip("_- ")
                lowered = value.lower()
                changed = True
                break
    return value or (name or "").strip()


def _resolve_dataset_name(dataset_name: str) -> str:
    """Resolve dataset aliases like 'MuSiQue_entities' -> 'MuSiQue'."""
    candidate = _strip_dataset_alias_suffix(dataset_name)
    if not candidate:
        return candidate

    ctx = _state.get("context")
    if ctx is None:
        return candidate

    known: set[str] = set()
    if hasattr(ctx, "list_graphs"):
        for gid in ctx.list_graphs():
            known.add(_strip_dataset_alias_suffix(_strip_graph_suffix(gid)))
    if hasattr(ctx, "list_vdbs"):
        for vid in ctx.list_vdbs():
            known.add(_strip_dataset_alias_suffix(vid))
    known = {k for k in known if k}
    if not known:
        return candidate

    for ds in known:
        if ds.lower() == candidate.lower():
            return ds
    for ds in known:
        if candidate.lower() in ds.lower() or ds.lower() in candidate.lower():
            return ds
    return candidate


def _resolve_graph_reference_id(graph_reference_id: str = "", dataset_name: str = "") -> str:
    """Resolve graph id from exact id, dataset name, or aliases."""
    ctx = _state.get("context")
    graphs = ctx.list_graphs() if ctx is not None and hasattr(ctx, "list_graphs") else []
    if not graphs:
        return graph_reference_id or dataset_name

    probes = [graph_reference_id, dataset_name]
    for probe in probes:
        if not probe:
            continue
        p = probe.strip()
        for gid in graphs:
            if gid.lower() == p.lower():
                return gid
        resolved_dataset = _resolve_dataset_name(p)
        for gid in graphs:
            gid_dataset = _strip_dataset_alias_suffix(_strip_graph_suffix(gid))
            if gid_dataset.lower() == resolved_dataset.lower():
                return gid
        for gid in graphs:
            if p.lower() in gid.lower() or gid.lower() in p.lower():
                return gid

    return graphs[0] if len(graphs) == 1 else (graph_reference_id or "")


def _resolve_vdb_reference_id(
    vdb_reference_id: str = "",
    dataset_name: str = "",
    *,
    kind: str | None = None,
) -> str:
    """Resolve VDB id from exact id or dataset aliases."""
    ctx = _state.get("context")
    vdbs = ctx.list_vdbs() if ctx is not None and hasattr(ctx, "list_vdbs") else []
    base = _resolve_dataset_name(dataset_name or vdb_reference_id)

    def _preferred_from_base() -> str:
        if not base:
            return ""
        if kind == "entity":
            return f"{base}_entities"
        if kind == "relation":
            return f"{base}_relations"
        if kind == "chunk":
            return f"{base}_chunks"
        return base

    if not vdbs:
        preferred = _preferred_from_base()
        return preferred or vdb_reference_id or dataset_name

    def _kind_match(vdb_id: str) -> bool:
        lower = vdb_id.lower()
        if kind == "entity":
            return "entit" in lower
        if kind == "relation":
            return "relat" in lower or "relation" in lower
        if kind == "chunk":
            return "chunk" in lower
        return True

    probes = [vdb_reference_id, dataset_name]
    for probe in probes:
        if not probe:
            continue
        p = probe.strip()
        for vid in vdbs:
            if vid.lower() == p.lower():
                return vid

    if base:
        preferred = []
        if kind == "entity":
            preferred.append(f"{base}_entities")
        elif kind == "relation":
            preferred.append(f"{base}_relations")
        elif kind == "chunk":
            preferred.append(f"{base}_chunks")
        for pref in preferred:
            for vid in vdbs:
                if vid.lower() == pref.lower():
                    return vid

    best_vid = ""
    best_score = -1
    for vid in vdbs:
        score = 0
        if kind and _kind_match(vid):
            score += 40
        if base:
            base_vid = _strip_dataset_alias_suffix(vid)
            if base_vid.lower() == base.lower():
                score += 60
            elif base.lower() in vid.lower():
                score += 30
        if vdb_reference_id and vdb_reference_id.lower() in vid.lower():
            score += 20
        if score > best_score:
            best_score = score
            best_vid = vid

    if best_score > 0:
        return best_vid
    preferred = _preferred_from_base()
    return preferred or vdb_reference_id or (vdbs[0] if len(vdbs) == 1 else "")


def _looks_like_date_entity(name: str) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return bool((_MONTH_RE.search(lowered) and _YEAR_RE.search(lowered)) or _YEAR_RE.fullmatch(lowered.strip()))


def _looks_like_person_entity(name: str) -> bool:
    tokens = [t for t in name.strip().split() if t]
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    if any(not t.isalpha() for t in tokens):
        return False
    if any(len(t) < 2 for t in tokens):
        return False
    lowered = name.lower()
    return not lowered.startswith(("the ", "la ", "el "))


def _normalize_entity_search_payload(result: Any) -> dict:
    """Convert entity search result object to plain dict."""
    if hasattr(result, "model_dump"):
        return result.model_dump(exclude_none=True)
    if isinstance(result, dict):
        return dict(result)
    try:
        parsed = json.loads(_format_result(result))
        return parsed if isinstance(parsed, dict) else {"similar_entities": []}
    except Exception:
        return {"similar_entities": []}


def _build_entity_query_variants(query_text: str) -> list[str]:
    """Build small deterministic query variants to improve entity recall."""
    from Core.Common.Utils import clean_str

    variants = [query_text.strip()]
    cleaned = " ".join(clean_str(query_text).split())
    if cleaned:
        variants.append(cleaned)

        tokens = [t for t in cleaned.split() if t]
        stripped = [t for t in tokens if t not in _QUERY_TITLE_TOKENS]
        if stripped and stripped != tokens:
            variants.append(" ".join(stripped))

    deduped: list[str] = []
    seen: set[str] = set()
    for v in variants:
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(v)
    return deduped


def _build_entity_search_guidance(similar_entities: list[dict]) -> list[str]:
    """Generate short retrieval hints to reduce anchor errors in multi-hop questions."""
    if not similar_entities:
        return []

    top = similar_entities[:5]
    date_candidates = [
        item.get("entity_name", "")
        for item in top
        if _looks_like_date_entity(str(item.get("entity_name", "")))
    ]
    non_date_candidates = [
        item.get("entity_name", "")
        for item in top
        if item.get("entity_name") and not _looks_like_date_entity(str(item.get("entity_name", "")))
    ]

    hints: list[str] = []

    if date_candidates and non_date_candidates:
        person_like = [n for n in non_date_candidates if _looks_like_person_entity(n)]
        bridge_entity = person_like[0] if person_like else non_date_candidates[0]
        hints.append(
            "Top candidates include both a date-like entity and a person/entity. "
            "Verify this pair with chunk_get_text_by_entity_ids before deciding.",
        )
        hints.append(
            f"Try: chunk_get_text_by_entity_ids(graph_reference_id=..., entity_ids=[{bridge_entity!r}]) "
            "and check whether it supports the date.",
        )

    if len(top) >= 2:
        try:
            first = float(top[0].get("score") or 0.0)
            second = float(top[1].get("score") or 0.0)
        except (TypeError, ValueError):
            first = 0.0
            second = 0.0
        if abs(first - second) < 0.03:
            hints.append(
                "Top entity scores are close. Do not trust rank #1 blindly; verify at least two candidates.",
            )

    return hints


def _chunk_ids_from_node_data(node_data: dict[str, Any]) -> list[str]:
    """Extract chunk IDs from graph node attributes."""
    from Core.Common.Constants import GRAPH_FIELD_SEP
    from Core.Common.Utils import split_string_by_multi_markers

    chunk_ids: list[str] = []

    def _append(raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, str):
            values = split_string_by_multi_markers(raw, [GRAPH_FIELD_SEP])
        elif isinstance(raw, (list, tuple, set)):
            values = [str(v) for v in raw if v is not None]
        else:
            values = [str(raw)]
        for value in values:
            cid = value.strip()
            if not cid:
                continue
            if cid.startswith("chunk_"):
                chunk_ids.append(cid)

    for key in (
        "chunk_id",
        "source_chunk_id",
        "chunk_ids",
        "source_chunk_ids",
        "source_chunks",
        "source_id",
    ):
        _append(node_data.get(key))

    deduped: list[str] = []
    seen: set[str] = set()
    for cid in chunk_ids:
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append(cid)
    return deduped


def _load_chunk_entity_index_for_dataset(dataset_name: str) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    """Build or reuse chunk_id -> candidate-entity index for the dataset graph."""
    resolved_graph_id = _resolve_graph_reference_id(dataset_name=dataset_name)
    if not resolved_graph_id:
        return "", {}

    cached = _chunk_entity_index_cache.get(resolved_graph_id)
    if cached is not None:
        return resolved_graph_id, cached

    ctx = _state.get("context")
    graph_instance = ctx.get_graph_instance(resolved_graph_id) if ctx is not None and hasattr(ctx, "get_graph_instance") else None
    if not graph_instance or not hasattr(graph_instance, "_graph") or not hasattr(graph_instance._graph, "graph"):
        return resolved_graph_id, {}
    nx_graph = graph_instance._graph.graph

    chunk_to_candidates: dict[str, list[dict[str, Any]]] = {}
    for node_id, attrs in nx_graph.nodes(data=True):
        node_attrs = dict(attrs or {})
        chunk_ids = _chunk_ids_from_node_data(node_attrs)
        if not chunk_ids:
            continue

        entity_id = str(node_id)
        entity_name = (
            str(node_attrs.get("entity_name") or "").strip()
            or str(node_attrs.get("name") or "").strip()
            or entity_id
        )
        coarse_type = (
            str(node_attrs.get("entity_type") or "").strip()
            or str(node_attrs.get("type") or "").strip()
            or "unknown"
        )
        degree = 0.0
        try:
            degree = float(nx_graph.degree(node_id))
        except Exception:
            degree = 0.0
        salience = round(min(1.0, degree / 20.0), 4)
        base_payload = {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "coarse_type": coarse_type,
            "salience": salience,
            "source": "graph_source_id",
        }

        for chunk_id in chunk_ids:
            bucket = chunk_to_candidates.setdefault(chunk_id, [])
            bucket.append(base_payload)

    # Dedup and stable sort per chunk.
    for chunk_id, candidates in list(chunk_to_candidates.items()):
        unique: dict[str, dict[str, Any]] = {}
        for item in candidates:
            eid = str(item.get("entity_id") or "").strip()
            if not eid:
                continue
            prev = unique.get(eid)
            if prev is None or float(item.get("salience") or 0.0) > float(prev.get("salience") or 0.0):
                unique[eid] = item
        ordered = sorted(
            unique.values(),
            key=lambda x: (
                float(x.get("salience") or 0.0),
                str(x.get("entity_name") or ""),
            ),
            reverse=True,
        )
        chunk_to_candidates[chunk_id] = ordered

    _chunk_entity_index_cache[resolved_graph_id] = chunk_to_candidates
    return resolved_graph_id, chunk_to_candidates


def _enrich_chunks_with_entity_candidates(
    *,
    dataset_name: str,
    query_text: str,
    chunks: list[dict[str, Any]],
    max_candidates_per_chunk: int = 4,
    max_total_candidates: int = 40,
) -> dict[str, Any]:
    """Add bounded candidate entities to chunk retrieval payloads."""
    global _latest_entity_candidates_flat

    resolved_graph_id, chunk_index = _load_chunk_entity_index_for_dataset(dataset_name)
    if not chunks or not chunk_index:
        _latest_entity_candidates_by_chunk.clear()
        _latest_entity_candidates_flat = []
        return {
            "resolved_graph_reference_id": resolved_graph_id or None,
            "entity_candidates": [],
            "entity_candidates_by_chunk": {},
            "candidate_summary": {
                "n_chunks_with_candidates": 0,
                "n_candidates": 0,
            },
        }

    query_tokens = _signal_tokens(query_text)
    expected_types = _infer_expected_coarse_types(query_text)
    chunk_scores = [float(c.get("score") or 0.0) for c in chunks if isinstance(c, dict)]
    max_chunk_score = max(chunk_scores) if chunk_scores else 0.0
    max_chunk_score = max(max_chunk_score, 1e-6)
    max_rank = max(1, len(chunks))

    entity_candidates_by_chunk: dict[str, list[dict[str, Any]]] = {}
    flat_candidates: list[dict[str, Any]] = []

    for rank, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if not chunk_id:
            continue
        chunk_text = str(chunk.get("text") or chunk.get("text_content") or "")
        raw_candidates = chunk_index.get(chunk_id, [])
        if not raw_candidates:
            continue

        chunk_signal = float(chunk.get("score") or 0.0) / max_chunk_score
        chunk_signal = max(0.0, min(1.0, chunk_signal))
        rank_signal = 1.0 - ((rank - 1) / max(1, max_rank - 1))
        rank_signal = max(0.0, min(1.0, rank_signal))

        scored: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            entity_name = str(candidate.get("entity_name") or "")
            name_tokens = _signal_tokens(entity_name)
            overlap = 0.0
            if query_tokens and name_tokens:
                overlap = len(query_tokens & name_tokens) / max(1, len(name_tokens))
            salience = float(candidate.get("salience") or 0.0)
            candidate_type = _normalize_coarse_type(str(candidate.get("coarse_type") or ""))
            type_match = 0.0
            type_penalty = 0.0
            if expected_types:
                if _coarse_type_matches(candidate_type, expected_types):
                    type_match = 1.0
                elif candidate_type and candidate_type != "unknown":
                    # Small penalty for confidently wrong coarse types when
                    # the query strongly hints an expected entity class.
                    type_penalty = 0.1
            candidate_score = (
                (0.35 * overlap)
                + (0.20 * salience)
                + (0.20 * chunk_signal)
                + (0.15 * rank_signal)
                + (0.20 * type_match)
                - type_penalty
            )
            candidate_score = max(0.0, min(1.0, candidate_score))
            scored.append(
                {
                    "chunk_id": chunk_id,
                    "entity_id": str(candidate.get("entity_id") or "").strip(),
                    "entity_name": entity_name,
                    "coarse_type": candidate.get("coarse_type"),
                    "candidate_score": round(candidate_score, 4),
                    "salience": round(salience, 4),
                    "query_overlap": round(overlap, 4),
                    "chunk_score_signal": round(chunk_signal, 4),
                    "rank_signal": round(rank_signal, 4),
                    "type_match_signal": round(type_match, 4),
                    "expected_coarse_types": sorted(expected_types) if expected_types else [],
                    "retrieval_rank": rank,
                    "mention_text": entity_name,
                    "evidence_ref": chunk_id,
                    "source": candidate.get("source", "graph_source_id"),
                    "context_snippet": chunk_text[:160] if chunk_text else "",
                }
            )

        scored.sort(
            key=lambda x: (
                float(x.get("candidate_score") or 0.0),
                float(x.get("salience") or 0.0),
            ),
            reverse=True,
        )
        selected = scored[: max(1, int(max_candidates_per_chunk))]
        if selected:
            entity_candidates_by_chunk[chunk_id] = selected
            flat_candidates.extend(selected)

    flat_candidates.sort(
        key=lambda x: (
            float(x.get("candidate_score") or 0.0),
            -int(x.get("retrieval_rank") or 9999),
        ),
        reverse=True,
    )
    if max_total_candidates > 0:
        flat_candidates = flat_candidates[:max_total_candidates]
        keep = {
            (
                str(item.get("chunk_id") or ""),
                str(item.get("entity_id") or ""),
            )
            for item in flat_candidates
        }
        for chunk_id, items in list(entity_candidates_by_chunk.items()):
            filtered = [
                it for it in items
                if (str(it.get("chunk_id") or ""), str(it.get("entity_id") or "")) in keep
            ]
            if filtered:
                entity_candidates_by_chunk[chunk_id] = filtered
            else:
                entity_candidates_by_chunk.pop(chunk_id, None)

    _latest_entity_candidates_by_chunk.clear()
    _latest_entity_candidates_by_chunk.update(entity_candidates_by_chunk)
    _latest_entity_candidates_flat = list(flat_candidates)

    return {
        "resolved_graph_reference_id": resolved_graph_id or None,
        "entity_candidates": flat_candidates,
        "entity_candidates_by_chunk": entity_candidates_by_chunk,
        "candidate_summary": {
            "n_chunks_with_candidates": len(entity_candidates_by_chunk),
            "n_candidates": len(flat_candidates),
        },
    }


async def _ensure_corpus(dataset_name: str, input_directory: str | None) -> None:
    """Auto-prepare corpus if Corpus.json doesn't exist and input_directory is given."""
    config = _state["config"]
    corpus_paths = [
        Path(config.working_dir) / dataset_name / "Corpus.json",
        Path(config.working_dir) / dataset_name / "corpus" / "Corpus.json",
    ]
    if hasattr(config, "data_root"):
        corpus_paths.append(Path(config.data_root) / dataset_name / "Corpus.json")

    if any(p.exists() for p in corpus_paths):
        return

    if input_directory is None:
        raise RuntimeError(
            f"No Corpus.json found for dataset '{dataset_name}'. "
            f"Run corpus_prepare first, or pass input_directory to auto-prepare. "
            f"Searched: {[str(p) for p in corpus_paths]}"
        )

    logger.info(f"Auto-preparing corpus for '{dataset_name}' from '{input_directory}'")
    result_str = await corpus_prepare(input_directory, dataset_name)
    result = json.loads(result_str)
    if result.get("status") != "success":
        raise RuntimeError(f"Auto corpus_prepare failed: {result.get('message', 'unknown')}")
    logger.info(f"Auto-prepared corpus: {result.get('document_count', 0)} documents")


async def _register_graph_if_built(result: Any) -> None:
    """Register a successfully built graph into the GraphRAGContext.

    Replicates the orchestrator's post-build registration logic so that
    subsequent tools (VDB build, entity search, etc.) can find the graph.
    """
    if result is None:
        return
    if not (hasattr(result, "graph_id") and hasattr(result, "status")):
        return
    if result.status != "success" or not result.graph_id:
        return

    ctx = _state["context"]
    graph_instance = getattr(result, "graph_instance", None)

    if graph_instance:
        artifact_dataset_name = getattr(result, "artifact_dataset_name", None)
        if not artifact_dataset_name:
            artifact_dataset_name = result.graph_id
            for suffix in ["_ERGraph", "_RKGraph", "_TreeGraphBalanced", "_TreeGraph", "_PassageGraph"]:
                if artifact_dataset_name.endswith(suffix):
                    artifact_dataset_name = artifact_dataset_name[: -len(suffix)]
                    break
        source_dataset_name = getattr(result, "source_dataset_name", None)
        if source_dataset_name:
            graph_instance.source_dataset_name = source_dataset_name
        graph_instance.artifact_dataset_name = artifact_dataset_name
        # Set namespace so chunk lookups work
        if hasattr(graph_instance, "_graph") and hasattr(graph_instance._graph, "namespace"):
            graph_instance._graph.namespace = _state["chunk_factory"].get_namespace(
                artifact_dataset_name
            )

        ctx.add_graph_instance(result.graph_id, graph_instance)


# =============================================================================
# CORPUS TOOLS
# =============================================================================

async def corpus_prepare(input_directory: str, dataset_name: str) -> str:
    """Prepare documents from a directory into a Corpus.json for DIGIMON processing.

    Supported formats: .txt, .md, .json, .jsonl, .csv, .pdf
    For structured formats (JSON, CSV), auto-detects content and title fields.

    Args:
        input_directory: Path to directory containing source files (relative to project root or absolute)
        dataset_name: Name for this dataset (used to namespace all artifacts)

    Returns:
        status: str, corpus_path: str, num_documents: int
    """
    await _ensure_initialized()
    from Core.AgentTools.corpus_tools import prepare_corpus_from_directory
    from Core.AgentSchema.corpus_tool_contracts import PrepareCorpusInputs

    project_root = _get_project_root()
    if not os.path.isabs(input_directory):
        input_directory = os.path.join(project_root, input_directory)

    output_dir = os.path.join(project_root, "results", dataset_name, "corpus")
    os.makedirs(output_dir, exist_ok=True)

    inputs = PrepareCorpusInputs(
        input_directory_path=input_directory,
        output_directory_path=output_dir,
        target_corpus_name=dataset_name,
    )
    result = await prepare_corpus_from_directory(inputs, _state["config"])
    return _format_result(result)

if not BENCHMARK_MODE:
    corpus_prepare = mcp.tool()(corpus_prepare)


# =============================================================================
# GRAPH CONSTRUCTION TOOLS
# =============================================================================

def _tag_llm_for_build(graph_type: str, dataset_name: str) -> None:
    """Set task and trace_id on the build LLM before graph construction."""
    llm = _state.get("llm")
    if llm is not None and hasattr(llm, "set_task"):
        llm.set_task(f"digimon.graph_build_{graph_type}")
    if llm is not None and hasattr(llm, "set_trace_id"):
        trace_id = f"digimon.graph_build_{graph_type}.{dataset_name}.{uuid.uuid4().hex[:8]}"
        llm.set_trace_id(trace_id)


async def graph_build_er(dataset_name: str, force_rebuild: bool = False,
                          input_directory: str = None,
                          config_overrides: dict = None) -> str:
    """Build an Entity-Relationship (ER) knowledge graph from a prepared corpus.
    Extracts entities (with types and descriptions) and relationships using LLM.
    Best for general-purpose KG. Uses single-step delimiter extraction by default,
    which produces entity types, entity descriptions, and relation descriptions.

    If no Corpus.json exists and input_directory is provided, auto-prepares the corpus first.

    Args:
        dataset_name: Name of the dataset (must have corpus prepared, or pass input_directory)
        force_rebuild: Force rebuild even if graph exists
        input_directory: Path to source files for auto corpus preparation (optional)
        config_overrides: Optional dict of graph config overrides. Supported fields:
            enable_entity_description (bool), enable_entity_type (bool),
            enable_edge_description (bool), enable_edge_name (bool),
            enable_chunk_cooccurrence (bool, add implicit edges between co-occurring entities),
            max_gleaning (int, 1=off, 2-3 recommended), extract_two_step (bool)

    Returns:
        graph_id: str, status: str, num_nodes: int, num_edges: int
    """
    await _ensure_initialized()
    await _ensure_corpus(dataset_name, input_directory)
    _tag_llm_for_build("er", dataset_name)
    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs, ERGraphConfigOverrides

    overrides = ERGraphConfigOverrides(**config_overrides) if config_overrides else None
    inputs = BuildERGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
        config_overrides=overrides,
    )
    result = await build_er_graph(inputs, _state["config"], _state["llm"],
                                   _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


async def graph_build_rk(dataset_name: str, force_rebuild: bool = False,
                          input_directory: str = None,
                          config_overrides: dict = None) -> str:
    """Build an RK (Relationship-Keyword) graph. Like ER but with keyword-enriched edges.

    If no Corpus.json exists and input_directory is provided, auto-prepares the corpus first.

    Args:
        dataset_name: Name of the dataset (must have corpus prepared, or pass input_directory)
        force_rebuild: Force rebuild even if graph exists
        input_directory: Path to source files for auto corpus preparation (optional)
        config_overrides: Optional dict of graph config overrides. Supported fields:
            enable_edge_keywords (bool), max_gleaning (int),
            enable_entity_description (bool)

    Returns:
        graph_id: str, status: str, num_nodes: int, num_edges: int
    """
    await _ensure_initialized()
    await _ensure_corpus(dataset_name, input_directory)
    _tag_llm_for_build("rk", dataset_name)
    from Core.AgentTools.graph_construction_tools import build_rk_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildRKGraphInputs, RKGraphConfigOverrides

    overrides = RKGraphConfigOverrides(**config_overrides) if config_overrides else None
    inputs = BuildRKGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
        config_overrides=overrides,
    )
    result = await build_rk_graph(inputs, _state["config"], _state["llm"],
                                   _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


async def graph_build_tree(dataset_name: str, force_rebuild: bool = False,
                            input_directory: str = None,
                            config_overrides: dict = None) -> str:
    """Build a hierarchical Tree graph (RAPTOR-style). Clusters chunks and creates summaries at multiple levels.

    If no Corpus.json exists and input_directory is provided, auto-prepares the corpus first.

    Args:
        dataset_name: Name of the dataset (must have corpus prepared, or pass input_directory)
        force_rebuild: Force rebuild even if graph exists
        input_directory: Path to source files for auto corpus preparation (optional)
        config_overrides: Optional dict of tree config overrides. Supported fields:
            num_layers (int), reduction_dimension (int), threshold (float),
            summarization_length (int), max_length_in_cluster (int),
            cluster_metric (str), random_seed (int)

    Returns:
        graph_id: str, status: str, num_nodes: int, num_edges: int
    """
    await _ensure_initialized()
    _ensure_embedding_provider_initialized(reason="graph_build_tree")
    await _ensure_corpus(dataset_name, input_directory)
    _tag_llm_for_build("tree", dataset_name)
    from Core.AgentTools.graph_construction_tools import build_tree_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildTreeGraphInputs, TreeGraphConfigOverrides

    overrides = TreeGraphConfigOverrides(**config_overrides) if config_overrides else None
    inputs = BuildTreeGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
        config_overrides=overrides,
    )
    result = await build_tree_graph(inputs, _state["config"], _state["llm"],
                                     _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


async def graph_build_tree_balanced(dataset_name: str, force_rebuild: bool = False,
                                     input_directory: str = None,
                                     config_overrides: dict = None) -> str:
    """Build a balanced Tree graph using K-Means clustering for more uniform cluster sizes.

    If no Corpus.json exists and input_directory is provided, auto-prepares the corpus first.

    Args:
        dataset_name: Name of the dataset (must have corpus prepared, or pass input_directory)
        force_rebuild: Force rebuild even if graph exists
        input_directory: Path to source files for auto corpus preparation (optional)
        config_overrides: Optional dict of tree config overrides. Supported fields:
            num_layers (int), summarization_length (int), size_of_clusters (int),
            max_size_percentage (float), max_iter (int), tol (float), random_seed (int)

    Returns:
        graph_id: str, status: str, num_nodes: int, num_edges: int
    """
    await _ensure_initialized()
    _ensure_embedding_provider_initialized(reason="graph_build_tree_balanced")
    await _ensure_corpus(dataset_name, input_directory)
    _tag_llm_for_build("tree_balanced", dataset_name)
    from Core.AgentTools.graph_construction_tools import build_tree_graph_balanced
    from Core.AgentSchema.graph_construction_tool_contracts import BuildTreeGraphBalancedInputs, TreeGraphBalancedConfigOverrides

    overrides = TreeGraphBalancedConfigOverrides(**config_overrides) if config_overrides else None
    inputs = BuildTreeGraphBalancedInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
        config_overrides=overrides,
    )
    result = await build_tree_graph_balanced(inputs, _state["config"], _state["llm"],
                                              _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


async def graph_build_passage(dataset_name: str, force_rebuild: bool = False,
                               input_directory: str = None,
                               config_overrides: dict = None) -> str:
    """Build a Passage graph where nodes are text passages linked by shared entities.

    If no Corpus.json exists and input_directory is provided, auto-prepares the corpus first.

    Args:
        dataset_name: Name of the dataset (must have corpus prepared, or pass input_directory)
        force_rebuild: Force rebuild even if graph exists
        input_directory: Path to source files for auto corpus preparation (optional)
        config_overrides: Optional dict of passage graph config overrides. Supported fields:
            prior_prob (float)

    Returns:
        graph_id: str, status: str, num_nodes: int, num_edges: int
    """
    await _ensure_initialized()
    await _ensure_corpus(dataset_name, input_directory)
    _tag_llm_for_build("passage", dataset_name)
    from Core.AgentTools.graph_construction_tools import build_passage_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildPassageGraphInputs, PassageGraphConfigOverrides

    overrides = PassageGraphConfigOverrides(**config_overrides) if config_overrides else None
    inputs = BuildPassageGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
        config_overrides=overrides,
    )
    result = await build_passage_graph(inputs, _state["config"], _state["llm"],
                                        _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


# =============================================================================
# ENTITY TOOLS
# =============================================================================

async def entity_vdb_build(graph_reference_id: str, vdb_collection_name: str,
                           force_rebuild: bool = False) -> str:
    """Build a vector database index from entities in a graph. Required before entity_vdb_search.

    Args:
        graph_reference_id: ID of the graph (e.g. 'Fictional_Test_ERGraph')
        vdb_collection_name: Name for the VDB collection (e.g. 'Fictional_Test_entities')
        force_rebuild: Force rebuild even if VDB exists

    Returns:
        status: str, vdb_id: str, num_entities_indexed: int
    """
    await _ensure_initialized()
    _ensure_embedding_provider_initialized(reason="entity_vdb_build")
    from Core.AgentTools.entity_vdb_tools import entity_vdb_build_tool
    from Core.AgentSchema.tool_contracts import EntityVDBBuildInputs

    inputs = EntityVDBBuildInputs(
        graph_reference_id=graph_reference_id,
        vdb_collection_name=vdb_collection_name,
        force_rebuild=force_rebuild,
    )
    result = await entity_vdb_build_tool(inputs, _state["context"])
    return _format_result(result)

# Register build/infrastructure tools only when NOT in benchmark mode.
# In benchmark mode, the graph and VDB are pre-built — exposing these wastes
# ~15s/question on redundant no-op calls.
if not BENCHMARK_MODE:
    graph_build_er = mcp.tool()(graph_build_er)
    graph_build_rk = mcp.tool()(graph_build_rk)
    graph_build_tree = mcp.tool()(graph_build_tree)
    graph_build_tree_balanced = mcp.tool()(graph_build_tree_balanced)
    graph_build_passage = mcp.tool()(graph_build_passage)
    entity_vdb_build = mcp.tool()(entity_vdb_build)


@mcp.tool()
async def entity_vdb_search(
    vdb_reference_id: str = "",
    query_text: str = "",
    top_k: int = 5,
    dataset_name: str = "",
    query: str = "",
) -> str:
    """Search for entities similar to a query using vector similarity.

    Args:
        vdb_reference_id: ID of the entity VDB to search (or dataset alias)
        query_text: Natural language search query
        top_k: Number of results to return

    Returns:
        similar_entities: list of {entity_name: str, score: float, node_id: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_tools import entity_vdb_search_tool
    from Core.AgentSchema.tool_contracts import EntityVDBSearchInputs

    requested_query = (query_text or query or "").strip()
    effective_query, query_contract = _build_retrieval_query_contract(
        requested_query,
        tool_name="entity_vdb_search",
    )
    if not effective_query:
        return json.dumps({"error": "query_text is required"})

    resolved_vdb = _resolve_vdb_reference_id(
        vdb_reference_id=vdb_reference_id,
        dataset_name=dataset_name,
        kind="entity",
    )
    if not resolved_vdb:
        ctx = _state.get("context")
        known_vdbs = ctx.list_vdbs() if ctx is not None and hasattr(ctx, "list_vdbs") else []
        return json.dumps(
            {
                "error": (
                    f"Could not resolve entity VDB from vdb_reference_id={vdb_reference_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
                "known_vdbs": known_vdbs,
            },
            indent=2,
        )

    query_variants = _build_entity_query_variants(effective_query)
    ranked_lists: list[list[dict]] = []

    for variant in query_variants:
        inputs = EntityVDBSearchInputs(
            vdb_reference_id=resolved_vdb,
            query_text=variant,
            top_k_results=top_k,
        )
        result = await entity_vdb_search_tool(inputs, _state["context"])
        payload = _normalize_entity_search_payload(result)
        entities = payload.get("similar_entities") or []
        if isinstance(entities, list):
            ranked_lists.append(entities)

    merged: dict[str, dict[str, Any]] = {}
    for entities in ranked_lists:
        for rank, item in enumerate(entities, start=1):
            node_id = str(item.get("node_id") or item.get("entity_name") or "").strip()
            if not node_id:
                continue
            entry = merged.setdefault(node_id, {
                "node_id": node_id,
                "entity_name": str(item.get("entity_name") or node_id),
                "score": item.get("score"),
                "_rrf": 0.0,
            })
            entry["_rrf"] += 1.0 / (50.0 + rank)  # reciprocal rank fusion

            # Keep the best numeric score we have for visibility.
            try:
                score_val = float(item.get("score"))
                prev = entry.get("score")
                prev_val = float(prev) if prev is not None else None
                if prev_val is None or score_val > prev_val:
                    entry["score"] = score_val
            except (TypeError, ValueError):
                pass

    merged_sorted = sorted(
        merged.values(),
        key=lambda x: (x.get("_rrf", 0.0), x.get("score") if isinstance(x.get("score"), (int, float)) else 0.0),
        reverse=True,
    )[:top_k]
    for item in merged_sorted:
        item.pop("_rrf", None)

    payload = {
        "similar_entities": merged_sorted,
        "resolved_vdb_reference_id": resolved_vdb,
        "query_contract": query_contract,
    }
    if len(query_variants) > 1:
        payload["query_variants_used"] = query_variants

    hints = _build_entity_search_guidance(merged_sorted)
    if hints:
        payload["search_guidance"] = hints

    return json.dumps(payload, indent=2, default=str)


@mcp.tool()
async def entity_onehop(
    entity_ids: list[str] | None = None,
    graph_reference_id: str = "",
    entity_name: str = "",
    dataset_name: str = "",
    top_k: int | None = None,
    neighbor_limit_per_entity: int | None = None,
) -> str:
    """Find one-hop neighbor entities in the graph.

    Args:
        entity_ids: List of entity IDs to find neighbors for
        graph_reference_id: ID of the graph to search
        top_k: Optional alias for neighbor_limit_per_entity
        neighbor_limit_per_entity: Optional cap of neighbors per input entity

    Returns:
        neighbors: {entity_id: [{...}]}, total_neighbors_found: int, message: str
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_onehop_tools import entity_onehop_neighbors_tool

    normalized_entity_ids = list(entity_ids or [])
    if not normalized_entity_ids and entity_name:
        normalized_entity_ids = [entity_name]
    if not normalized_entity_ids:
        return json.dumps({"error": "entity_ids (or entity_name) is required"}, indent=2)

    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id=graph_reference_id,
        dataset_name=dataset_name,
    )
    if not resolved_graph_id:
        return json.dumps(
            {
                "error": (
                    f"Could not resolve graph_reference_id from graph_reference_id={graph_reference_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
            },
            indent=2,
        )

    effective_neighbor_limit = neighbor_limit_per_entity
    if effective_neighbor_limit is None and top_k is not None:
        effective_neighbor_limit = top_k
    if effective_neighbor_limit is not None and int(effective_neighbor_limit) <= 0:
        return json.dumps(
            {"error": "neighbor_limit_per_entity/top_k must be a positive integer"},
            indent=2,
        )

    inputs = {
        "entity_ids": normalized_entity_ids,
        "graph_reference_id": resolved_graph_id,
    }
    if effective_neighbor_limit is not None:
        inputs["neighbor_limit_per_entity"] = int(effective_neighbor_limit)
    result = await entity_onehop_neighbors_tool(inputs, _state["context"])
    formatted = _format_result(result)
    try:
        payload = json.loads(formatted)
        if isinstance(payload, dict):
            payload["resolved_graph_reference_id"] = resolved_graph_id
            return json.dumps(payload, indent=2, default=str)
    except Exception:
        pass
    return formatted


@mcp.tool()
async def entity_ppr(graph_reference_id: str, seed_entity_ids: list[str],
                     top_k: int = 10) -> str:
    """Run Personalized PageRank from seed entities to find related entities.

    Args:
        graph_reference_id: ID of the graph
        seed_entity_ids: Starting entity IDs for PPR
        top_k: Number of top-ranked entities to return

    Returns:
        ranked_entities: list of [entity_id: str, score: float]
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_tools import entity_ppr_tool
    from Core.AgentSchema.tool_contracts import EntityPPRInputs

    inputs = EntityPPRInputs(
        graph_reference_id=graph_reference_id,
        seed_entity_ids=seed_entity_ids,
        top_k_results=top_k,
    )
    result = await entity_ppr_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# ENTITY OPERATORS (NEW)
# =============================================================================

@mcp.tool()
async def entity_agent(query_text: str, text_context: str,
                       target_entity_types: list[str] = None,
                       max_entities: int = 10) -> str:
    """Use LLM to extract entities from text guided by a query.

    Args:
        query_text: Query to guide entity extraction
        text_context: Text content to extract entities from
        target_entity_types: Entity types to focus on (e.g. ['person', 'organization'])
        max_entities: Maximum entities to extract

    Returns:
        extracted_entities: list of {entity_name: str, entity_type: str, description?: str, extraction_confidence?: float}
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_tools import entity_agent_tool
    from Core.AgentSchema.tool_contracts import EntityAgentInputs

    inputs = EntityAgentInputs(
        query_text=query_text,
        text_context=text_context,
        target_entity_types=target_entity_types,
        max_entities_to_extract=max_entities,
    )
    result = await entity_agent_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def entity_string_search(
    query: str,
    graph_reference_id: str = "",
    dataset_name: str = "",
    top_k: int = 10,
) -> str:
    """Find entities by exact or substring match on entity names in the graph.

    Use this when you already know (or suspect) the entity name. Much faster
    and more precise than VDB search for known names. Returns matching entity
    names with their types and descriptions.

    Args:
        query: Entity name or substring to search for (case-insensitive)
        graph_reference_id: Graph to search (e.g. 'MuSiQue_ERGraph')
        dataset_name: Dataset alias (resolved to graph_reference_id if needed)
        top_k: Maximum results to return

    Returns:
        matches: list of {entity_name, entity_type, description, match_type}
    """
    await _ensure_initialized()
    effective_query, query_contract = _build_retrieval_query_contract(
        query,
        tool_name="entity_string_search",
    )
    if not effective_query.strip():
        return json.dumps({"error": "query is required"})

    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id=graph_reference_id,
        dataset_name=dataset_name,
    )
    if not resolved_graph_id:
        return json.dumps({"error": f"Could not resolve graph from {graph_reference_id!r} / {dataset_name!r}"})

    graph_instance = _state["context"].get_graph_instance(resolved_graph_id)
    if graph_instance is None:
        return json.dumps({"error": f"Graph '{resolved_graph_id}' not found in context"})

    storage = graph_instance._graph
    G = storage._graph if hasattr(storage, '_graph') else None
    if G is None:
        return json.dumps({"error": "Could not access NetworkX graph"})

    def _entity_aliases(attrs: Dict[str, Any]) -> tuple[str, ...]:
        """Extract de-duplicated aliases from graph node attributes."""

        aliases: list[str] = []
        seen: set[str] = set()
        for key in ("aliases", "alias", "aka", "surface_forms", "names"):
            raw_value = attrs.get(key)
            if isinstance(raw_value, str):
                values = [raw_value]
            elif isinstance(raw_value, (list, tuple, set)):
                values = [str(v) for v in raw_value if v is not None]
            else:
                values = []
            for value in values:
                alias = re.sub(r"\s+", " ", value.strip())
                if not alias:
                    continue
                alias_key = alias.casefold()
                if alias_key in seen:
                    continue
                seen.add(alias_key)
                aliases.append(alias)
        return tuple(aliases)

    def _entity_type(attrs: Dict[str, Any]) -> str:
        """Return the most informative available entity type for a node."""

        return (
            str(attrs.get("entity_type") or "").strip()
            or str(attrs.get("type") or "").strip()
            or str(attrs.get("category") or "").strip()
            or str(attrs.get("label") or "").strip()
        )

    def _entity_description(attrs: Dict[str, Any]) -> str:
        """Return a compact description preview for one search result."""

        for key in ("description", "summary", "text", "content"):
            value = str(attrs.get(key) or "").strip()
            if value:
                return value[:200]
        return ""

    scored: list[tuple[float, str, str, Dict[str, Any]]] = []
    for raw_node_id in G.nodes():
        node_id = str(raw_node_id)
        valid, _ = classify_entity_name(node_id)
        if not valid:
            continue

        attrs = dict(G.nodes[raw_node_id])
        aliases = _entity_aliases(attrs)
        match = score_entity_candidate(query_text=effective_query, candidate_name=node_id, aliases=aliases)
        if match.score <= 0:
            continue
        scored.append((match.score, node_id, match.match_type, attrs))

    scored.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    results = []
    for score, node_id, match_type, attrs in scored[:top_k]:
        results.append({
            "entity_name": node_id,
            "canonical_name": str(attrs.get("entity_name") or attrs.get("name") or attrs.get("title") or node_id).strip()
            or node_id,
            "entity_type": _entity_type(attrs),
            "description": _entity_description(attrs),
            "match_type": match_type,
            "match_score": score,
        })

    return json.dumps(
        {
            "matches": results,
            "total_matches": len(scored),
            "query_contract": query_contract,
            "resolved_graph_reference_id": resolved_graph_id,
            "dataset_name": dataset_name,
        },
        indent=2,
    )


@mcp.tool()
async def entity_neighborhood(
    entity_names: list[str] | str,
    graph_reference_id: str = "",
    dataset_name: str = "",
    hops: int = 1,
    max_nodes: int = 30,
) -> str:
    """Get the full subgraph neighborhood around one or more entities.

    Returns ALL nodes and edges within N hops in a single response, so you
    can reason across relationships simultaneously. Use this instead of
    multiple relationship_onehop calls when you need to see how entities
    connect to each other.

    Best for multi-hop questions: start from a seed entity, get its 1-2 hop
    neighborhood, then identify the chain that answers the question.
    Prioritizes extracted relationships (with descriptions) over co-occurrence
    edges when limiting results.

    Args:
        entity_names: One or more entity names to center the neighborhood on
        graph_reference_id: Graph to query (e.g. 'MuSiQue_ERGraph')
        dataset_name: Dataset alias (resolved to graph if needed)
        hops: Number of hops from seed entities (1 or 2, default 1)
        max_nodes: Maximum nodes to return (default 30)

    Returns:
        nodes: list of {name, type, description}
        edges: list of {source, target, relation_name, description, weight}
        seed_entities: which seeds were found in the graph
    """
    await _ensure_initialized()
    import re as _re

    normalized_names = _normalize_string_list(entity_names)
    if not normalized_names:
        return json.dumps({"error": "entity_names is required"})

    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id=graph_reference_id,
        dataset_name=dataset_name,
    )
    if not resolved_graph_id:
        return json.dumps({"error": f"Could not resolve graph from {graph_reference_id!r} / {dataset_name!r}"})

    graph_instance = _state["context"].get_graph_instance(resolved_graph_id)
    if graph_instance is None:
        return json.dumps({"error": f"Graph '{resolved_graph_id}' not found in context"})

    storage = graph_instance._graph
    G = storage._graph if hasattr(storage, '_graph') else None
    if G is None:
        return json.dumps({"error": "Could not access NetworkX graph"})

    hops = max(1, min(hops, 2))  # clamp to 1-2

    # Resolve entity names to graph node IDs (with normalization)
    seeds_found = []
    seed_node_ids = set()
    for name in normalized_names:
        if G.has_node(name):
            seeds_found.append(name)
            seed_node_ids.add(name)
        else:
            # Normalize: lowercase, strip punctuation
            normalized = _re.sub(r'[^a-z0-9\s]', ' ', name.lower()).strip()
            normalized = _re.sub(r'\s+', ' ', normalized)
            if G.has_node(normalized):
                seeds_found.append(normalized)
                seed_node_ids.add(normalized)

    # Expand seeds with common abbreviation aliases (saint↔st, mount↔mt, etc.).
    # The graph still stores normalized text strings rather than a dedicated alias
    # index, so keep this low-cost recall bridge until entity aliases become a
    # first-class build artifact.
    _ALIAS_PAIRS = [("saint", "st"), ("mount", "mt"), ("fort", "ft"), ("doctor", "dr")]
    alias_seeds = set()
    for seed in list(seed_node_ids):
        seed_lower = seed.lower()
        for long_form, short_form in _ALIAS_PAIRS:
            if f" {long_form} " in f" {seed_lower} " or seed_lower.startswith(f"{long_form} "):
                variant = _re.sub(rf'\b{long_form}\b', short_form, seed_lower)
                for v in [variant, variant.replace(f"{short_form} ", f"{short_form}  ")]:
                    if G.has_node(v) and v not in seed_node_ids:
                        alias_seeds.add(v)
            elif f" {short_form} " in f" {seed_lower} " or seed_lower.startswith(f"{short_form} "):
                variant = _re.sub(rf'\b{short_form}\b', long_form, seed_lower)
                for v in [variant, variant.replace(f"{long_form} ", f"{long_form}  ")]:
                    if G.has_node(v) and v not in seed_node_ids:
                        alias_seeds.add(v)
    if alias_seeds:
        seed_node_ids.update(alias_seeds)
        seeds_found.extend(sorted(alias_seeds))

    if not seed_node_ids:
        return json.dumps({
            "error": f"None of the entities {normalized_names} found in graph",
            "hint": "Try entity_string_search to find the correct entity name",
        })

    # Collect N-hop neighborhood
    neighborhood = set(seed_node_ids)
    for _ in range(hops):
        next_layer = set()
        for node in neighborhood:
            next_layer.update(G.neighbors(node))
        neighborhood.update(next_layer)
        if len(neighborhood) > max_nodes:
            break

    # If too many nodes, prioritize: extracted relationships (high weight) over co-occurrence
    if len(neighborhood) > max_nodes:
        scored_nodes = []
        for node in neighborhood - seed_node_ids:
            best_weight = 0
            has_extracted_rel = False
            for seed in seed_node_ids:
                for u, v in [(seed, node), (node, seed)]:
                    edge_data = G.get_edge_data(u, v)
                    if edge_data:
                        w = edge_data.get('weight', 0.5)
                        rname = edge_data.get('relation_name', '')
                        if rname != 'chunk_cooccurrence':
                            has_extracted_rel = True
                            w += 100  # strongly prefer extracted relationships
                        best_weight = max(best_weight, w)
            scored_nodes.append((node, best_weight, has_extracted_rel))
        scored_nodes.sort(key=lambda x: -x[1])
        neighborhood = seed_node_ids | {n for n, _, _ in scored_nodes[:max_nodes - len(seed_node_ids)]}

    # Build node list
    nodes_out = []
    for node in sorted(neighborhood):
        attrs = G.nodes.get(node, {})
        desc = (attrs.get('description', '') or '').split('<SEP>')[0][:200]
        nodes_out.append({
            "name": node,
            "type": attrs.get('entity_type', ''),
            "description": desc,
            "is_seed": node in seed_node_ids,
        })

    # Build edge list (only edges between neighborhood nodes)
    edges_out = []
    for u, v, data in G.edges(data=True):
        if u in neighborhood and v in neighborhood:
            rname = data.get('relation_name', '')
            desc = (data.get('description', '') or '').split('<SEP>')[0][:150]
            weight = data.get('weight', None)
            source_chunks = data.get('source_id', '')
            edge = {
                "source": u,
                "target": v,
                "relation": rname,
            }
            if desc:
                edge["description"] = desc
            if weight is not None:
                edge["weight"] = weight
            if source_chunks and rname == 'chunk_cooccurrence':
                # For co-occurrence edges, include chunk IDs so agent can read them
                chunk_ids = [c.strip() for c in str(source_chunks).split('<SEP>') if c.strip()][:3]
                if chunk_ids:
                    edge["source_chunks"] = chunk_ids
            edges_out.append(edge)

    return json.dumps({
        "seed_entities": seeds_found,
        "nodes": nodes_out,
        "edges": edges_out,
        "n_nodes": len(nodes_out),
        "n_edges": len(edges_out),
    }, indent=2)


@mcp.tool()
async def entity_link(
                      source_entities: list[str] | str | None = None,
                      vdb_reference_id: str = "",
                      similarity_threshold: float = 0.5,
                      dataset_name: str = "",
                      entity_names: list[str] | str | None = None) -> str:
    """Link entity mentions to canonical entities in a VDB.

    Args:
        source_entities: Entity mention strings to link
        vdb_reference_id: VDB to search for canonical matches
        similarity_threshold: Minimum score to consider a match

    Returns:
        linked_entities_results: list of {source_entity_mention: str, linked_entity_id?: str, similarity_score?: float, link_status: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_tools import entity_link_tool
    from Core.AgentSchema.tool_contracts import EntityLinkInputs
    normalized_source_entities = _normalize_string_list(source_entities)
    if not normalized_source_entities and entity_names is not None:
        normalized_source_entities = _normalize_string_list(entity_names)
    if not normalized_source_entities:
        return json.dumps({"error": "source_entities (or entity_names) is required"}, indent=2)

    resolved_vdb = _resolve_vdb_reference_id(
        vdb_reference_id=vdb_reference_id,
        dataset_name=dataset_name or vdb_reference_id,
        kind="entity",
    )
    if not resolved_vdb:
        ctx = _state.get("context")
        known_vdbs = ctx.list_vdbs() if ctx is not None and hasattr(ctx, "list_vdbs") else []
        return json.dumps(
            {
                "error": (
                    f"Could not resolve entity VDB from vdb_reference_id={vdb_reference_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
                "known_vdbs": known_vdbs,
            },
            indent=2,
        )

    inputs = EntityLinkInputs(
        source_entities=normalized_source_entities,
        knowledge_base_reference_id=resolved_vdb,
        similarity_threshold=similarity_threshold,
    )
    result = await entity_link_tool(inputs, _state["context"])
    formatted = _format_result(result)
    try:
        payload = json.loads(formatted)
    except Exception:
        payload = {}
    if isinstance(payload, dict):
        payload["resolved_vdb_reference_id"] = resolved_vdb
        return json.dumps(payload, indent=2, default=str)
    return formatted


@mcp.tool()
async def entity_resolve_names_to_ids(
    entity_names: list[str] | str | None,
    vdb_reference_id: str = "",
    dataset_name: str = "",
    top_k_per_name: int = 3,
    similarity_threshold: float = 0.0,
    expected_coarse_types: list[str] | str | None = None,
) -> str:
    """Resolve free-form entity names into canonical entity IDs via entity VDB search.

    This is a composability conversion operator:
    - input: names/candidates
    - output: canonical IDs for downstream graph tools
    """
    await _ensure_initialized()
    normalized_names = _normalize_string_list(entity_names)

    if not normalized_names:
        return json.dumps({"error": "entity_names is required"}, indent=2)

    resolved_vdb = _resolve_vdb_reference_id(
        vdb_reference_id=vdb_reference_id,
        dataset_name=dataset_name,
        kind="entity",
    )
    if not resolved_vdb:
        return json.dumps(
            {
                "error": (
                    f"Could not resolve entity VDB from vdb_reference_id={vdb_reference_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
            },
            indent=2,
        )

    resolved_entities: list[dict[str, Any]] = []
    unresolved_entity_names: list[str] = []
    expected_types_norm = {
        _normalize_coarse_type(v)
        for v in _normalize_string_list(expected_coarse_types, split_commas=True)
        if v
    }
    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id="",
        dataset_name=dataset_name,
    )
    graph_instance = None
    nx_graph = None
    if resolved_graph_id:
        ctx = _state.get("context")
        graph_instance = (
            ctx.get_graph_instance(resolved_graph_id)
            if ctx is not None and hasattr(ctx, "get_graph_instance")
            else None
        )
        if (
            graph_instance is not None
            and hasattr(graph_instance, "_graph")
            and hasattr(graph_instance._graph, "graph")
        ):
            nx_graph = graph_instance._graph.graph

    for entity_name in normalized_names:
        exact_entity_id: str | None = None
        if nx_graph is not None:
            try:
                from Core.Common.Utils import clean_str
            except Exception:
                clean_str = lambda x: x  # type: ignore[assignment]
            for candidate in (entity_name, clean_str(entity_name)):
                candidate_norm = str(candidate or "").strip()
                if not candidate_norm or candidate_norm not in nx_graph:
                    continue
                candidate_type = _lookup_entity_coarse_type(
                    entity_id=candidate_norm,
                    dataset_name=dataset_name,
                )
                if expected_types_norm and not _coarse_type_matches(candidate_type, expected_types_norm):
                    continue
                exact_entity_id = candidate_norm
                break
        if exact_entity_id is not None:
            resolved_entities.append(
                {
                    "source_entity_name": entity_name,
                    "resolved_entity_id": exact_entity_id,
                    "resolved_entity_name": exact_entity_id,
                    "coarse_type": _lookup_entity_coarse_type(
                        entity_id=exact_entity_id,
                        dataset_name=dataset_name,
                    ),
                    "score": 1.0,
                    "resolution_mode": "graph_exact_match",
                    "top_candidates": [
                        {
                            "entity_id": exact_entity_id,
                            "entity_name": exact_entity_id,
                            "coarse_type": _lookup_entity_coarse_type(
                                entity_id=exact_entity_id,
                                dataset_name=dataset_name,
                            ),
                            "score": 1.0,
                        }
                    ],
                }
            )
            continue

        raw_payload = await entity_vdb_search(
            vdb_reference_id=resolved_vdb,
            query_text=entity_name,
            top_k=max(1, int(top_k_per_name)),
            dataset_name=dataset_name,
        )
        try:
            payload = json.loads(raw_payload)
        except Exception:
            payload = {}

        candidates = payload.get("similar_entities") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            candidates = []

        best: dict[str, Any] | None = None
        best_score = float("-inf")
        for item in candidates:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("node_id") or item.get("entity_name") or "").strip()
            if not entity_id:
                continue
            candidate_type = _lookup_entity_coarse_type(
                entity_id=entity_id,
                dataset_name=dataset_name,
            )
            if expected_types_norm and not _coarse_type_matches(candidate_type, expected_types_norm):
                continue
            score_raw = item.get("score")
            try:
                score = float(score_raw)
            except (TypeError, ValueError):
                score = None

            if score is not None and score < float(similarity_threshold):
                continue

            if best is None:
                best = item
                best_score = score if score is not None else 0.0
                continue
            if score is not None and score > best_score:
                best = item
                best_score = score

        if best is None:
            unresolved_entity_names.append(entity_name)
            continue

        resolved_entities.append(
            {
                "source_entity_name": entity_name,
                "resolved_entity_id": str(best.get("node_id") or best.get("entity_name") or "").strip(),
                "resolved_entity_name": str(best.get("entity_name") or "").strip() or None,
                "coarse_type": _lookup_entity_coarse_type(
                    entity_id=str(best.get("node_id") or best.get("entity_name") or "").strip(),
                    dataset_name=dataset_name,
                ),
                "score": best.get("score"),
                "resolution_mode": "entity_vdb_search",
                "top_candidates": [
                    {
                        "entity_id": str(c.get("node_id") or c.get("entity_name") or "").strip(),
                        "entity_name": c.get("entity_name"),
                        "coarse_type": _lookup_entity_coarse_type(
                            entity_id=str(c.get("node_id") or c.get("entity_name") or "").strip(),
                            dataset_name=dataset_name,
                        ),
                        "score": c.get("score"),
                    }
                    for c in candidates[: max(1, int(top_k_per_name))]
                    if isinstance(c, dict)
                ],
            }
        )

    return json.dumps(
        {
            "resolved_entities": resolved_entities,
            "unresolved_entity_names": unresolved_entity_names,
            "resolved_vdb_reference_id": resolved_vdb,
            "expected_coarse_types": sorted(expected_types_norm) if expected_types_norm else [],
            "status_message": (
                f"Resolved {len(resolved_entities)}/{len(normalized_names)} entity names to IDs"
            ),
        },
        indent=2,
        default=str,
    )


@mcp.tool()
async def entity_profile(
    entity_id: str = "",
    entity_name: str = "",
    graph_reference_id: str = "",
    dataset_name: str = "",
) -> str:
    """Get a compact profile for one entity (canonical name, aliases, type, evidence refs)."""
    await _ensure_initialized()
    from Core.Common.Utils import clean_str

    query_value = (entity_id or entity_name or "").strip()
    if not query_value:
        return json.dumps({"error": "entity_id or entity_name is required"}, indent=2)

    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id=graph_reference_id,
        dataset_name=dataset_name,
    )
    if not resolved_graph_id:
        return json.dumps(
            {
                "error": (
                    f"Could not resolve graph_reference_id from graph_reference_id={graph_reference_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
            },
            indent=2,
        )

    ctx = _state["context"]
    graph_instance = ctx.get_graph_instance(resolved_graph_id) if hasattr(ctx, "get_graph_instance") else None
    if not graph_instance or not hasattr(graph_instance, "_graph") or not hasattr(graph_instance._graph, "graph"):
        return json.dumps(
            {"error": f"Graph instance not available for {resolved_graph_id!r}"},
            indent=2,
        )

    nx_graph = graph_instance._graph.graph
    candidate_ids: list[str] = []
    for candidate in (query_value, clean_str(query_value)):
        value = (candidate or "").strip()
        if value and value not in candidate_ids:
            candidate_ids.append(value)

    resolved_entity_id: str | None = None
    for candidate in candidate_ids:
        if candidate in nx_graph:
            resolved_entity_id = candidate
            break

    vdb_candidates: list[dict[str, Any]] = []
    if resolved_entity_id is None and entity_name:
        resolved_vdb = _resolve_vdb_reference_id(
            vdb_reference_id="",
            dataset_name=dataset_name,
            kind="entity",
        )
        if resolved_vdb:
            raw_payload = await entity_vdb_search(
                vdb_reference_id=resolved_vdb,
                query_text=entity_name,
                top_k=5,
                dataset_name=dataset_name,
            )
            try:
                payload = json.loads(raw_payload)
            except Exception:
                payload = {}
            raw_candidates = payload.get("similar_entities") if isinstance(payload, dict) else []
            if isinstance(raw_candidates, list):
                for item in raw_candidates:
                    if not isinstance(item, dict):
                        continue
                    cid = str(item.get("node_id") or item.get("entity_name") or "").strip()
                    if not cid:
                        continue
                    vdb_candidates.append(
                        {
                            "entity_id": cid,
                            "entity_name": item.get("entity_name"),
                            "score": item.get("score"),
                        }
                    )
                    if resolved_entity_id is None and cid in nx_graph:
                        resolved_entity_id = cid

    if resolved_entity_id is None:
        return json.dumps(
            {
                "error": f"Entity {query_value!r} not found in graph {resolved_graph_id!r}",
                "resolved_graph_reference_id": resolved_graph_id,
                "candidate_ids_tried": candidate_ids,
                "vdb_candidates": vdb_candidates,
            },
            indent=2,
            default=str,
        )

    node_attrs = dict(nx_graph.nodes[resolved_entity_id]) if resolved_entity_id in nx_graph else {}
    canonical_name = (
        str(node_attrs.get("entity_name") or "").strip()
        or str(node_attrs.get("name") or "").strip()
        or str(node_attrs.get("title") or "").strip()
        or resolved_entity_id
    )

    aliases: list[str] = []
    seen_aliases: set[str] = set()
    for key in ("aliases", "alias", "aka", "surface_forms", "names"):
        raw_alias = node_attrs.get(key)
        values: list[str]
        if isinstance(raw_alias, str):
            values = [raw_alias]
        elif isinstance(raw_alias, (list, tuple, set)):
            values = [str(v) for v in raw_alias if v is not None]
        else:
            values = []
        for value in values:
            cleaned = re.sub(r"\s+", " ", value.strip())
            if len(cleaned) < 2:
                continue
            alias_key = cleaned.lower()
            if alias_key in seen_aliases:
                continue
            seen_aliases.add(alias_key)
            aliases.append(cleaned)

    coarse_type = (
        str(node_attrs.get("entity_type") or "").strip()
        or str(node_attrs.get("type") or "").strip()
        or str(node_attrs.get("category") or "").strip()
        or str(node_attrs.get("label") or "").strip()
        or "unknown"
    )

    short_desc = (
        str(node_attrs.get("description") or "").strip()
        or str(node_attrs.get("summary") or "").strip()
        or str(node_attrs.get("text") or "").strip()
        or str(node_attrs.get("content") or "").strip()
    )
    if len(short_desc) > 280:
        short_desc = short_desc[:280].rstrip() + "..."

    evidence_refs: list[str] = [f"entity:{resolved_entity_id}"]
    for key in ("chunk_id", "source_chunk_id", "chunk_ids", "source_chunk_ids"):
        raw_chunks = node_attrs.get(key)
        chunk_values: list[str]
        if isinstance(raw_chunks, str):
            chunk_values = [raw_chunks]
        elif isinstance(raw_chunks, (list, tuple, set)):
            chunk_values = [str(v) for v in raw_chunks if v is not None]
        else:
            chunk_values = []
        for cid in chunk_values:
            cid_norm = cid.strip()
            if not cid_norm.startswith("chunk_"):
                continue
            if cid_norm not in evidence_refs:
                evidence_refs.append(cid_norm)

    # Add connectivity info so the agent can decide whether to traverse
    edge_count = 0
    relationship_types = []
    connected_entities = []
    try:
        neighbors = list(nx_graph.neighbors(resolved_entity_id))
        edge_count = len(neighbors)
        seen_rel_types = set()
        for neighbor in neighbors[:20]:
            edge_data = nx_graph.get_edge_data(resolved_entity_id, neighbor, default={})
            rel_name = str(edge_data.get("relation_name", edge_data.get("label", ""))).strip()
            if rel_name and rel_name not in seen_rel_types:
                seen_rel_types.add(rel_name)
                relationship_types.append(rel_name)
            neighbor_name = str(nx_graph.nodes[neighbor].get("entity_name", neighbor))
            if neighbor_name and not neighbor_name.startswith("passage_"):
                connected_entities.append(neighbor_name)
    except Exception:
        pass

    return json.dumps(
        {
            "entity_id": resolved_entity_id,
            "canonical_name": canonical_name,
            "aliases": aliases[:12],
            "coarse_type": coarse_type,
            "short_description": short_desc,
            "edge_count": edge_count,
            "relationship_types": relationship_types[:10],
            "connected_entities": connected_entities[:10],
            "evidence_refs": evidence_refs,
            "resolved_graph_reference_id": resolved_graph_id,
            "resolved_dataset_name": _dataset_name_from_graph_reference(resolved_graph_id),
            "status_message": f"Entity profile resolved. {edge_count} connections." + (" Use entity_traverse or relationship_search to explore." if edge_count > 0 else " No graph edges — use chunk_retrieve for evidence."),
        },
        indent=2,
        default=str,
    )


@mcp.tool()
async def entity_select_candidate(
    candidate_entities: list[Any] | None = None,
    chunk_ids: list[str] | str | None = None,
    chunk_id: str = "",
    entity_name: str = "",
    atom_id: str = "",
    task_text: str = "",
    operation: str = "",
    expected_coarse_types: list[str] | str | None = None,
    dataset_name: str = "",
    top_k: int = 3,
    min_candidate_score: float = 0.0,
    require_unambiguous: bool = False,
    ambiguity_score_gap: float = 0.08,
) -> str:
    """Select canonical entity IDs from candidate entity sets.

    This tool is used both as a lightweight resolver and as a stricter
    benchmark-time anchor selector. In `require_unambiguous` mode it must fail
    loudly with `status="needs_revision"` when multiple plausible top
    candidates remain too close to select safely.
    """
    await _ensure_initialized()

    pool: list[dict[str, Any]] = []
    name_candidates_from_args: list[str] = []
    explicit_candidate_input = False
    if isinstance(candidate_entities, list):
        for item in candidate_entities:
            if isinstance(item, dict):
                pool.append(dict(item))
            elif isinstance(item, str):
                name = item.strip()
                if name:
                    name_candidates_from_args.append(name)
        explicit_candidate_input = bool(pool or name_candidates_from_args)

    normalized_chunk_ids = _normalize_string_list(chunk_ids)
    if (chunk_id or "").strip():
        normalized_chunk_ids.append((chunk_id or "").strip())

    if not pool and normalized_chunk_ids:
        for cid in normalized_chunk_ids:
            for item in _latest_entity_candidates_by_chunk.get(cid, []):
                pool.append(dict(item))

    if not pool and _latest_entity_candidates_flat:
        pool = [dict(item) for item in _latest_entity_candidates_flat]

    if not pool:
        return json.dumps(
            {
                "selected_entities": [],
                "status_message": "No candidate entities available. Run chunk_text_search/chunk_vdb_search first.",
            },
            indent=2,
        )

    name_filter = (entity_name or "").strip().lower()
    if name_filter:
        filtered: list[dict[str, Any]] = []
        for item in pool:
            candidate_name = str(item.get("entity_name") or item.get("resolved_entity_name") or "").lower()
            candidate_id = str(item.get("entity_id") or item.get("resolved_entity_id") or "").lower()
            if name_filter in candidate_name or name_filter in candidate_id:
                filtered.append(item)
        if filtered:
            pool = filtered

    by_entity: dict[str, dict[str, Any]] = {}
    unresolved_names: list[str] = list(name_candidates_from_args)
    atom_context_text = ""
    atom_id_norm = (atom_id or "").strip()
    if atom_id_norm:
        atom = _semantic_plan_atom_by_id(atom_id_norm)
        if atom is not None:
            atom_context_text = " ".join(
                part.strip()
                for part in (
                    str(atom.get("sub_question") or ""),
                    str(atom.get("done_criteria") or ""),
                )
                if part and part.strip()
            )

    semantic_context = " ".join(
        part.strip()
        for part in (
            str(task_text or ""),
            str(operation or ""),
            atom_context_text,
            str(entity_name or ""),
            str(_current_question or ""),
        )
        if part and part.strip()
    )

    expected_types_norm = {
        _normalize_coarse_type(v)
        for v in _normalize_string_list(expected_coarse_types, split_commas=True)
        if v
    }
    expected_types_source = "args" if expected_types_norm else ""
    if not expected_types_norm:
        inferred_types = _infer_expected_coarse_types(semantic_context)
        if inferred_types:
            expected_types_norm = {t for t in inferred_types if t}
            expected_types_source = "inferred"
    else:
        # Reconcile explicit type hints with question-level semantic intent.
        # If caller hints conflict with a clear inferred expectation, prefer the
        # inferred set to avoid committing to obviously wrong pivot types.
        inferred_from_question = {
            t for t in _infer_expected_coarse_types(semantic_context) if t
        }
        if inferred_from_question:
            overlap = expected_types_norm.intersection(inferred_from_question)
            if overlap:
                expected_types_norm = overlap
                expected_types_source = "args+question_overlap"
            elif len(inferred_from_question) == 1:
                expected_types_norm = set(inferred_from_question)
                expected_types_source = "question_override"
    for item in pool:
        entity_id = str(
            item.get("entity_id")
            or item.get("resolved_entity_id")
            or item.get("node_id")
            or ""
        ).strip()
        candidate_name = str(item.get("entity_name") or item.get("resolved_entity_name") or "").strip()
        score_raw = item.get("candidate_score", item.get("score", 0.0))
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.0

        if entity_id:
            existing = by_entity.get(entity_id)
            normalized = {
                "entity_id": entity_id,
                "entity_name": candidate_name or entity_id,
                "coarse_type": str(item.get("coarse_type") or "unknown"),
                "candidate_score": score,
                "chunk_id": item.get("chunk_id"),
                "evidence_ref": item.get("evidence_ref") or item.get("chunk_id") or f"entity:{entity_id}",
                "source": item.get("source", "candidate_set"),
            }
            if existing is None or float(normalized.get("candidate_score") or 0.0) > float(existing.get("candidate_score") or 0.0):
                by_entity[entity_id] = normalized
            continue

        if candidate_name:
            unresolved_names.append(candidate_name)

    strict_type_filter_requested = bool(expected_coarse_types and expected_types_norm)

    # Optional name->ID conversion fallback when candidates are name-only.
    # Avoid opportunistic snippet-mention expansion when caller provided an explicit
    # candidate list plus strict expected types; prefer clear needs_revision instead.
    if not unresolved_names and not explicit_candidate_input:
        snippet_mentions: list[str] = []
        for item in pool[:8]:
            snippet_mentions.extend(
                _extract_context_entity_mentions(str(item.get("context_snippet") or ""), limit=4)
            )
        unresolved_names.extend(snippet_mentions)

    unresolved_names = _normalize_alternatives_tested(unresolved_names)
    if unresolved_names and not (strict_type_filter_requested and explicit_candidate_input):
        resolved_raw = await entity_resolve_names_to_ids(
            entity_names=unresolved_names,
            dataset_name=dataset_name,
            top_k_per_name=3,
            similarity_threshold=0.0,
        )
        try:
            resolved_payload = json.loads(resolved_raw)
        except Exception:
            resolved_payload = {}
        resolved_entities = resolved_payload.get("resolved_entities") if isinstance(resolved_payload, dict) else []
        if isinstance(resolved_entities, list):
            for item in resolved_entities:
                if not isinstance(item, dict):
                    continue
                entity_id = str(item.get("resolved_entity_id") or "").strip()
                if not entity_id:
                    continue
                score_raw = item.get("score", 0.5)
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    score = 0.5
                normalized = {
                    "entity_id": entity_id,
                    "entity_name": str(item.get("resolved_entity_name") or entity_id),
                    "coarse_type": _lookup_entity_coarse_type(
                        entity_id=entity_id,
                        dataset_name=dataset_name,
                    ),
                    "candidate_score": score,
                    "chunk_id": None,
                    "evidence_ref": f"entity:{entity_id}",
                    "source": "entity_resolve_names_to_ids",
                }
                existing = by_entity.get(entity_id)
                if existing is None or score > float(existing.get("candidate_score") or 0.0):
                    by_entity[entity_id] = normalized

    ordered = sorted(
        by_entity.values(),
        key=lambda x: float(x.get("candidate_score") or 0.0),
        reverse=True,
    )
    type_matched = [
        item for item in ordered
        if _coarse_type_matches(str(item.get("coarse_type") or ""), expected_types_norm)
    ]
    strict_type_filter = strict_type_filter_requested
    # When ALL candidates have unknown/empty type, the type filter is uninformative —
    # fall back to the full ordered list with a warning instead of rejecting everything.
    all_unknown = all(
        _normalize_coarse_type(str(item.get("coarse_type") or "")) == "unknown"
        for item in ordered
    ) if ordered else False
    if strict_type_filter and not type_matched and not all_unknown:
        return json.dumps(
            {
                "status": "needs_revision",
                "selected_entities": [],
                "n_selected": 0,
                "n_candidates_considered": len(pool),
                "expected_coarse_types": sorted(expected_types_norm),
                "expected_coarse_types_source": expected_types_source,
                "n_type_matches": 0,
                "type_filter_applied": True,
                "rejected_top_candidates": ordered[: min(5, len(ordered))],
                "recovery_policy": {
                    "new_evidence_required_before_retry": True,
                },
                "suggested_next_actions": [
                    "Run chunk_text_search with an anchored query from the atom sub-question.",
                    "Resolve names to IDs from chunk evidence, then retry entity_select_candidate.",
                ],
                "status_message": (
                    "No candidates matched expected_coarse_types. "
                    "Broaden retrieval and/or provide different candidates."
                ),
            },
            indent=2,
            default=str,
        )
    type_filter_applied = bool(expected_types_norm and type_matched and not all_unknown)
    candidates_for_selection = type_matched if type_filter_applied else ordered
    filtered_generic = [
        item for item in candidates_for_selection
        if str(item.get("entity_name") or item.get("entity_id") or "").strip().lower()
        not in _GENERIC_ENTITY_CANDIDATE_NAMES
    ]
    if filtered_generic:
        candidates_for_selection = filtered_generic
    threshold = float(min_candidate_score or 0.0)
    selected_pool = [
        item for item in candidates_for_selection
        if float(item.get("candidate_score") or 0.0) >= threshold
    ]
    selected = selected_pool[: max(1, int(top_k))]

    if require_unambiguous and len(selected_pool) >= 2:
        top_candidate = selected_pool[0]
        runner_up = selected_pool[1]
        top_score = float(top_candidate.get("candidate_score") or 0.0)
        runner_up_score = float(runner_up.get("candidate_score") or 0.0)
        observed_gap = top_score - runner_up_score
        requested_name = (entity_name or "").strip().lower()
        top_name = str(top_candidate.get("entity_name") or top_candidate.get("entity_id") or "").strip().lower()
        top_id = str(top_candidate.get("entity_id") or "").strip().lower()
        exact_anchor_match = bool(requested_name and requested_name in {top_name, top_id})
        if observed_gap <= float(ambiguity_score_gap) and not exact_anchor_match:
            return json.dumps(
                {
                    "status": "needs_revision",
                    "selected_entities": [],
                    "n_selected": 0,
                    "n_candidates_considered": len(pool),
                    "expected_coarse_types": sorted(expected_types_norm) if expected_types_norm else [],
                    "expected_coarse_types_source": expected_types_source or None,
                    "n_type_matches": len(type_matched),
                    "type_filter_applied": type_filter_applied,
                    "require_unambiguous": True,
                    "ambiguity_score_gap": float(ambiguity_score_gap),
                    "observed_top_score_gap": round(observed_gap, 6),
                    "top_candidates": selected_pool[: min(5, len(selected_pool))],
                    "recovery_policy": {
                        "new_evidence_required_before_retry": True,
                    },
                    "suggested_next_actions": [
                        "Ground the anchor in chunk evidence before selecting a canonical entity.",
                        "Use entity_profile on the plausible candidates and compare them against the atom.",
                        "If the bridge remains ambiguous, test the candidates against the downstream clue or use bridge_disambiguate.",
                    ],
                    "status_message": (
                        "Multiple plausible anchor candidates remain too close to select safely."
                    ),
                },
                indent=2,
                default=str,
            )

    return json.dumps(
        {
            "status": "ok",
            "selected_entities": selected,
            "n_selected": len(selected),
            "n_candidates_considered": len(pool),
            "expected_coarse_types": sorted(expected_types_norm) if expected_types_norm else [],
            "expected_coarse_types_source": expected_types_source or None,
            "n_type_matches": len(type_matched),
            "type_filter_applied": type_filter_applied,
            "status_message": f"Selected {len(selected)} canonical entity IDs from candidate set",
        },
        indent=2,
        default=str,
    )


@mcp.tool()
async def entity_tfidf(candidate_entity_ids: list[str] | str | None = None, query_text: str = "",
                       graph_reference_id: str = "", top_k: int = 10) -> str:
    """Rank candidate entities by TF-IDF similarity to a query.

    Args:
        candidate_entity_ids: Entity IDs to rank
        query_text: Query to compare against
        graph_reference_id: Graph containing the entities
        top_k: Number of top results

    Returns:
        ranked_entities: list of [entity_id: str, score: float]
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_tools import entity_tfidf_tool
    from Core.AgentSchema.tool_contracts import EntityTFIDFInputs
    normalized_candidates = _normalize_string_list(candidate_entity_ids)
    if not normalized_candidates and _latest_entity_candidates_flat:
        seen: set[str] = set()
        for item in _latest_entity_candidates_flat:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("entity_id") or item.get("resolved_entity_id") or "").strip()
            if not entity_id:
                continue
            key = entity_id.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_candidates.append(entity_id)

    if not normalized_candidates:
        return json.dumps(
            {"error": "candidate_entity_ids is required (or run candidate-producing retrieval first)"},
            indent=2,
        )

    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id=graph_reference_id,
        dataset_name="",
    )
    if not resolved_graph_id:
        return json.dumps(
            {"error": f"Could not resolve graph_reference_id from {graph_reference_id!r}"},
            indent=2,
        )

    inputs = EntityTFIDFInputs(
        candidate_entity_ids=normalized_candidates,
        query_text=query_text,
        graph_reference_id=resolved_graph_id,
        top_k=top_k,
    )
    result = await entity_tfidf_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# RELATIONSHIP TOOLS
# =============================================================================

@mcp.tool()
async def relationship_onehop(entity_ids: list[str] | str | None, graph_reference_id: str) -> str:
    """Get one-hop relationships for given entities.

    Args:
        entity_ids: Entity IDs to find relationships for
        graph_reference_id: ID of the graph

    Returns:
        one_hop_relationships: list of {relationship_id: str, source_node_id: str, target_node_id: str, type: str, description?: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.relationship_tools import relationship_one_hop_neighbors_tool
    from Core.AgentSchema.tool_contracts import RelationshipOneHopNeighborsInputs
    normalized_entity_ids = _normalize_string_list(entity_ids)
    if not normalized_entity_ids:
        return json.dumps({"error": "entity_ids is required"}, indent=2)

    inputs = RelationshipOneHopNeighborsInputs(
        entity_ids=normalized_entity_ids,
        graph_reference_id=graph_reference_id,
    )
    result = await relationship_one_hop_neighbors_tool(inputs, _state["context"])
    if BENCHMARK_MODE:
        if os.environ.get("DIGIMON_CONSOLIDATED_TOOLS", "").strip().lower() in {"1", "true", "yes"}:
            return _format_result(result)
        return _format_relationship_onehop(result)
    return _format_result(result)


@mcp.tool()
async def relationship_score_aggregator(
    graph_reference_id: str,
    entity_scores: dict | None = None,
    top_k: int = 10, aggregation_method: str = "sum"
) -> str:
    """Aggregate entity scores (e.g. from PPR) onto relationships and return top-k.

    Args:
        graph_reference_id: ID of the graph
        entity_scores: Optional dict mapping entity_id to score (defaults to empty dict)
        top_k: Number of top relationships to return
        aggregation_method: How to combine scores: 'sum', 'average', or 'max'

    Returns:
        scored_relationships: list of [{relationship_id: str, source_node_id: str, target_node_id: str, type: str}, score: float]
    """
    await _ensure_initialized()
    from Core.AgentTools.relationship_tools import relationship_score_aggregator_tool
    from Core.AgentSchema.tool_contracts import RelationshipScoreAggregatorInputs

    inputs = RelationshipScoreAggregatorInputs(
        entity_scores=entity_scores or {},
        graph_reference_id=graph_reference_id,
        top_k_relationships=top_k,
        aggregation_method=aggregation_method,
    )
    result = await relationship_score_aggregator_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def relationship_agent(query_text: str, text_context: str,
                              context_entity_names: list[str] = None,
                              target_relationship_types: list[str] = None,
                              max_relationships: int = 10) -> str:
    """Use LLM to extract relationships from text context.

    Args:
        query_text: Query to guide extraction
        text_context: Text to extract relationships from
        context_entity_names: Known entity names for context
        target_relationship_types: Relationship types to focus on
        max_relationships: Maximum relationships to extract

    Returns:
        extracted_relationships: list of {relationship_id: str, source_node_id: str, target_node_id: str, type: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.relationship_tools import relationship_agent_tool
    from Core.AgentSchema.tool_contracts import RelationshipAgentInputs, ExtractedEntityData

    # Build context_entities from names
    context_entities = []
    if context_entity_names:
        for name in context_entity_names:
            context_entities.append(ExtractedEntityData(
                entity_name=name, source_id="mcp_input", entity_type="unknown"
            ))

    inputs = RelationshipAgentInputs(
        query_text=query_text,
        text_context=text_context,
        context_entities=context_entities,
        target_relationship_types=target_relationship_types,
        max_relationships_to_extract=max_relationships,
    )
    result = await relationship_agent_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# CHUNK TOOLS
# =============================================================================

@mcp.tool()
async def chunk_from_relationships(target_relationships: list[str],
                                    document_collection_id: str = "",
                                    dataset_name: str = "",
                                    top_k: int = 10) -> str:
    """Retrieve text chunks associated with specified relationships.

    Args:
        target_relationships: List of relationship identifiers (e.g. 'entity1->entity2')
        document_collection_id: Graph/collection ID to search
        top_k: Maximum chunks to return

    Returns:
        relevant_chunks: list of {chunk_id: str, content: str, relevance_score?: float}
    """
    await _ensure_initialized()
    from Core.AgentTools.chunk_tools import chunk_from_relationships_tool

    resolved_collection_id = _resolve_graph_reference_id(
        graph_reference_id=document_collection_id,
        dataset_name=dataset_name,
    )
    if not resolved_collection_id:
        return json.dumps(
            {
                "error": (
                    f"Could not resolve document_collection_id from document_collection_id={document_collection_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
            },
            indent=2,
        )

    input_data = {
        "target_relationships": target_relationships,
        "document_collection_id": resolved_collection_id,
        "top_k_total": top_k,
    }
    result = await chunk_from_relationships_tool(input_data, _state["context"])
    formatted = _format_result(result)
    try:
        payload = json.loads(formatted)
        if isinstance(payload, dict):
            payload["resolved_document_collection_id"] = resolved_collection_id
            return json.dumps(payload, indent=2, default=str)
    except Exception:
        pass
    return formatted


@mcp.tool()
async def chunk_occurrence(
    target_entity_pairs: list[dict] | None = None,
    document_collection_id: str = "",
    top_k: int = 5,
    entity_names: list[str] | None = None,
    dataset_name: str = "",
) -> str:
    """Rank chunks by entity pair co-occurrence.

    Args:
        target_entity_pairs: List of dicts like {"entity1_id": "X", "entity2_id": "Y"}
        document_collection_id: Graph ID to search
        top_k: Number of top chunks to return

    Returns:
        ranked_occurrence_chunks: list of {chunk_id: str, content: str, relevance_score?: float}
    """
    await _ensure_initialized()
    from Core.AgentTools.chunk_tools import chunk_occurrence_tool
    from Core.AgentSchema.tool_contracts import ChunkOccurrenceInputs

    normalized_pairs = list(target_entity_pairs or [])
    if not normalized_pairs and entity_names and len(entity_names) >= 2:
        normalized_pairs = [
            {"entity1_id": entity_names[0], "entity2_id": entity_names[1]},
        ]
    if not normalized_pairs:
        return json.dumps(
            {"error": "target_entity_pairs (or at least 2 entity_names) is required"},
            indent=2,
        )

    resolved_collection_id = _resolve_graph_reference_id(
        graph_reference_id=document_collection_id,
        dataset_name=dataset_name,
    )
    if not resolved_collection_id:
        return json.dumps(
            {
                "error": (
                    f"Could not resolve document_collection_id from document_collection_id={document_collection_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
            },
            indent=2,
        )

    inputs = ChunkOccurrenceInputs(
        target_entity_pairs_in_relationship=normalized_pairs,
        document_collection_id=resolved_collection_id,
        top_k_chunks=top_k,
    )
    result = await chunk_occurrence_tool(inputs, _state["context"])
    formatted = _format_result(result)
    try:
        payload = json.loads(formatted)
        if isinstance(payload, dict):
            payload["resolved_document_collection_id"] = resolved_collection_id
            return json.dumps(payload, indent=2, default=str)
    except Exception:
        pass
    return formatted


@mcp.tool()
async def chunk_get_text(
    graph_reference_id: str = "",
    entity_ids: list[str] | str | None = None,
    chunk_ids: list[str] | str | None = None,
    chunk_id: str = "",
    max_chunks_per_entity: int = 5,
    entity_names: list[str] | str | None = None,
    dataset_name: str = "",
    mode: str = _CHUNK_GET_TEXT_MODE_AUTO,
) -> str:
    """Get source text chunks associated with entities or explicit chunk IDs.

    Args:
        graph_reference_id: ID of the graph containing the entities
        entity_ids: List of entity names/IDs to get text for
        chunk_ids: Optional list of explicit chunk IDs to fetch (alias path)
        chunk_id: Optional single explicit chunk ID (alias for chunk_ids=[...])
        max_chunks_per_entity: Max chunks per entity
        mode: One of "entity_ids", "chunk_ids", or "auto". In auto mode,
            exactly one mode must be inferable from provided args.

    Returns:
        retrieved_chunks: list of {entity_id?: str, chunk_id: str, text_content: str}, status_message: str
    """
    await _ensure_initialized()
    from Core.AgentTools.chunk_tools import chunk_get_text_for_entities_tool
    from Core.AgentSchema.tool_contracts import ChunkGetTextForEntitiesInput

    normalized_mode = (mode or _CHUNK_GET_TEXT_MODE_AUTO).strip().lower()
    if normalized_mode not in _CHUNK_GET_TEXT_VALID_MODES:
        return json.dumps(
            {
                "error": (
                    "mode must be one of "
                    f"{sorted(_CHUNK_GET_TEXT_VALID_MODES)}"
                )
            },
            indent=2,
        )

    # Robust alias handling for explicit chunk-ID retrieval attempts.
    normalized_chunk_ids = _normalize_string_list(chunk_ids)
    single_chunk_id = (chunk_id or "").strip()
    if single_chunk_id:
        normalized_chunk_ids.append(single_chunk_id)
    seen_ids: set[str] = set()
    ordered_chunk_ids: list[str] = []
    for cid in normalized_chunk_ids:
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        ordered_chunk_ids.append(cid)

    normalized_entity_ids = _normalize_string_list(entity_ids)
    if not normalized_entity_ids and entity_names:
        normalized_entity_ids = _normalize_string_list(entity_names)

    has_chunk_refs = bool(ordered_chunk_ids)
    has_entity_refs = bool(normalized_entity_ids)

    resolved_mode = normalized_mode
    if normalized_mode == _CHUNK_GET_TEXT_MODE_AUTO:
        if has_chunk_refs and has_entity_refs:
            return json.dumps(
                {
                    "error": (
                        "chunk_get_text auto mode is ambiguous: provide only one of "
                        "(chunk_id/chunk_ids) or (entity_ids/entity_names), or pass "
                        "mode='chunk_ids' or mode='entity_ids' explicitly."
                    ),
                },
                indent=2,
            )
        if has_chunk_refs:
            resolved_mode = _CHUNK_GET_TEXT_MODE_BY_CHUNK_IDS
        elif has_entity_refs:
            resolved_mode = _CHUNK_GET_TEXT_MODE_BY_ENTITY_IDS
        else:
            return json.dumps(
                {
                    "error": (
                        "chunk_get_text requires either chunk references or entity references "
                        "when mode='auto'."
                    )
                },
                indent=2,
            )

    if resolved_mode == _CHUNK_GET_TEXT_MODE_BY_CHUNK_IDS:
        if has_entity_refs:
            return json.dumps(
                {
                    "error": "entity_ids/entity_names are not allowed when mode='chunk_ids'",
                },
                indent=2,
            )
        if not has_chunk_refs:
            return json.dumps(
                {
                    "error": "chunk_id or chunk_ids is required when mode='chunk_ids'",
                },
                indent=2,
            )

        seen_ids: set[str] = set()
        ordered_chunk_ids = []
        for cid in normalized_chunk_ids:
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            ordered_chunk_ids.append(cid)

        resolved_dataset_name = _resolve_dataset_name(dataset_name) if dataset_name else ""
        # Auto-resolve from preloaded dataset if not provided
        if not resolved_dataset_name:
            preloaded = os.environ.get("DIGIMON_PRELOAD_DATASET", "")
            if preloaded:
                resolved_dataset_name = preloaded
        retrieved_chunks: list[dict[str, Any]] = []
        missing_chunk_ids: list[str] = []

        # Fast path: already seen in this session.
        for cid in ordered_chunk_ids:
            cached_text = _seen_chunk_text.get(cid)
            if cached_text:
                _is_new, text_out = _dedup_chunk(cid, cached_text)
                retrieved_chunks.append({"chunk_id": cid, "text_content": text_out})
            else:
                missing_chunk_ids.append(cid)

        # Slow path: load from chunk storage if dataset_name is available.
        if missing_chunk_ids and resolved_dataset_name:
            chunk_factory = _state.get("chunk_factory")
            if chunk_factory is not None:
                try:
                    chunks_list = await chunk_factory.get_chunks_for_dataset(resolved_dataset_name)
                    chunk_map: dict[str, str] = {}
                    for item in chunks_list or []:
                        if not isinstance(item, tuple) or len(item) < 2:
                            continue
                        cid, chunk_obj = item[0], item[1]
                        if not isinstance(cid, str):
                            continue
                        if hasattr(chunk_obj, "content"):
                            content = chunk_obj.content
                        elif hasattr(chunk_obj, "text"):
                            content = chunk_obj.text
                        else:
                            content = str(chunk_obj)
                        chunk_map[cid] = content or ""

                    unresolved: list[str] = []
                    for cid in missing_chunk_ids:
                        content = chunk_map.get(cid)
                        if content:
                            _is_new, text_out = _dedup_chunk(cid, content)
                            retrieved_chunks.append(
                                {
                                    "chunk_id": cid,
                                    "text_content": text_out,
                                    "evidence_ref": cid,
                                }
                            )
                        else:
                            unresolved.append(cid)
                    missing_chunk_ids = unresolved
                except Exception as e:
                    logger.warning(
                        "chunk_get_text chunk-id lookup failed for dataset '%s': %s",
                        resolved_dataset_name,
                        e,
                    )

        return json.dumps(
            {
                "retrieved_chunks": retrieved_chunks,
                "evidence_refs": [
                    str(item.get("evidence_ref") or "")
                    for item in retrieved_chunks
                    if isinstance(item, dict) and str(item.get("evidence_ref") or "").strip()
                ],
                "missing_chunk_ids": missing_chunk_ids,
                "resolved_mode": resolved_mode,
                "resolved_dataset_name": resolved_dataset_name or None,
                "status_message": (
                    f"Retrieved {len(retrieved_chunks)} chunks by chunk-id lookup"
                    + (f"; {len(missing_chunk_ids)} missing" if missing_chunk_ids else "")
                ),
            },
            indent=2,
            default=str,
        )

    if resolved_mode == _CHUNK_GET_TEXT_MODE_BY_ENTITY_IDS and has_chunk_refs:
        return json.dumps(
            {
                "error": "chunk_id/chunk_ids are not allowed when mode='entity_ids'",
            },
            indent=2,
        )
    if not normalized_entity_ids:
        return json.dumps({"error": "entity_ids (or entity_names) is required when mode='entity_ids'"}, indent=2)

    resolved_graph_id = _resolve_graph_reference_id(
        graph_reference_id=graph_reference_id,
        dataset_name=dataset_name,
    )
    if not resolved_graph_id:
        return json.dumps(
            {
                "error": (
                    f"Could not resolve graph_reference_id from graph_reference_id={graph_reference_id!r} "
                    f"dataset_name={dataset_name!r}"
                ),
            },
            indent=2,
        )

    inputs = ChunkGetTextForEntitiesInput(
        graph_reference_id=resolved_graph_id,
        entity_ids=normalized_entity_ids,
        max_chunks_per_entity=max_chunks_per_entity,
    )
    result = await chunk_get_text_for_entities_tool(inputs, _state["context"])

    # Dedup chunks — replace repeated text with reference
    if hasattr(result, "retrieved_chunks"):
        deduped = []
        for chunk in result.retrieved_chunks:
            chunk_id = getattr(chunk, "chunk_id", None)
            text = getattr(chunk, "text_content", "") or ""
            if chunk_id and text:
                is_new, text = _dedup_chunk(chunk_id, text)
                d = chunk.model_dump(exclude_none=True) if hasattr(chunk, "model_dump") else {}
                d["text_content"] = text
                d["evidence_ref"] = chunk_id
                deduped.append(d)
            else:
                deduped.append(chunk.model_dump(exclude_none=True) if hasattr(chunk, "model_dump") else {})
        return json.dumps({
            "retrieved_chunks": deduped,
            "evidence_refs": [
                str(item.get("evidence_ref") or "")
                for item in deduped
                if isinstance(item, dict) and str(item.get("evidence_ref") or "").strip()
            ],
            "resolved_mode": resolved_mode,
            "resolved_graph_reference_id": resolved_graph_id,
            "status_message": f"Retrieved {len(deduped)} chunks for {len(normalized_entity_ids)} entities",
        }, indent=2, default=str)

    return _format_result(result)


@mcp.tool()
async def chunk_get_text_by_chunk_ids(
    chunk_ids: list[str] | str | None = None,
    chunk_id: str = "",
    dataset_name: str = "",
) -> str:
    """Get chunk text by explicit chunk IDs only."""
    return await chunk_get_text(
        chunk_ids=chunk_ids,
        chunk_id=chunk_id,
        dataset_name=dataset_name,
        mode=_CHUNK_GET_TEXT_MODE_BY_CHUNK_IDS,
    )


@mcp.tool()
async def chunk_get_text_by_entity_ids(
    graph_reference_id: str = "",
    entity_ids: list[str] | str | None = None,
    entity_names: list[str] | str | None = None,
    max_chunks_per_entity: int = 5,
    dataset_name: str = "",
) -> str:
    """Get chunk text by canonical entity IDs (or explicit entity-name aliases)."""
    return await chunk_get_text(
        graph_reference_id=graph_reference_id,
        entity_ids=entity_ids,
        max_chunks_per_entity=max_chunks_per_entity,
        entity_names=entity_names,
        dataset_name=dataset_name,
        mode=_CHUNK_GET_TEXT_MODE_BY_ENTITY_IDS,
    )


def _extract_date_mentions_from_sources(
    *,
    sources: list[dict[str, str]],
    max_mentions: int = 20,
) -> str:
    """Shared date-mention extraction over normalized source text blocks."""
    if not sources:
        return json.dumps(
            {
                "error": "Provide text or chunk_id/chunk_ids.",
                "status_message": "No source text available for date extraction.",
            },
            indent=2,
        )

    month_pattern = r"(?:%s)" % "|".join(_MONTH_NAMES)
    full_date_re = re.compile(
        rf"\b(?P<month>{month_pattern})\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+"
        r"(?P<year>\d{3,4})\b",
        flags=re.IGNORECASE,
    )
    month_year_re = re.compile(
        rf"\b(?P<month>{month_pattern})\s+(?P<year>\d{{3,4}})\b",
        flags=re.IGNORECASE,
    )
    year_re = re.compile(r"\b(?P<year>[89]\d{2}|1\d{3}|20\d{2})\b")

    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()

    def _add_mention(
        *,
        source_chunk_id: str,
        source_text: str,
        start: int,
        end: int,
        mention_text: str,
        normalized_date: str,
        precision: str,
    ) -> None:
        key = (source_chunk_id, start, end, normalized_date)
        if key in seen:
            return
        seen.add(key)
        evidence_ref = source_chunk_id if source_chunk_id else "inline_text"
        mentions.append(
            {
                "mention_text": mention_text,
                "normalized_date": normalized_date,
                "precision": precision,
                "chunk_id": source_chunk_id or None,
                "char_start": start,
                "char_end": end,
                "evidence_ref": evidence_ref,
                "context_snippet": source_text[max(0, start - 40): min(len(source_text), end + 40)],
            }
        )

    for source in sources:
        source_chunk_id = source.get("chunk_id", "")
        source_text = source.get("text", "")
        if not source_text:
            continue

        occupied_spans: list[tuple[int, int]] = []

        for match in full_date_re.finditer(source_text):
            month = match.group("month").capitalize()
            day = int(match.group("day"))
            year = match.group("year")
            normalized_date = f"{month} {day}, {year}"
            start, end = match.span()
            occupied_spans.append((start, end))
            _add_mention(
                source_chunk_id=source_chunk_id,
                source_text=source_text,
                start=start,
                end=end,
                mention_text=match.group(0),
                normalized_date=normalized_date,
                precision="day",
            )

        for match in month_year_re.finditer(source_text):
            start, end = match.span()
            if any(start >= a and end <= b for a, b in occupied_spans):
                continue
            month = match.group("month").capitalize()
            year = match.group("year")
            normalized_date = f"{month} {year}"
            occupied_spans.append((start, end))
            _add_mention(
                source_chunk_id=source_chunk_id,
                source_text=source_text,
                start=start,
                end=end,
                mention_text=match.group(0),
                normalized_date=normalized_date,
                precision="month",
            )

        for match in year_re.finditer(source_text):
            start, end = match.span()
            if any(start >= a and end <= b for a, b in occupied_spans):
                continue
            year = match.group("year")
            _add_mention(
                source_chunk_id=source_chunk_id,
                source_text=source_text,
                start=start,
                end=end,
                mention_text=match.group(0),
                normalized_date=year,
                precision="year",
            )

    mentions.sort(key=lambda item: (item.get("chunk_id") or "", int(item.get("char_start") or 0)))
    limited_mentions = mentions[: max(1, int(max_mentions))]

    return json.dumps(
        {
            "date_mentions": limited_mentions,
            "evidence_refs": [
                str(item.get("evidence_ref") or "")
                for item in limited_mentions
                if isinstance(item, dict) and str(item.get("evidence_ref") or "").strip()
            ],
            "n_date_mentions": len(limited_mentions),
            "n_sources": len(sources),
            "status_message": (
                f"Extracted {len(limited_mentions)} date mentions from {len(sources)} source blocks"
            ),
        },
        indent=2,
        default=str,
    )


@mcp.tool()
async def extract_date_mentions(
    chunk_ids: list[str] | None = None,
    chunk_id: str = "",
    text: str = "",
    dataset_name: str = "",
    max_mentions: int = 20,
) -> str:
    """Extract normalized date mentions from chunk text with evidence refs."""
    await _ensure_initialized()

    sources: list[dict[str, str]] = []
    if (text or "").strip():
        sources.append({"chunk_id": "", "text": text.strip()})

    if chunk_ids or (chunk_id or "").strip():
        payload_raw = await chunk_get_text_by_chunk_ids(
            chunk_ids=chunk_ids,
            chunk_id=chunk_id,
            dataset_name=dataset_name,
        )
        try:
            payload = json.loads(payload_raw)
        except Exception:
            payload = {}
        retrieved_chunks = payload.get("retrieved_chunks") if isinstance(payload, dict) else []
        if isinstance(retrieved_chunks, list):
            for item in retrieved_chunks:
                if not isinstance(item, dict):
                    continue
                cid = str(item.get("chunk_id") or "").strip()
                chunk_text = str(
                    item.get("text_content")
                    or item.get("text")
                    or item.get("content")
                    or ""
                )
                if chunk_text:
                    sources.append({"chunk_id": cid, "text": chunk_text})

    return _extract_date_mentions_from_sources(
        sources=sources,
        max_mentions=max_mentions,
    )


@mcp.tool()
async def chunk_text_search(query_text: str, dataset_name: str,
                             top_k: int = 5,
                             entity_names: list[str] | str | None = None,
                             max_candidates_per_chunk: int = 4,
                             max_text_chars: int = 1200) -> str:
    """Keyword/TF-IDF search over raw chunk text. Bypasses entity-based retrieval.

    Use when entity VDB search misses relevant passages, or as a complementary
    signal. Searches the actual document text directly using TF-IDF cosine similarity.

    Args:
        query_text: Search query (keywords or natural language)
        dataset_name: Dataset whose chunks to search
        top_k: Number of top chunks to return
        entity_names: Optional entity names to pre-filter chunks (search only chunks associated with these entities)

    Returns:
        chunks: list of {chunk_id: str, text: str, score: float}
        entity_candidates: optional candidate entities linked to returned chunks
    """
    await _ensure_initialized()
    from Core.Operators.chunk.text_search import chunk_text_search as _text_search
    from Core.Schema.SlotTypes import EntityRecord, SlotKind, SlotValue

    resolved_dataset_name = _resolve_dataset_name(dataset_name)
    query_text_norm, query_contract = _build_retrieval_query_contract(
        query_text,
        tool_name="chunk_text_search",
    )
    normalized_entities = _normalize_string_list(entity_names)
    if not query_text_norm and normalized_entities:
        query_text_norm = " ".join(normalized_entities)
    elif normalized_entities:
        missing = [name for name in normalized_entities if name.lower() not in query_text_norm.lower()]
        if missing:
            query_text_norm = (query_text_norm + " " + " ".join(missing)).strip()
    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text_norm, producer="mcp")}

    # Optionally add entity filter
    if entity_names:
        # Look up entity source_ids from the graph
        ctx = _state["context"]
        entity_records = []
        graph_id = None
        if hasattr(ctx, "list_graphs"):
            for gid in ctx.list_graphs():
                if resolved_dataset_name in gid:
                    graph_id = gid
                    break
        if graph_id:
            gi = ctx.get_graph_instance(graph_id)
            if gi and hasattr(gi, "_graph") and hasattr(gi._graph, "graph"):
                nx_graph = gi._graph.graph
                for name in normalized_entities:
                    if name in nx_graph:
                        node_data = nx_graph.nodes[name]
                        entity_records.append(EntityRecord(
                            entity_name=name,
                            source_id=node_data.get("source_id", ""),
                        ))
        if entity_records:
            inputs["entities"] = SlotValue(
                kind=SlotKind.ENTITY_SET, data=entity_records, producer="mcp",
            )

    op_ctx = await _build_operator_context_for_dataset(resolved_dataset_name)
    result = await _text_search(inputs=inputs, ctx=op_ctx, params={"top_k": top_k})

    chunks = result.get("chunks")
    if chunks and hasattr(chunks, "data"):
        deduped = []
        for c in chunks.data:
            full_text = c.text or ""
            _is_new, dedup_text = _dedup_chunk(c.chunk_id, full_text)
            compact_text, was_truncated = _compact_chunk_text_for_prompt(
                dedup_text,
                max_chars=max_text_chars,
            )
            deduped.append(
                {
                    "chunk_id": c.chunk_id,
                    "evidence_ref": c.chunk_id,
                    "text": compact_text,
                    "score": c.score,
                    "text_truncated": bool(was_truncated),
                }
            )
        enriched = _enrich_chunks_with_entity_candidates(
            dataset_name=resolved_dataset_name,
            query_text=query_text_norm,
            chunks=deduped,
            max_candidates_per_chunk=max_candidates_per_chunk,
            max_total_candidates=24,
        )
        compact_candidates_by_chunk = {
            chunk_id: [
                str(item.get("entity_id") or "")
                for item in items
                if isinstance(item, dict) and str(item.get("entity_id") or "").strip()
            ]
            for chunk_id, items in (enriched.get("entity_candidates_by_chunk") or {}).items()
            if isinstance(items, list)
        }
        # Compact entity candidates: only name, type, score (agent can call entity_profile for details)
        compact_candidates = [
            {"entity_id": c.get("entity_id", ""), "type": c.get("coarse_type", ""), "score": c.get("candidate_score", 0)}
            for c in enriched.get("entity_candidates", [])
        ]
        return json.dumps({
            "resolved_dataset_name": resolved_dataset_name,
            "chunks": [entry for entry in deduped],
            "evidence_refs": [
                str(entry.get("evidence_ref") or "")
                for entry in deduped
                if isinstance(entry, dict) and str(entry.get("evidence_ref") or "").strip()
            ],
            "resolved_graph_reference_id": enriched.get("resolved_graph_reference_id"),
            "entity_candidates": compact_candidates,
            "query_contract": query_contract,
        }, indent=2, default=str)
    return json.dumps(
        {
            "resolved_dataset_name": resolved_dataset_name,
            "chunks": [],
            "entity_candidates": [],
            "entity_candidates_by_chunk": {},
            "candidate_summary": {"n_chunks_with_candidates": 0, "n_candidates": 0},
            "query_contract": query_contract,
        },
        indent=2,
        default=str,
    )


async def chunk_vdb_build(dataset_name: str, vdb_collection_name: str = "",
                           force_rebuild: bool = False) -> str:
    """Build a vector database (embedding index) over document chunks.

    Enables semantic chunk retrieval via chunk_vdb_search. Complements the keyword-based
    chunk_text_search (TF-IDF) — together they form dual retrieval (EcphoryRAG pattern).

    Args:
        dataset_name: Dataset whose chunks to index
        vdb_collection_name: VDB ID (default: '{dataset_name}_chunks')
        force_rebuild: Force rebuild even if VDB exists

    Returns:
        vdb_id: str, num_chunks_indexed: int, status: str
    """
    await _ensure_initialized()
    _ensure_embedding_provider_initialized(reason="chunk_vdb_build")
    from Core.AgentTools.chunk_vdb_tools import chunk_vdb_build_tool

    resolved_dataset_name = _resolve_dataset_name(dataset_name)
    result = await chunk_vdb_build_tool(
        dataset_name=resolved_dataset_name,
        graphrag_context=_state["context"],
        vdb_collection_name=vdb_collection_name or None,
        force_rebuild=force_rebuild,
    )
    return json.dumps(result, indent=2, default=str)

if not BENCHMARK_MODE:
    chunk_vdb_build = mcp.tool()(chunk_vdb_build)


@mcp.tool()
async def chunk_vdb_search(query_text: str, dataset_name: str,
                            top_k: int = 10,
                            entity_names: list[str] | str | None = None,
                            max_candidates_per_chunk: int = 4,
                            max_text_chars: int = 1200) -> str:
    """Semantic embedding search over document chunks. Finds passages similar in meaning to the query.

    Use alongside chunk_text_search for dual retrieval — embedding search catches
    semantic matches that keyword search misses, and vice versa.

    Args:
        query_text: Natural language search query
        dataset_name: Dataset whose chunk VDB to search
        top_k: Number of top chunks to return

    Returns:
        chunks: list of {chunk_id: str, text: str, score: float}
        entity_candidates: optional candidate entities linked to returned chunks
    """
    await _ensure_initialized()
    from Core.Operators.chunk.vdb import chunk_vdb as _chunk_vdb_op
    from Core.Schema.SlotTypes import SlotKind, SlotValue

    resolved_dataset_name = _resolve_dataset_name(dataset_name)
    query_text_norm, query_contract = _build_retrieval_query_contract(
        query_text,
        tool_name="chunk_vdb_search",
    )
    normalized_entities = _normalize_string_list(entity_names)
    if not query_text_norm and normalized_entities:
        query_text_norm = " ".join(normalized_entities)
    elif normalized_entities:
        missing = [name for name in normalized_entities if name.lower() not in query_text_norm.lower()]
        if missing:
            query_text_norm = (query_text_norm + " " + " ".join(missing)).strip()
    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text_norm, producer="mcp")}
    op_ctx = await _build_operator_context_for_dataset(resolved_dataset_name)

    if op_ctx.chunks_vdb is None:
        return json.dumps({"error": "Chunk VDB not built. Run chunk_vdb_build first.", "chunks": []})

    result = await _chunk_vdb_op(inputs=inputs, ctx=op_ctx, params={"top_k": top_k})

    chunks = result.get("chunks")
    if chunks and hasattr(chunks, "data"):
        deduped = []
        for c in chunks.data:
            full_text = c.text or ""
            _is_new, dedup_text = _dedup_chunk(c.chunk_id, full_text)
            compact_text, was_truncated = _compact_chunk_text_for_prompt(
                dedup_text,
                max_chars=max_text_chars,
            )
            deduped.append(
                {
                    "chunk_id": c.chunk_id,
                    "evidence_ref": c.chunk_id,
                    "text": compact_text,
                    "score": c.score,
                    "text_truncated": bool(was_truncated),
                }
            )
        enriched = _enrich_chunks_with_entity_candidates(
            dataset_name=resolved_dataset_name,
            query_text=query_text_norm,
            chunks=deduped,
            max_candidates_per_chunk=max_candidates_per_chunk,
            max_total_candidates=24,
        )
        compact_candidates_by_chunk = {
            chunk_id: [
                str(item.get("entity_id") or "")
                for item in items
                if isinstance(item, dict) and str(item.get("entity_id") or "").strip()
            ]
            for chunk_id, items in (enriched.get("entity_candidates_by_chunk") or {}).items()
            if isinstance(items, list)
        }
        compact_candidates = [
            {"entity_id": c.get("entity_id", ""), "type": c.get("coarse_type", ""), "score": c.get("candidate_score", 0)}
            for c in enriched.get("entity_candidates", [])
        ]
        return json.dumps(
            {
                "resolved_dataset_name": resolved_dataset_name,
                "chunks": deduped,
                "evidence_refs": [
                    str(entry.get("evidence_ref") or "")
                    for entry in deduped
                    if isinstance(entry, dict) and str(entry.get("evidence_ref") or "").strip()
                ],
                "resolved_graph_reference_id": enriched.get("resolved_graph_reference_id"),
                "entity_candidates": compact_candidates,
                "query_contract": query_contract,
            },
            indent=2,
            default=str,
        )
    return json.dumps(
        {
            "resolved_dataset_name": resolved_dataset_name,
            "chunks": [],
            "entity_candidates": [],
            "entity_candidates_by_chunk": {},
            "candidate_summary": {"n_chunks_with_candidates": 0, "n_candidates": 0},
            "query_contract": query_contract,
        },
        indent=2,
        default=str,
    )


@mcp.tool()
async def search_then_expand_onehop(
    query_text: str,
    dataset_name: str,
    graph_reference_id: str = "",
    atom_id: str = "",
    task_text: str = "",
    operation: str = "",
    expected_coarse_types: list[str] | str | None = None,
    top_k_chunks: int = 6,
    max_candidates_per_chunk: int = 4,
    max_entities: int = 5,
    neighbor_limit_per_entity: int = 20,
    require_unambiguous: bool = False,
    ambiguity_score_gap: float = 0.08,
) -> str:
    """Composite search->candidate selection->entity one-hop expansion.

    This helper is useful for descriptive anchors that do not have a clean
    surface-form lookup. It can optionally require ambiguity-safe candidate
    selection before traversing the graph.
    """
    await _ensure_initialized()

    step_summaries: list[dict[str, Any]] = []

    chunk_raw = await chunk_text_search(
        query_text=query_text,
        dataset_name=dataset_name,
        top_k=max(1, int(top_k_chunks)),
        max_candidates_per_chunk=max(1, int(max_candidates_per_chunk)),
    )
    try:
        chunk_payload = json.loads(chunk_raw)
    except Exception:
        chunk_payload = {}

    chunks = chunk_payload.get("chunks") if isinstance(chunk_payload, dict) else []
    candidates = chunk_payload.get("entity_candidates") if isinstance(chunk_payload, dict) else []
    if not isinstance(chunks, list):
        chunks = []
    if not isinstance(candidates, list):
        candidates = []

    step_summaries.append(
        {
            "step": "chunk_text_search",
            "n_chunks": len(chunks),
            "n_entity_candidates": len(candidates),
        }
    )

    select_raw = await entity_select_candidate(
        candidate_entities=candidates,
        atom_id=atom_id,
        task_text=task_text or query_text,
        operation=operation,
        expected_coarse_types=expected_coarse_types,
        top_k=max(1, int(max_entities)),
        dataset_name=dataset_name,
        min_candidate_score=0.0,
        require_unambiguous=require_unambiguous,
        ambiguity_score_gap=ambiguity_score_gap,
    )
    try:
        select_payload = json.loads(select_raw)
    except Exception:
        select_payload = {}
    selected_entities = select_payload.get("selected_entities") if isinstance(select_payload, dict) else []
    if not isinstance(selected_entities, list):
        selected_entities = []

    entity_ids: list[str] = []
    for item in selected_entities:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or "").strip()
        if entity_id and entity_id not in entity_ids:
            entity_ids.append(entity_id)

    step_summaries.append(
        {
            "step": "entity_select_candidate",
            "n_selected_entities": len(entity_ids),
        }
    )

    if not entity_ids:
        return json.dumps(
            {
                "resolved_dataset_name": _resolve_dataset_name(dataset_name),
                "chunks": chunks,
                "entity_candidates": candidates,
                "selected_entities": [],
                "selection_status": select_payload.get("status") if isinstance(select_payload, dict) else None,
                "selection_status_message": select_payload.get("status_message") if isinstance(select_payload, dict) else None,
                "selection_top_candidates": select_payload.get("top_candidates") if isinstance(select_payload, dict) else None,
                "selection_suggested_next_actions": select_payload.get("suggested_next_actions") if isinstance(select_payload, dict) else None,
                "neighbors": {},
                "substeps": step_summaries,
                "status_message": "No canonical entity candidates selected; expansion skipped.",
            },
            indent=2,
            default=str,
        )

    onehop_raw = await entity_onehop(
        entity_ids=entity_ids,
        graph_reference_id=graph_reference_id,
        dataset_name=dataset_name,
        neighbor_limit_per_entity=max(1, int(neighbor_limit_per_entity)),
    )
    try:
        onehop_payload = json.loads(onehop_raw)
    except Exception:
        onehop_payload = {}

    neighbors = onehop_payload.get("neighbors") if isinstance(onehop_payload, dict) else {}
    if not isinstance(neighbors, dict):
        neighbors = {}
    step_summaries.append(
        {
            "step": "entity_onehop",
            "n_neighbor_groups": len(neighbors),
        }
    )

    compact_chunks: list[dict[str, Any]] = []
    for item in chunks:
        if not isinstance(item, dict):
            continue
        compact_chunks.append(
            {
                "chunk_id": item.get("chunk_id"),
                "evidence_ref": item.get("evidence_ref") or item.get("chunk_id"),
                "score": item.get("score"),
                "text": item.get("text"),
            }
        )

    composite_evidence_refs: list[str] = []
    for item in compact_chunks:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("evidence_ref") or "").strip()
        if ref and ref not in composite_evidence_refs:
            composite_evidence_refs.append(ref)
    for item in selected_entities:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("evidence_ref") or "").strip()
        if ref and ref not in composite_evidence_refs:
            composite_evidence_refs.append(ref)

    return json.dumps(
        {
            "resolved_dataset_name": chunk_payload.get("resolved_dataset_name") if isinstance(chunk_payload, dict) else _resolve_dataset_name(dataset_name),
            "resolved_graph_reference_id": onehop_payload.get("resolved_graph_reference_id") if isinstance(onehop_payload, dict) else None,
            "chunks": compact_chunks,
            "evidence_refs": composite_evidence_refs,
            "entity_candidates": candidates,
            "selected_entities": selected_entities,
            "neighbors": neighbors,
            "substeps": step_summaries,
            "status_message": (
                f"Composite search/expand produced {len(compact_chunks)} chunks, "
                f"{len(selected_entities)} selected entities, {len(neighbors)} one-hop groups"
            ),
        },
        indent=2,
        default=str,
    )


# =============================================================================
# GRAPH ANALYSIS TOOLS
# =============================================================================

if not BENCHMARK_MODE:
    @mcp.tool()
    async def graph_analyze(graph_id: str) -> str:
        """Get statistics and metrics about a built graph (node count, edge count, centrality, clustering, etc).

        Args:
            graph_id: ID of the graph to analyze

        Returns:
            node_count: int, edge_count: int, density: float, avg_degree: float, centrality_stats: {...}, clustering_coefficient: float
        """
        await _ensure_initialized()
        from Core.AgentTools.graph_analysis_tools import analyze_graph

        inputs = {"graph_id": graph_id}
        result = analyze_graph(inputs, _state["context"])
        return _format_result(result)


    @mcp.tool()
    async def graph_visualize(graph_id: str, output_format: str = "JSON_NODES_EDGES") -> str:
        """Export a graph's structure for visualization (nodes and edges as JSON).

        Args:
            graph_id: ID of the graph to export
            output_format: Format - 'JSON_NODES_EDGES' or 'GML'

        Returns:
            nodes: list of {id: str, label: str, ...}, edges: list of {source: str, target: str, ...}
        """
        await _ensure_initialized()
        from Core.AgentTools.graph_visualization_tools import visualize_graph

        inputs = {"graph_id": graph_id, "output_format": output_format}
        result = visualize_graph(inputs, _state["context"])
        return _format_result(result)


    @mcp.tool()
    async def augment_chunk_cooccurrence(dataset_name: str, weight: float = 0.5) -> str:
        """Add chunk co-occurrence edges to an existing graph without rebuilding.

        Entities that share a source chunk but lack an explicit extracted edge
        get an implicit 'chunk_cooccurrence' edge. Useful for improving recall
        on multi-hop questions where entities are mentioned together.

        Args:
            dataset_name: Name of the dataset (must have graph built)
            weight: Edge weight for co-occurrence edges (default 0.5)

        Returns:
            edges_added: int, status: str
        """
        await _ensure_initialized()
        ctx = _state["context"]
        graph = None
        for gid in ctx.list_graphs():
            if dataset_name in gid:
                graph = ctx.get_graph_instance(gid)
                break
        if graph is None:
            return _format_result({"status": "error", "message": f"No graph found for dataset '{dataset_name}'. Build one first."})
        count = await graph.augment_graph_by_chunk_cooccurrence(weight=weight)
        return _format_result({"edges_added": count, "status": "success"})

    @mcp.tool()
    async def augment_centrality(dataset_name: str) -> str:
        """Compute centrality metrics (PageRank, degree, betweenness) and store as node attributes.

        Pre-computing centrality enables fast retrieval-time prioritization
        of important entities without re-computing graph metrics each query.

        Args:
            dataset_name: Name of the dataset (must have graph built)

        Returns:
            nodes_updated: int, pagerank_max: float, degree_centrality_max: float
        """
        await _ensure_initialized()
        ctx = _state["context"]
        graph = None
        for gid in ctx.list_graphs():
            if dataset_name in gid:
                graph = ctx.get_graph_instance(gid)
                break
        if graph is None:
            return _format_result({"status": "error", "message": f"No graph found for dataset '{dataset_name}'. Build one first."})
        stats = await graph.augment_graph_with_centrality()
        stats["status"] = "success"
        return _format_result(stats)

    @mcp.tool()
    async def augment_synonym_edges(dataset_name: str, threshold: float = 0.92) -> str:
        """Detect near-duplicate entities via embedding similarity and add SYNONYM edges.

        Entities whose VDB embeddings are above the similarity threshold
        get a 'synonym' edge if they don't already share an edge.
        Requires entity VDB to be built.

        Args:
            dataset_name: Name of the dataset (must have graph and entity VDB built)
            threshold: Cosine similarity threshold (default 0.92, very high to avoid false positives)

        Returns:
            edges_added: int, status: str
        """
        await _ensure_initialized()
        ctx = _state["context"]
        graph = None
        entity_vdb = None
        for gid in ctx.list_graphs():
            if dataset_name in gid:
                graph = ctx.get_graph_instance(gid)
                break
        for vid in ctx.list_vdbs():
            if dataset_name in vid and "entit" in vid.lower():
                entity_vdb = ctx.get_vdb_instance(vid)
                break
        if graph is None:
            return _format_result({"status": "error", "message": f"No graph found for dataset '{dataset_name}'."})
        if entity_vdb is None:
            return _format_result({"status": "error", "message": f"No entity VDB found for dataset '{dataset_name}'. Build one first."})
        count = await graph.augment_graph_by_synonym_detection(entity_vdb, threshold=threshold)
        return _format_result({"edges_added": count, "status": "success"})


# =============================================================================
# COMMUNITY TOOLS
# =============================================================================

async def build_communities(dataset_name: str, force_rebuild: bool = False) -> str:
    """Run Leiden clustering on an existing graph and generate community reports.

    Required by basic_global method. This calls LLM to generate community summaries,
    so it's more expensive than VDB builds but much cheaper than graph rebuilds.

    Args:
        dataset_name: Name of the dataset (must have graph built)
        force_rebuild: Force rebuild even if community data exists on disk

    Returns:
        status: str, dataset: str, num_communities: int
    """
    await _ensure_initialized()
    ctx = _state["context"]
    config = _state["config"]
    llm = _state.get("agentic_llm") or _state["llm"]

    # Tag the LLM for community building
    if hasattr(llm, "set_task"):
        llm.set_task("digimon.build_communities")
    if hasattr(llm, "set_trace_id"):
        llm.set_trace_id(f"digimon.build_communities.{dataset_name}.{uuid.uuid4().hex[:8]}")

    # Find the graph for this dataset
    gi = None
    if hasattr(ctx, "list_graphs"):
        for gid in ctx.list_graphs():
            if dataset_name in gid:
                gi = ctx.get_graph_instance(gid)
                break

    if gi is None:
        return json.dumps({"error": f"No graph found for dataset '{dataset_name}'. Build one first."})

    # Get largest connected component for clustering
    lcc = await gi.stable_largest_cc()
    if lcc is None:
        return json.dumps({"error": "Could not compute largest connected component"})

    # Build community namespace using Workspace/NameSpace pattern
    from Core.Storage.NameSpace import Workspace
    workspace = Workspace(config.working_dir, dataset_name)
    community_ns = workspace.make_for("community_storage")

    # Instantiate Leiden community
    from Core.Community.ClusterFactory import get_community
    community = get_community(
        "leiden",
        enforce_sub_communities=False,
        llm=llm,
        namespace=community_ns,
    )

    # Cluster
    logger.info(f"Running Leiden clustering for '{dataset_name}'")
    await community.cluster(
        largest_cc=lcc,
        max_cluster_size=getattr(config.graph, "max_graph_cluster_size", 10),
        random_seed=getattr(config.graph, "graph_cluster_seed", 0xDEADBEEF),
        force=force_rebuild,
    )

    # Generate community reports (calls LLM)
    logger.info(f"Generating community reports for '{dataset_name}'")
    await community.generate_community_report(gi, force=force_rebuild)

    # Store in _state for _build_operator_context_for_dataset to find
    _state.setdefault("communities", {})[dataset_name] = community

    # Count communities from the reports
    report_data = community.community_reports.json_data if hasattr(community, "community_reports") else {}
    num_communities = len(report_data) if report_data else 0

    logger.info(f"Community detection complete for '{dataset_name}': {num_communities} communities")

    return json.dumps({
        "status": "success",
        "dataset": dataset_name,
        "num_communities": num_communities,
    }, indent=2)

if not BENCHMARK_MODE:
    build_communities = mcp.tool()(build_communities)


@mcp.tool()
async def community_detect_from_entities(graph_reference_id: str,
                                          seed_entity_ids: list[str],
                                          max_communities: int = 5) -> str:
    """Find communities containing the given seed entities.

    Args:
        graph_reference_id: ID of the graph with community structure
        seed_entity_ids: Entity IDs to find communities for
        max_communities: Maximum communities to return

    Returns:
        relevant_communities: list of {community_id: str, level?: int, title?: str, nodes?: list, description?: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.community_tools import community_detect_from_entities_tool
    from Core.AgentSchema.tool_contracts import CommunityDetectFromEntitiesInputs

    inputs = CommunityDetectFromEntitiesInputs(
        graph_reference_id=graph_reference_id,
        seed_entity_ids=seed_entity_ids,
        max_communities_to_return=max_communities,
    )
    result = await community_detect_from_entities_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def community_get_layer(community_hierarchy_reference_id: str,
                               max_layer_depth: int = 1) -> str:
    """Get all communities at or below a hierarchy layer depth.

    Args:
        community_hierarchy_reference_id: Graph ID with community hierarchy
        max_layer_depth: Maximum layer depth to include (0=top level)

    Returns:
        communities_in_layers: list of {community_id: str, level?: int, title?: str, nodes?: list, description?: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.community_tools import community_get_layer_tool
    from Core.AgentSchema.tool_contracts import CommunityGetLayerInputs

    inputs = CommunityGetLayerInputs(
        community_hierarchy_reference_id=community_hierarchy_reference_id,
        max_layer_depth=max_layer_depth,
    )
    result = await community_get_layer_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# SUBGRAPH TOOLS
# =============================================================================

@mcp.tool()
async def subgraph_khop_paths(graph_reference_id: str,
                               start_entity_ids: list[str],
                               end_entity_ids: list[str] = None,
                               k_hops: int = 2,
                               max_paths: int = 10) -> str:
    """Find k-hop paths between entities in a graph.

    Args:
        graph_reference_id: ID of the graph to search
        start_entity_ids: Starting entity IDs
        end_entity_ids: Target entity IDs (if None, explores k-hop neighborhood)
        k_hops: Maximum number of hops
        max_paths: Maximum paths to return

    Returns:
        discovered_paths: list of {path_id: str, segments: [{item_id: str, item_type: str, label?: str}], start_node_id: str, hop_count: int}
    """
    await _ensure_initialized()
    from Core.AgentTools.subgraph_tools import subgraph_khop_paths_tool
    from Core.AgentSchema.tool_contracts import SubgraphKHopPathsInputs

    inputs = SubgraphKHopPathsInputs(
        graph_reference_id=graph_reference_id,
        start_entity_ids=start_entity_ids,
        end_entity_ids=end_entity_ids,
        k_hops=k_hops,
        max_paths_to_return=max_paths,
    )
    result = await subgraph_khop_paths_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def subgraph_steiner_tree(graph_reference_id: str,
                                 terminal_node_ids: list[str]) -> str:
    """Compute a Steiner tree connecting the given terminal entities.

    Args:
        graph_reference_id: ID of the graph
        terminal_node_ids: Entity IDs that must be connected (minimum 2)

    Returns:
        steiner_tree_edges: list of {source: str, target: str, weight?: float}
    """
    await _ensure_initialized()
    from Core.AgentTools.subgraph_tools import subgraph_steiner_tree_tool
    from Core.AgentSchema.tool_contracts import SubgraphSteinerTreeInputs

    inputs = SubgraphSteinerTreeInputs(
        graph_reference_id=graph_reference_id,
        terminal_node_ids=terminal_node_ids,
    )
    result = await subgraph_steiner_tree_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def subgraph_agent_path(user_question: str,
                               candidate_paths_json: str,
                               max_paths: int = 5) -> str:
    """Use LLM to rank candidate paths by relevance to a question.

    Args:
        user_question: The question to evaluate path relevance against
        candidate_paths_json: JSON string of candidate PathObject list
        max_paths: Maximum relevant paths to return

    Returns:
        relevant_paths: list of {path_id: str, segments: [{item_id: str, item_type: str, label?: str}]}
    """
    await _ensure_initialized()
    from Core.AgentTools.subgraph_tools import subgraph_agent_path_tool
    from Core.AgentSchema.tool_contracts import SubgraphAgentPathInputs, PathObject

    paths = [PathObject(**p) for p in json.loads(candidate_paths_json)]
    inputs = SubgraphAgentPathInputs(
        user_question=user_question,
        candidate_paths=paths,
        max_paths_to_return=max_paths,
    )
    result = await subgraph_agent_path_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# CONTEXT INSPECTION TOOLS
# =============================================================================

async def list_available_resources() -> str:
    """List all currently available graphs, VDBs, communities, sparse matrices, and datasets."""
    await _ensure_initialized()
    ctx = _state["context"]
    config = _state["config"]

    # Communities loaded in this session
    communities = list(_state.get("communities", {}).keys())

    # Check for persisted sparse matrices on disk
    sparse_matrices_available = []
    graphs = ctx.list_graphs() if hasattr(ctx, "list_graphs") else []
    for gid in graphs:
        # Derive dataset name from graph_id by stripping suffix
        ds = gid
        for suffix in ["_ERGraph", "_RKGraph", "_TreeGraphBalanced", "_TreeGraph", "_PassageGraph"]:
            if ds.endswith(suffix):
                ds = ds[: -len(suffix)]
                break
        e2r_path, r2c_path = _sparse_matrix_paths(ds)
        if e2r_path.exists() and r2c_path.exists():
            sparse_matrices_available.append(ds)

    return json.dumps({
        "graphs": graphs,
        "vdbs": ctx.list_vdbs() if hasattr(ctx, "list_vdbs") else [],
        "communities": communities,
        "sparse_matrices": sparse_matrices_available,
        "working_dir": str(config.working_dir),
        "data_root": str(config.data_root),
    }, indent=2)

list_available_resources = mcp.tool()(list_available_resources)


# =============================================================================
# CONFIG TOOLS
# =============================================================================

@mcp.tool()
async def get_config() -> str:
    """Get current DIGIMON configuration (model roles, paths).

    Returns JSON with llm_model, agentic_model, data_root, and working_dir.
    """
    await _ensure_initialized()
    config = _state["config"]

    agentic_model = None
    agentic_source = None
    if _state.get("agentic_llm"):
        agentic_model = _state["agentic_llm"].model
        agentic_source = _state.get("agentic_model_source", "config")

    return json.dumps({
        "llm_model": config.llm.model,
        "agentic_model": agentic_model,
        "agentic_model_source": agentic_source,
        "data_root": str(config.data_root),
        "working_dir": str(config.working_dir),
    }, indent=2)


@mcp.tool()
async def set_agentic_model(model: str) -> str:
    """Override the agentic model at runtime.

    The agentic model handles mid-pipeline LLM calls (entity extraction,
    answer generation, iterative reasoning). Graph building uses the
    separate llm.model and is unaffected.

    Args:
        model: Model identifier (e.g. 'gemini/gemini-2.0-flash', 'anthropic/claude-sonnet-4-5-20250929')
    """
    await _ensure_initialized()
    from Core.Provider.LLMClientAdapter import LLMClientAdapter

    old_model = _state["agentic_llm"].model if _state.get("agentic_llm") else None
    _state["agentic_llm"] = LLMClientAdapter(model)
    _state["agentic_model_source"] = "runtime_override"

    logger.info(f"Agentic model changed: {old_model} -> {model}")

    return json.dumps({
        "status": "success",
        "previous_model": old_model,
        "new_model": model,
        "source": "runtime_override",
    }, indent=2)



# =============================================================================
# RELATIONSHIP VDB BUILD + SEARCH
# =============================================================================

async def relationship_vdb_build(graph_reference_id: str, vdb_collection_name: str,
                                   force_rebuild: bool = False) -> str:
    """Build a vector database index from relationships in a graph. Required before relationship_vdb_search.

    Args:
        graph_reference_id: ID of the graph (e.g. 'Fictional_Test_ERGraph')
        vdb_collection_name: Name for the VDB collection (e.g. 'Fictional_Test_relations')
        force_rebuild: Force rebuild even if VDB exists

    Returns:
        status: str, vdb_id: str, num_relationships_indexed: int
    """
    await _ensure_initialized()
    _ensure_embedding_provider_initialized(reason="relationship_vdb_build")
    from Core.AgentTools.relationship_tools import relationship_vdb_build_tool
    from Core.AgentSchema.tool_contracts import RelationshipVDBBuildInputs

    inputs = RelationshipVDBBuildInputs(
        graph_reference_id=graph_reference_id,
        vdb_collection_name=vdb_collection_name,
        force_rebuild=force_rebuild,
    )
    result = await relationship_vdb_build_tool(inputs, _state["context"])
    return _format_result(result)

if not BENCHMARK_MODE:
    relationship_vdb_build = mcp.tool()(relationship_vdb_build)

@mcp.tool()
async def relationship_vdb_search(vdb_reference_id: str, query_text: str = "",
                                   top_k: int = 10,
                                   score_threshold: float = None,
                                   entity_names: list[str] | str | None = None) -> str:
    """Search for relationships similar to a query using vector similarity.

    Args:
        vdb_reference_id: ID of the relationship VDB to search
        query_text: Natural language search query
        top_k: Number of results to return
        score_threshold: Minimum similarity score (optional)
        entity_names: Optional entity names to inject into the relationship query context

    Returns:
        similar_relationships: list of [relationship_id: str, description: str, score: float]
    """
    await _ensure_initialized()
    from Core.AgentTools.relationship_tools import relationship_vdb_search_tool
    from Core.AgentSchema.tool_contracts import RelationshipVDBSearchInputs

    query_parts = [str(query_text or "").strip()]
    query_parts.extend(_normalize_string_list(entity_names))
    effective_query = " ".join(part for part in query_parts if part)
    if not effective_query:
        return json.dumps({"error": "query_text or entity_names is required"}, indent=2)

    inputs = RelationshipVDBSearchInputs(
        vdb_reference_id=vdb_reference_id,
        query_text=effective_query,
        top_k=top_k,
        score_threshold=score_threshold,
    )
    result = await relationship_vdb_search_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# SPARSE MATRIX BUILD
# =============================================================================

async def build_sparse_matrices(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build sparse CSR matrices mapping entities→relationships→chunks for a graph.

    Required by fastgraphrag and hipporag methods. Persists matrices to disk.

    Args:
        dataset_name: Name of the dataset (must have graph built)
        force_rebuild: Force rebuild even if matrices exist on disk

    Returns:
        status: str, dataset: str, entity_to_rel_shape: [int, int], rel_to_chunk_shape: [int, int]
    """
    await _ensure_initialized()
    ctx = _state["context"]
    config = _state["config"]
    chunk_factory = _state.get("chunk_factory")

    # Find the graph for this dataset
    graph_id = None
    gi = None
    if hasattr(ctx, "list_graphs"):
        for gid in ctx.list_graphs():
            if dataset_name in gid:
                graph_id = gid
                gi = ctx.get_graph_instance(gid)
                break

    if gi is None:
        return json.dumps({"error": f"No graph found for dataset '{dataset_name}'. Build one first."})

    # Check if already built (unless force)
    e2r_path, r2c_path = _sparse_matrix_paths(dataset_name)
    if not force_rebuild and e2r_path.exists() and r2c_path.exists():
        matrices = _try_load_sparse_matrices(dataset_name)
        if matrices:
            gi.sparse_matrices = matrices
            e2r = matrices["entity_to_rel"]
            r2c = matrices["rel_to_chunk"]
            return json.dumps({
                "status": "loaded_from_disk",
                "dataset": dataset_name,
                "entity_to_rel_shape": list(e2r.shape),
                "rel_to_chunk_shape": list(r2c.shape),
            }, indent=2)

    # Build entity_to_rel matrix
    logger.info(f"Building entity_to_rel sparse matrix for '{dataset_name}'")
    e2r = await gi.get_entities_to_relationships_map(is_directed=False)

    # Build rel_to_chunk matrix via _DocChunkAdapter
    logger.info(f"Building rel_to_chunk sparse matrix for '{dataset_name}'")
    if chunk_factory is None:
        return json.dumps({"error": "ChunkFactory not available"})

    chunks_list = await chunk_factory.get_chunks_for_dataset(dataset_name)
    if not chunks_list:
        return json.dumps({"error": f"No chunks found for dataset '{dataset_name}'"})

    adapter = _DocChunkAdapter(chunks_list)
    r2c = await gi.get_relationships_to_chunks_map(adapter)

    # Stash on graph instance
    matrices = {"entity_to_rel": e2r, "rel_to_chunk": r2c}
    gi.sparse_matrices = matrices

    # Persist to disk
    e2r_path.parent.mkdir(parents=True, exist_ok=True)
    with open(e2r_path, "wb") as f:
        pickle.dump(e2r, f)
    with open(r2c_path, "wb") as f:
        pickle.dump(r2c, f)

    logger.info(f"Sparse matrices built and persisted for '{dataset_name}': "
                f"e2r={e2r.shape}, r2c={r2c.shape}")

    return json.dumps({
        "status": "success",
        "dataset": dataset_name,
        "entity_to_rel_shape": list(e2r.shape),
        "rel_to_chunk_shape": list(r2c.shape),
    }, indent=2)

if not BENCHMARK_MODE:
    build_sparse_matrices = mcp.tool()(build_sparse_matrices)


# =============================================================================
# CHUNK AGGREGATOR
# =============================================================================

@mcp.tool()
async def chunk_aggregator(relationship_scores: dict,
                            graph_reference_id: str,
                            top_k: int = 10) -> str:
    """Propagate relationship/PPR scores to chunks via sparse matrices.

    Used in FastGraphRAG and HippoRAG pipelines. Requires sparse matrices
    built during graph construction.

    Args:
        relationship_scores: Dict mapping relationship_id to score
        graph_reference_id: Graph ID containing the chunks
        top_k: Maximum chunks to return

    Returns:
        ranked_aggregated_chunks: list of {chunk_id: str, content: str, relevance_score?: float}
    """
    await _ensure_initialized()
    from Core.AgentTools.chunk_tools import chunk_aggregator_tool
    from Core.AgentSchema.tool_contracts import ChunkRelationshipScoreAggregatorInputs

    inputs = ChunkRelationshipScoreAggregatorInputs(
        chunk_candidates=[],  # Will be populated from graph
        relationship_scores=relationship_scores,
        top_k_chunks=top_k,
    )
    result = await chunk_aggregator_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# META OPERATORS (LLM-powered)
# =============================================================================

@mcp.tool()
async def meta_extract_entities(query_text: str) -> str:
    """Use LLM to extract entity mentions from query text.

    Useful when you need to identify entities in a question before linking
    them to graph entities. Used in HippoRAG, ToG, and DALK pipelines.

    Args:
        query_text: The question or text to extract entities from

    Returns:
        entities: list of {entity_name: str, score: float}
    """
    await _ensure_initialized()
    from Core.Operators.meta.extract_entities import meta_extract_entities as _extract
    from Core.Schema.SlotTypes import SlotKind, SlotValue

    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp")}
    result = await _extract(inputs=inputs, ctx=_build_operator_context("digimon.meta_extract_entities"), params={})

    # Convert SlotValue result to serializable format
    entities = result.get("entities")
    if entities and hasattr(entities, "data"):
        return json.dumps({
            "entities": [
                {"entity_name": e.entity_name, "score": e.score}
                for e in entities.data
            ]
        }, indent=2)
    return json.dumps({"entities": []})


@mcp.tool()
async def meta_generate_answer(query_text: str, context_chunks: list[str],
                                system_prompt: str = None) -> str:
    """Generate an answer from query + retrieved text chunks using LLM.

    Terminal operator in most retrieval pipelines. Pass retrieved chunks
    as context for the LLM to synthesize an answer.

    Args:
        query_text: The question to answer
        context_chunks: List of text strings providing context
        system_prompt: Optional custom system prompt (supports {context_data} placeholder)

    Returns:
        Plain text string (LLM-generated answer)
    """
    await _ensure_initialized()
    from Core.Operators.meta.generate_answer import meta_generate_answer as _generate
    from Core.Schema.SlotTypes import ChunkRecord, SlotKind, SlotValue

    chunk_records = [ChunkRecord(chunk_id=f"mcp_{i}", text=t) for i, t in enumerate(context_chunks)]
    inputs = {
        "query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp"),
        "chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=chunk_records, producer="mcp"),
    }
    params = {}
    if system_prompt:
        params["system_prompt"] = system_prompt

    result = await _generate(inputs=inputs, ctx=_build_operator_context("digimon.meta_generate_answer"), params=params)

    answer = result.get("answer")
    if answer and hasattr(answer, "data"):
        return answer.data
    return "Failed to generate answer."


@mcp.tool()
async def meta_pcst_optimize(entity_ids: list[str], entity_scores: dict,
                               relationship_triples: list[dict],
                               graph_reference_id: str) -> str:
    """Optimize entity+relationship sets into a compact subgraph using PCST.

    Prize-Collecting Steiner Tree selects the most informative nodes and
    edges based on scores. Used in the GR method pipeline.

    Args:
        entity_ids: List of entity names/IDs
        entity_scores: Dict mapping entity_id to score (prize)
        relationship_triples: List of dicts with src_id, tgt_id, weight keys
        graph_reference_id: Graph ID for context

    Returns:
        nodes: list of str, edges: list of [source: str, target: str]
    """
    await _ensure_initialized()
    from Core.Operators.meta.pcst_optimize import meta_pcst_optimize as _pcst
    from Core.Schema.SlotTypes import EntityRecord, RelationshipRecord, SlotKind, SlotValue

    entities = [
        EntityRecord(entity_name=eid, score=entity_scores.get(eid, 1.0))
        for eid in entity_ids
    ]
    rels = [
        RelationshipRecord(
            src_id=r["src_id"], tgt_id=r["tgt_id"],
            weight=r.get("weight", 1.0),
            description=r.get("description", ""),
        )
        for r in relationship_triples
    ]

    inputs = {
        "entities": SlotValue(kind=SlotKind.ENTITY_SET, data=entities, producer="mcp"),
        "relationships": SlotValue(kind=SlotKind.RELATIONSHIP_SET, data=rels, producer="mcp"),
    }
    result = await _pcst(inputs=inputs, ctx=_build_operator_context("digimon.meta_pcst_optimize"), params={})

    sg = result.get("subgraph")
    if sg and hasattr(sg, "data"):
        sg_data = sg.data
        return json.dumps({
            "nodes": list(sg_data.nodes) if sg_data.nodes else [],
            "edges": [(e[0], e[1]) if isinstance(e, tuple) else e for e in (sg_data.edges or [])],
        }, indent=2, default=str)
    return json.dumps({"nodes": [], "edges": []})


@mcp.tool()
async def meta_decompose_question(query_text: str, max_questions: int = 5) -> str:
    """Decompose a complex question into independent sub-questions (AoT-style).

    Breaks a multi-hop question into focused sub-questions that can each be
    answered via separate retrieval chains, then combined with meta_synthesize_answers.

    Args:
        query_text: The complex question to decompose
        max_questions: Maximum number of sub-questions to generate

    Returns:
        sub_questions: list of {entity_name: str (sub-question text), entity_type: "sub_question", score: float}
    """
    await _ensure_initialized()
    from Core.Operators.meta.decompose_question import meta_decompose_question as _decompose
    from Core.Schema.SlotTypes import SlotKind, SlotValue

    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp")}
    result = await _decompose(inputs=inputs, ctx=_build_operator_context("digimon.meta_decompose_question"), params={"max_questions": max_questions})

    sub_qs = result.get("sub_questions")
    if sub_qs and hasattr(sub_qs, "data"):
        return json.dumps({
            "sub_questions": [
                {"entity_name": e.entity_name, "entity_type": e.entity_type, "score": e.score}
                for e in sub_qs.data
            ]
        }, indent=2)
    return json.dumps({"sub_questions": []})


@mcp.tool()
async def meta_synthesize_answers(query_text: str, sub_answers: list[str],
                                   synthesis_style: str = "concise") -> str:
    """Synthesize sub-answers into a final coherent answer.

    Combines answers from parallel retrieval chains (e.g., from decomposed
    sub-questions) into a single answer addressing the original question.

    Args:
        query_text: The original question
        sub_answers: List of sub-answer strings to synthesize
        synthesis_style: Style of synthesis: 'concise', 'detailed', or 'bullet_points'

    Returns:
        Plain text string (synthesized answer)
    """
    await _ensure_initialized()
    from Core.Operators.meta.synthesize_answers import meta_synthesize_answers as _synthesize
    from Core.Schema.SlotTypes import ChunkRecord, SlotKind, SlotValue

    chunk_records = [ChunkRecord(chunk_id=f"sub_{i}", text=t) for i, t in enumerate(sub_answers)]
    inputs = {
        "query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp"),
        "chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=chunk_records, producer="mcp"),
    }
    result = await _synthesize(inputs=inputs, ctx=_build_operator_context("digimon.meta_synthesize_answers"), params={"synthesis_style": synthesis_style})

    answer = result.get("answer")
    if answer and hasattr(answer, "data"):
        return answer.data
    return "Failed to synthesize answer."


def _build_operator_context(task: str, trace_id: str | None = None) -> Any:
    """Build an OperatorContext from the global MCP state for meta operator calls.

    Args:
        task: Task label for LLM call tagging (e.g. "digimon.meta_extract_entities")
        trace_id: Optional trace ID; if None, auto-generated from task
    """
    from Core.Operators._context import OperatorContext

    if trace_id is None:
        trace_id = f"{task}.{uuid.uuid4().hex[:8]}"

    ctx = _state["context"]

    # Extract the first available graph and its resources
    graph = None
    entities_vdb = None
    relations_vdb = None
    doc_chunks = None

    if hasattr(ctx, "list_graphs"):
        graphs = ctx.list_graphs()
        if graphs:
            graph_id = graphs[0]
            gi = ctx.get_graph_instance(graph_id)
            if gi:
                graph = gi._graph if hasattr(gi, "_graph") else gi

    llm = _state.get("agentic_llm") or _state["llm"]
    if hasattr(llm, "set_task"):
        llm.set_task(task)
    if hasattr(llm, "set_trace_id"):
        llm.set_trace_id(trace_id)

    return OperatorContext(
        graph=graph,
        entities_vdb=entities_vdb,
        relations_vdb=relations_vdb,
        doc_chunks=doc_chunks,
        llm=llm,
        config=_state["config"],
        trace_id=trace_id,
    )


# =============================================================================
# OPERATOR DISCOVERY TOOLS
# =============================================================================

@mcp.tool()
async def list_operators() -> str:
    """List all 24 operators with their I/O slots, cost tiers, and when to use.

    Returns the full operator catalog. Each entry includes operator_id,
    display_name, category, input/output slots (name + kind), cost_tier,
    requires_* flags, and when_to_use guidance.
    """
    await _ensure_initialized()
    from Core.Operators.registry import REGISTRY

    operators = REGISTRY.list_all()
    return json.dumps([
        {
            "operator_id": op.operator_id,
            "display_name": op.display_name,
            "category": op.category,
            "input_slots": [{"name": s.name, "kind": s.kind.value, "required": s.required} for s in op.input_slots],
            "output_slots": [{"name": s.name, "kind": s.kind.value} for s in op.output_slots],
            "cost_tier": op.cost_tier.value,
            "requires_llm": op.requires_llm,
            "requires_entity_vdb": op.requires_entity_vdb,
            "requires_relationship_vdb": op.requires_relationship_vdb,
            "requires_community": op.requires_community,
            "requires_sparse_matrices": op.requires_sparse_matrices,
            "when_to_use": op.when_to_use,
        }
        for op in operators
    ], indent=2)


@mcp.tool()
async def get_compatible_successors(operator_id: str) -> str:
    """Get operators that can consume the outputs of a given operator.

    Use this to explore valid operator chains. For example,
    get_compatible_successors("entity.ppr") returns operators that
    accept ENTITY_SET or SCORE_VECTOR as input.

    Args:
        operator_id: The operator to find successors for (e.g. 'entity.ppr')
    """
    await _ensure_initialized()
    from Core.Operators.registry import REGISTRY

    source = REGISTRY.get(operator_id)
    if not source:
        return json.dumps({"error": f"Unknown operator: '{operator_id}'"})

    successors = REGISTRY.get_compatible_successors(operator_id)
    return json.dumps([
        {
            "operator_id": op.operator_id,
            "display_name": op.display_name,
            "input_slots": [{"name": s.name, "kind": s.kind.value, "required": s.required} for s in op.input_slots],
            "output_slots": [{"name": s.name, "kind": s.kind.value} for s in op.output_slots],
            "cost_tier": op.cost_tier.value,
        }
        for op in successors
    ], indent=2)




@mcp.tool()
async def list_graph_types() -> str:
    """List all 5 available graph types with descriptions and guidance.

    Returns information about each graph type to help decide which to build.
    """
    graph_types = [
        {
            "name": "er",
            "build_tool": "graph_build_er",
            "description": "Entity-Relationship graph. Extracts entities and relationships using LLM.",
            "best_for": "General-purpose knowledge graphs. Works with all retrieval methods.",
            "capabilities": "Entities, relationships, source_ids for chunk lookup. Supports VDB, PPR, community detection.",
        },
        {
            "name": "rk",
            "build_tool": "graph_build_rk",
            "description": "Relationship-Keyword graph. Like ER but enriches edges with keywords.",
            "best_for": "Keyword-based retrieval (LightRAG). When relationship descriptions matter.",
            "capabilities": "All ER capabilities plus keyword-enriched edges for better relationship VDB search.",
        },
        {
            "name": "tree",
            "build_tool": "graph_build_tree",
            "description": "Hierarchical Tree graph (RAPTOR-style). Clusters chunks into summaries.",
            "best_for": "Summarization tasks. When you need multi-level abstraction of documents.",
            "capabilities": "Hierarchical clustering with summary nodes. Supports community-based retrieval.",
        },
        {
            "name": "tree_balanced",
            "build_tool": "graph_build_tree_balanced",
            "description": "Balanced Tree using K-Means clustering for uniform cluster sizes.",
            "best_for": "Same as tree but when more uniform cluster sizes are desired.",
            "capabilities": "Same as tree with better-balanced clusters.",
        },
        {
            "name": "passage",
            "build_tool": "graph_build_passage",
            "description": "Passage graph. Nodes are text passages linked by shared entities.",
            "best_for": "Document-centric retrieval. When passages themselves are the primary units.",
            "capabilities": "Passage-level nodes with entity-based edges. Good for passage retrieval.",
        },
    ]
    return json.dumps(graph_types, indent=2)






class _ChunkLookup:
    """Wraps ChunkFactory data as a key-value store for operators."""

    def __init__(self, chunks_dict: dict):
        self._chunks = chunks_dict

    async def get_data_by_key(self, chunk_id: str):
        return self._chunks.get(chunk_id)

    async def get_data_by_indices(self, indices):
        keys = list(self._chunks.keys())
        return [
            self._chunks[keys[i]] if i < len(keys) else None
            for i in indices
        ]


class _DocChunkAdapter:
    """Adapter to make ChunkFactory data look like a DocChunk for sparse matrix building.

    BaseGraph.get_relationships_to_chunks_map() needs an object with:
      - async get_index_by_merge_key(source_id_str) -> list[Optional[int]]
      - async size -> int
    """

    def __init__(self, chunks: List[Tuple[str, Any]]):
        from Core.Common.Utils import split_string_by_multi_markers
        from Core.Common.Constants import GRAPH_FIELD_SEP
        self._split_markers = [GRAPH_FIELD_SEP]
        self._split_fn = split_string_by_multi_markers
        self._key_to_index: dict[str, int] = {}
        for i, (chunk_id, _) in enumerate(chunks):
            self._key_to_index[chunk_id] = i
        self._size = len(chunks)

    @property
    async def size(self) -> int:
        return self._size

    async def get_index_by_merge_key(self, merge_chunk_id: str) -> List[Optional[int]]:
        """Map a merged chunk ID string (separated by GRAPH_FIELD_SEP) to indices."""
        key_list = self._split_fn(merge_chunk_id, self._split_markers)
        return [self._key_to_index.get(cid) for cid in key_list]


def _sparse_matrix_paths(dataset_name: str) -> Tuple[Path, Path]:
    """Return (e2r_path, r2c_path) for persisted sparse matrices."""
    config = _state["config"]
    base = Path(config.working_dir) / dataset_name / "er_graph"
    return base / "sparse_e2r.pkl", base / "sparse_r2c.pkl"


def _try_load_sparse_matrices(dataset_name: str) -> dict:
    """Try to load sparse matrices from persisted pickle files."""
    e2r_path, r2c_path = _sparse_matrix_paths(dataset_name)
    if e2r_path.exists() and r2c_path.exists():
        try:
            with open(e2r_path, "rb") as f:
                e2r = pickle.load(f)
            with open(r2c_path, "rb") as f:
                r2c = pickle.load(f)
            logger.info(f"Loaded sparse matrices from disk for '{dataset_name}'")
            return {"entity_to_rel": e2r, "rel_to_chunk": r2c}
        except Exception as e:
            logger.warning(f"Failed to load sparse matrices from disk: {e}")
    return {}


async def _build_operator_context_for_dataset(dataset_name: str, *, trace_id: str | None = None) -> Any:
    """Build a full OperatorContext for a specific dataset."""
    from Core.Operators._context import OperatorContext

    dataset_name = _resolve_dataset_name(dataset_name)
    ctx = _state["context"]

    graph = None
    entities_vdb = None
    relations_vdb = None
    doc_chunks = None
    sparse_matrices = {}

    # Find the graph for this dataset
    if hasattr(ctx, "list_graphs"):
        for graph_id in ctx.list_graphs():
            if dataset_name in graph_id:
                gi = ctx.get_graph_instance(graph_id)
                if gi:
                    graph = gi
                    # Check graph instance for in-memory sparse matrices
                    if hasattr(gi, "sparse_matrices") and gi.sparse_matrices:
                        sparse_matrices = gi.sparse_matrices
                    break

    # Fallback: try loading sparse matrices from persisted pickle files
    if not sparse_matrices:
        sparse_matrices = _try_load_sparse_matrices(dataset_name)

    # Check context-level VDBs
    chunks_vdb = None
    if hasattr(ctx, "list_vdbs"):
        vdb_ids = ctx.list_vdbs()
        for dataset_scoped_only in (True, False):
            for vdb_id in vdb_ids:
                vdb_inst = ctx.get_vdb_instance(vdb_id)
                if not vdb_inst:
                    continue
                if dataset_scoped_only:
                    base_vdb = _strip_dataset_alias_suffix(vdb_id)
                    in_dataset = (
                        dataset_name.lower() in vdb_id.lower()
                        or base_vdb.lower() == dataset_name.lower()
                    )
                    if not in_dataset:
                        continue
                if "entities" in vdb_id and entities_vdb is None:
                    entities_vdb = vdb_inst
                elif "relation" in vdb_id and relations_vdb is None:
                    relations_vdb = vdb_inst
                elif "chunks" in vdb_id and chunks_vdb is None:
                    chunks_vdb = vdb_inst
            if entities_vdb or relations_vdb or chunks_vdb:
                break

    # Build doc_chunks from ChunkFactory storage
    chunk_storage = getattr(ctx, "chunk_storage_manager", None) or _state.get("chunk_factory")
    if chunk_storage and doc_chunks is None:
        try:
            chunks_list = await chunk_storage.get_chunks_for_dataset(dataset_name)
            chunks_dict = {}
            for chunk_id, chunk_obj in chunks_list:
                content = chunk_obj.content if hasattr(chunk_obj, "content") else str(chunk_obj)
                chunks_dict[chunk_id] = content
            if chunks_dict:
                doc_chunks = _ChunkLookup(chunks_dict)
        except Exception as e:
            logger.warning(f"Could not load chunks for dataset '{dataset_name}': {e}")

    # Look up community from _state (set by build_communities tool)
    community = _state.get("communities", {}).get(dataset_name)

    # Operators expect RetrieverConfig (has top_k, max_token_*, etc.),
    # not the top-level Config object.
    full_config = _state["config"]
    retriever_config = getattr(full_config, "retriever", full_config)

    llm = _state.get("agentic_llm") or _state["llm"]
    if trace_id and hasattr(llm, "set_trace_id"):
        llm.set_trace_id(trace_id)

    # Set trace_id on VDB embedding models if they're LLMClientEmbedding instances
    for vdb in (entities_vdb, relations_vdb, chunks_vdb):
        if vdb is not None:
            embed_model = getattr(vdb, "_embed_model", None)
            if embed_model is not None and hasattr(embed_model, "llm_trace_id"):
                embed_model.llm_trace_id = trace_id

    return OperatorContext(
        graph=graph,
        entities_vdb=entities_vdb,
        relations_vdb=relations_vdb,
        chunks_vdb=chunks_vdb,
        doc_chunks=doc_chunks,
        community=community,
        llm=llm,
        config=retriever_config,
        sparse_matrices=sparse_matrices,
        trace_id=trace_id,
    )



# =============================================================================
# CROSS-MODAL CONVERSION TOOLS
# =============================================================================

@mcp.tool()
async def convert_modality(
    source_format: str,
    target_format: str,
    graph_reference_id: str = "",
    table_path: str = "",
    table_json: str = "",
    vector_json: str = "",
    mode: str = "auto",
    embedding_provider: str = "local",
    similarity_threshold: float = 0.5,
) -> str:
    """Convert data between graph, table, and vector modalities.

    Supported conversion paths (call list_modality_conversions for full details):
      graph -> table: modes = nodes, edges, adjacency
      table -> graph: modes = entity_rel, adjacency, auto
      graph -> vector: modes = node_embed, features
      table -> vector: modes = stats, row_embed
      vector -> graph: modes = similarity, clustering
      vector -> table: modes = direct, pca, similarity

    Args:
        source_format: "graph", "table", or "vector"
        target_format: "graph", "table", or "vector"
        graph_reference_id: Graph ID from context (for graph source)
        table_path: CSV file path (for table source)
        table_json: Inline JSON array of rows (for table source)
        vector_json: Inline JSON 2D array (for vector source)
        mode: Conversion strategy, or "auto" for default
        embedding_provider: "local" (sentence-transformers), "digimon" (configured model), or "hash" (testing)
        similarity_threshold: For vector->graph similarity mode (0.0-1.0)

    Returns:
        data: converted data (JSON rows for table, node/edge dict for graph, nested array for vector),
        format: str, mode: str, shape: [rows, cols], conversion_time_ms: float
    """
    await _ensure_initialized()

    from Core.AgentTools.cross_modal_tools import (
        _extract_networkx_graph as extract_nx, _graph_to_dict, _dict_to_networkx,
        convert, get_embedding_provider, serialize_conversion_result,
    )
    import numpy as np
    import pandas as pd

    # --- Resolve source data ---
    source_data: Any = None

    if source_format == "graph":
        if not graph_reference_id:
            return json.dumps({"error": "graph_reference_id is required for graph source"})
        ctx = _state["context"]
        graph_instance = ctx.get_graph_instance(graph_reference_id)
        if graph_instance is None:
            return json.dumps({"error": f"Graph '{graph_reference_id}' not found in context"})
        nx_graph = extract_nx(graph_instance)
        if nx_graph is None:
            return json.dumps({"error": f"Could not extract NetworkX graph from '{graph_reference_id}'"})
        source_data = _graph_to_dict(nx_graph)

    elif source_format == "table":
        if table_path:
            source_data = pd.read_csv(table_path)
        elif table_json:
            source_data = pd.DataFrame(json.loads(table_json))
        else:
            return json.dumps({"error": "table_path or table_json required for table source"})

    elif source_format == "vector":
        if not vector_json:
            return json.dumps({"error": "vector_json required for vector source"})
        source_data = np.array(json.loads(vector_json), dtype=np.float32)

    else:
        return json.dumps({"error": f"Unknown source_format: {source_format!r}"})

    # --- Get embedding provider ---
    provider = None
    provider_error = None
    try:
        provider = get_embedding_provider(embedding_provider, _state)
    except ValueError as e:
        provider_error = str(e)

    # --- Run conversion ---
    try:
        kwargs: Dict[str, Any] = {}
        if source_format == "vector" and target_format == "graph" and mode in ("similarity", "auto"):
            kwargs["threshold"] = similarity_threshold
        result = await convert(source_data, source_format, target_format,
                               mode=mode, provider=provider, **kwargs)
    except ValueError as e:
        # If embedding provider failed, surface the original error
        if provider_error and "embedding provider" in str(e).lower():
            return json.dumps({"error": f"{e} (provider error: {provider_error})"})
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"convert_modality: {e}", exc_info=True)
        return json.dumps({"error": str(e)})

    # --- Register graph in context if output is graph ---
    if target_format == "graph" and isinstance(result["data"], dict) and "nodes" in result["data"]:
        nx_graph = _dict_to_networkx(result["data"])
        ref_id = f"converted_{source_format}_to_graph"
        if graph_reference_id:
            ref_id = f"{graph_reference_id}_as_graph"
        from types import SimpleNamespace
        wrapper = SimpleNamespace(_graph=SimpleNamespace(graph=nx_graph))
        _state["context"].add_graph_instance(ref_id, wrapper)
        result["graph_reference_id"] = ref_id

    serialized = serialize_conversion_result(result)
    if "graph_reference_id" in result:
        serialized["graph_reference_id"] = result["graph_reference_id"]
    return json.dumps(serialized, indent=2, default=str)


@mcp.tool()
async def validate_conversion(
    format_sequence: str,
    graph_reference_id: str = "",
    table_json: str = "",
    vector_json: str = "",
    mode_sequence: str = "",
    embedding_provider: str = "local",
) -> str:
    """Validate round-trip conversion quality by converting through a sequence of formats.

    Example: format_sequence="graph,table,graph" converts graph->table->graph and
    measures how much structure is preserved.

    Args:
        format_sequence: Comma-separated format sequence (e.g. "graph,table,graph")
        graph_reference_id: Graph ID if starting from graph
        table_json: JSON rows if starting from table
        vector_json: JSON 2D array if starting from vector
        mode_sequence: Comma-separated modes for each step (optional, defaults to "auto")
        embedding_provider: "local", "digimon", or "hash"

    Returns:
        preservation_score: float (0-1), entity_preservation: float,
        edge_preservation: float, warnings: list[str], steps: list[{from, to, mode, shape, time_ms}]
    """
    await _ensure_initialized()

    from Core.AgentTools.cross_modal_tools import (
        _extract_networkx_graph as extract_nx, _graph_to_dict, validate_round_trip,
        get_embedding_provider,
    )
    import numpy as np
    import pandas as pd

    formats = [f.strip() for f in format_sequence.split(",")]
    if len(formats) < 2:
        return json.dumps({"error": "format_sequence must have at least 2 formats"})

    modes = None
    if mode_sequence:
        modes = [m.strip() for m in mode_sequence.split(",")]

    # Resolve starting data
    start_format = formats[0]
    data: Any = None

    if start_format == "graph":
        if not graph_reference_id:
            return json.dumps({"error": "graph_reference_id required when starting from graph"})
        ctx = _state["context"]
        gi = ctx.get_graph_instance(graph_reference_id)
        if gi is None:
            return json.dumps({"error": f"Graph '{graph_reference_id}' not found"})
        nx_graph = extract_nx(gi)
        if nx_graph is None:
            return json.dumps({"error": f"Could not extract NetworkX graph from '{graph_reference_id}'"})
        data = _graph_to_dict(nx_graph)
    elif start_format == "table":
        if not table_json:
            return json.dumps({"error": "table_json required when starting from table"})
        data = pd.DataFrame(json.loads(table_json))
    elif start_format == "vector":
        if not vector_json:
            return json.dumps({"error": "vector_json required when starting from vector"})
        data = np.array(json.loads(vector_json), dtype=np.float32)
    else:
        return json.dumps({"error": f"Unknown starting format: {start_format!r}"})

    provider = None
    provider_error = None
    try:
        provider = get_embedding_provider(embedding_provider, _state)
    except ValueError as e:
        provider_error = str(e)

    try:
        result = await validate_round_trip(data, formats, mode_sequence=modes, provider=provider)
    except ValueError as e:
        if provider_error and "embedding provider" in str(e).lower():
            return json.dumps({"error": f"{e} (provider error: {provider_error})"})
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"validate_conversion: {e}", exc_info=True)
        return json.dumps({"error": str(e)})

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def select_analysis_mode(
    research_question: str,
    dataset_name: str = "",
) -> str:
    """Recommend the best analysis modality (graph, table, vector, or cross-modal) for a research question.

    Uses an LLM to analyze the question type and recommend the optimal data modality
    plus a suggested workflow of DIGIMON tool calls.

    Args:
        research_question: The question to analyze
        dataset_name: Name of the dataset to check available resources

    Returns:
        recommended_mode: str, confidence: float, reasoning: str,
        suggested_steps: list[str]
    """
    await _ensure_initialized()

    from llm_client import render_prompt, acall_llm_structured
    from pydantic import BaseModel, Field

    class AnalysisModeDecision(BaseModel):
        recommended_mode: str = Field(description="One of: graph, table, vector, cross_modal")
        confidence: float = Field(ge=0.0, le=1.0)
        reasoning: str = Field(description="Why this mode fits the question")
        suggested_steps: list[str] = Field(description="2-5 workflow steps")

    # Get available resources for context
    resources = "{}"
    if dataset_name:
        try:
            resources = await list_available_resources()
        except Exception as e:
            logger.warning(f"select_analysis_mode: list_available_resources failed: {e}")

    prompt_path = str(Path(__file__).parent / "prompts" / "select_analysis_mode.yaml")

    try:
        messages = render_prompt(
            prompt_path,
            question=research_question,
            dataset_name=dataset_name or "(not specified)",
            resources=resources,
        )
    except Exception as e:
        logger.error(f"select_analysis_mode: prompt render failed: {e}")
        return json.dumps({"error": f"Prompt render failed: {e}"})

    # Use agentic LLM if available, else fall back to default LLM
    llm = _state.get("agentic_llm")
    model = llm.model if llm else _state["config"].llm.model

    try:
        _sam_trace = f"digimon.select_analysis_mode.{dataset_name or 'none'}.{uuid.uuid4().hex[:8]}"
        decision, meta = await acall_llm_structured(
            model, messages, response_model=AnalysisModeDecision,
            task="digimon.select_analysis_mode",
            trace_id=_sam_trace,
            max_budget=0,
        )
        logger.info(
            f"select_analysis_mode: recommended '{decision.recommended_mode}' "
            f"(confidence={decision.confidence:.2f})"
        )
    except Exception as e:
        logger.error(f"select_analysis_mode: LLM call failed: {e}")
        return json.dumps({"error": f"LLM call failed: {e}"})

    return json.dumps(decision.model_dump(), indent=2)


@mcp.tool()
async def list_modality_conversions() -> str:
    """List all supported cross-modal conversion paths with their modes and descriptions.

    Discovery tool for agents. Shows what conversions are available, which modes
    each supports, and whether embeddings are required.

    Returns:
        list of {source_format, target_format, mode, description, requires_embedding}
    """
    from Core.AgentTools.cross_modal_tools import list_all_conversions
    return json.dumps(list_all_conversions(), indent=2)


# =============================================================================
# BENCHMARK-ONLY: STRUCTURED ANSWER SUBMISSION
# =============================================================================

if BENCHMARK_MODE:
    _ANSWER_REFUSAL_RE = re.compile(
        r"(i can(?:not|'t)|unable to|do not know|don't know|not enough (?:evidence|information)|"
        r"no such|could not find|cannot find|not found|not applicable|unknown|n/?a|"
        r"unclear|cannot determine|can't determine|undetermined)",
        flags=re.IGNORECASE,
    )

    @mcp.tool()
    async def semantic_plan(question: str) -> str:
        """Create a typed semantic plan (atoms, dependencies, composition).

        Use this once at question start to avoid decomposition drift. The output
        is a compact JSON contract for TODO construction and evidence checks.
        """
        global _current_question, _current_expected_answer_kind
        global _current_semantic_plan_question
        await _ensure_initialized()

        from llm_client import acall_llm_structured
        from pydantic import BaseModel, Field
        from typing import Literal

        class PlanAtom(BaseModel):
            atom_id: str = Field(description="Short ID like a1, a2.")
            sub_question: str = Field(description="Atomic sub-question.")
            operation: str = Field(
                description="Operation type: lookup, relation, compose, intersection, compare, temporal."
            )
            answer_kind: Literal["entity", "date", "number", "yes_no"] = Field(
                description="Expected answer type for this atom."
            )
            output_var: str = Field(description="Variable produced by this atom.")
            depends_on: list[str] = Field(default_factory=list, description="Upstream atom IDs.")
            done_criteria: str = Field(description="Evidence requirement to mark this atom done.")

        class SemanticPlan(BaseModel):
            final_answer_kind: Literal["entity", "date", "number", "yes_no"] = Field(
                description="Expected answer type for final answer."
            )
            atoms: list[PlanAtom] = Field(description="2-6 ordered atoms.")
            composition_rule: str = Field(
                description="How atoms combine (e.g., intersection of a1 and a2 then lookup date of a3)."
            )
            uncertainty_points: list[str] = Field(
                default_factory=list,
                description="Potentially ambiguous bridge points that may need branching.",
            )

        def _plan_has_relation_scope_risk(q: str, p: SemanticPlan) -> bool:
            ql = (q or "").lower()
            relation_markers = (" north of ", " south of ", " east of ", " west of ", " before ", " after ")
            if " and " not in ql:
                return False
            if not any(m in ql for m in relation_markers):
                return False
            relation_ids = {
                a.atom_id for a in p.atoms
                if (a.operation or "").strip().lower() == "relation"
            }
            if not relation_ids:
                return False
            for atom in p.atoms:
                op = (atom.operation or "").strip().lower()
                if op not in {"intersection", "compose", "composition"}:
                    continue
                deps = atom.depends_on or []
                if len(deps) < 2:
                    continue
                if any(dep in relation_ids for dep in deps):
                    return True
            return False

        system_prompt = (
            "You are a strict semantic planner for multi-hop QA. "
            "Decompose the question into minimal typed atoms. "
            "Preserve composition operators explicitly (intersection/composition/comparison) "
            "instead of replacing them with nearest named entities. "
            "Never collapse nested clauses. For patterns like 'X where Y is located', "
            "first create an atom for Y's location, then apply X to that result. "
            "For conjunctions ('A and B'), create separate atoms for A and B, then an explicit "
            "intersection/compose atom. For comparatives/uniqueness ('only', 'largest', "
            "'larger than', ordinals), create an explicit compare/rank atom before downstream lookups. "
            "Do not shortcut relation targets (e.g., avoid replacing 'north of region where Israel is located' "
            "with 'north of Israel'). "
            "In sub_question text, use entity/title names exactly as they appear in the original question. "
            "Do not add assumed type qualifiers (song, movie, book, album, etc.) that the question "
            "does not explicitly state — the retrieval system is literal and added qualifiers can "
            "cause false mismatches."
        )
        user_prompt = (
            f"Question: {question}\n\n"
            "Requirements:\n"
            "1) Return 2-6 atoms.\n"
            "2) Each atom must have operation + answer_kind + output_var + dependencies.\n"
            "3) composition_rule must preserve how intermediate variables combine.\n"
            "4) uncertainty_points should call out ambiguous bridge entities if any.\n"
            "5) Preserve hidden intermediate variables implied by nested wording.\n"
            "6) For bridge atoms, done_criteria should mention evidence needed to disambiguate alternatives.\n\n"
            "Mini examples:\n"
            "- 'region north of the region where X is located and location of Y' => "
            "locate region(X), locate region(Y), compose/intersect, then apply north-of relation.\n"
            "- 'headquarters of the only group larger than L' => find L, compare/rank to unique group, "
            "then lookup headquarters.\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        llm = _state.get("agentic_llm")
        model = llm.model if llm else _state["config"].llm.model
        trace_id = f"digimon.semantic_plan.{uuid.uuid4().hex[:8]}"

        # Use deepseek for planning to avoid Gemini rate limits.
        # Planning is cheap (~500 tokens) and deepseek handles structured output well.
        plan_model = "deepseek/deepseek-chat"
        try:
            plan, _meta = await acall_llm_structured(
                plan_model,
                messages,
                response_model=SemanticPlan,
                task="digimon.semantic_plan",
                trace_id=trace_id,
                max_budget=0,
                num_retries=2,
            )

            # Second-pass plan critic/reviser:
            # catches scope/attachment errors in nested clauses before tools run.
            critique_system = (
                "You are a semantic-plan verifier/reviser for multi-hop QA. "
                "Given a question and a draft plan, return a corrected plan in the same schema. "
                "Preserve the same intent while fixing logic/scope mistakes. "
                "You must resolve relation-scope ambiguities explicitly."
            )
            critique_user = (
                f"Question: {question}\n\n"
                f"Draft plan JSON:\n{json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)}\n\n"
                "Validation checklist:\n"
                "1) Clause attachment: ensure relation targets are scoped correctly for nested phrases.\n"
                "2) Conjunction/composition: for 'A and B', keep explicit atoms for A and B plus compose/intersection.\n"
                "3) Comparatives/uniqueness: include explicit compare/rank atom before downstream lookups.\n"
                "4) Dependency validity: each atom should depend on required upstream outputs.\n"
                "5) Answer type: final atom must produce final_answer_kind with explicit evidence-ready done_criteria.\n"
                "6) No shortcut substitutions of relation targets (e.g., replacing a composed target with a nearby entity).\n\n"
                "Scope disambiguation rule:\n"
                "- If a relation phrase ('north of', 'south of', 'east/west of', 'before/after', etc.) is followed by a conjunction scope, "
                "consider BOTH parses and keep the one that preserves full literal scope.\n"
                "- Example pattern: 'R of A and B' should typically become R( intersection(A, B) ) unless punctuation clearly separates clauses.\n"
                "- Do not attach the relation only to A when the text implies it applies to (A and B).\n\n"
                "Before finalizing, run this self-check in your head:\n"
                "A) relation applied to first conjunct only\n"
                "B) relation applied to composed conjunct target\n"
                "Return the plan that best matches literal wording, then ensure atom dependencies encode that choice.\n\n"
                "Return only the corrected plan. If draft is already correct, return it unchanged."
            )
            critique_messages = [
                {"role": "system", "content": critique_system},
                {"role": "user", "content": critique_user},
            ]

            revised_trace_id = f"digimon.semantic_plan.revise.{uuid.uuid4().hex[:8]}"
            try:
                revised_plan, _rev_meta = await acall_llm_structured(
                    model,
                    critique_messages,
                    response_model=SemanticPlan,
                    task="digimon.semantic_plan.revise",
                    trace_id=revised_trace_id,
                    max_budget=0,
                )
                plan = revised_plan
            except Exception as revise_err:
                logger.warning("semantic_plan revise pass failed; using draft plan. err=%s", revise_err)

            if _plan_has_relation_scope_risk(question, plan):
                repair_system = (
                    "You repair relation-scope attachment in multi-hop semantic plans. "
                    "When a relation is attached before a conjunction/intersection target, "
                    "rewrite the plan so composition target is formed first, then relation applies "
                    "to that composed target if that best matches literal question scope."
                )
                repair_user = (
                    f"Question: {question}\n\n"
                    f"Current plan JSON:\n{json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)}\n\n"
                    "Potential issue: relation appears attached to a partial target before conjunction/intersection. "
                    "Evaluate whether relation should apply to the composed target instead.\n"
                    "Return corrected plan in the same schema."
                )
                repair_messages = [
                    {"role": "system", "content": repair_system},
                    {"role": "user", "content": repair_user},
                ]
                repair_trace_id = f"digimon.semantic_plan.scope_repair.{uuid.uuid4().hex[:8]}"
                try:
                    repaired_plan, _repair_meta = await acall_llm_structured(
                        model,
                        repair_messages,
                        response_model=SemanticPlan,
                        task="digimon.semantic_plan.scope_repair",
                        trace_id=repair_trace_id,
                        max_budget=0,
                    )
                    plan = repaired_plan
                except Exception as repair_err:
                    logger.warning("semantic_plan scope-repair pass failed; using prior plan. err=%s", repair_err)

            # Preserve ambiguity signal explicitly so the agent can branch only
            # when needed instead of committing too early to one attachment parse.
            relation_scope_risk = _plan_has_relation_scope_risk(question, plan)
            if relation_scope_risk:
                ambiguity_hint = (
                    "Relation-attachment ambiguity: test both parses before committing: "
                    "(A) R(intersection(X, Y)) and (B) intersection(R(X), Y). "
                    "Use downstream evidence to pick one."
                )
                if ambiguity_hint not in plan.uncertainty_points:
                    plan.uncertainty_points.append(ambiguity_hint)

            # Safety alignment: if the question clearly asks for date/number/yes_no
            # but planner returned entity, coerce final/sink atom kinds to avoid
            # deterministic wrong-answer-type failures.
            inferred_kind = _infer_answer_kind(question)
            planned_kind = _normalize_answer_kind(plan.final_answer_kind)
            if inferred_kind and inferred_kind != "entity" and planned_kind != inferred_kind:
                logger.warning(
                    "semantic_plan answer-kind correction: planned=%s inferred=%s question=%r",
                    planned_kind or "entity",
                    inferred_kind,
                    (question or "")[:160],
                )
                plan.final_answer_kind = inferred_kind

                # Prefer rewriting sink atoms (not depended on by others) since they
                # are closest to final answer production.
                dependent_ids = {
                    dep_id
                    for atom in plan.atoms
                    for dep_id in (atom.depends_on or [])
                }
                sink_atoms = [atom for atom in plan.atoms if atom.atom_id not in dependent_ids]
                target_atoms = sink_atoms or (plan.atoms[-1:] if plan.atoms else [])
                for atom in target_atoms:
                    atom.answer_kind = inferred_kind

            _current_semantic_plan.clear()
            _current_semantic_plan.update(plan.model_dump())
            _current_semantic_plan_question = (question or "").strip()
            _current_question = _current_semantic_plan_question
            _current_expected_answer_kind = (
                _normalize_answer_kind(plan.final_answer_kind)
                or _infer_answer_kind(_current_question)
            )
            # Auto-populate TODO list from plan atoms so the agent gets
            # status reminders even if it doesn't call todo_write itself.
            _todos.clear()
            for atom in plan.atoms:
                status = "in_progress" if atom.atom_id == plan.atoms[0].atom_id else "pending"
                _todos.append({
                    "id": atom.atom_id,
                    "content": atom.sub_question,
                    "status": status,
                })
            return json.dumps(plan.model_dump(), indent=2)
        except Exception as e:
            # Deterministic fallback keeps behavior safe if planner LLM is unavailable.
            fallback_kind = _infer_answer_kind(question)
            fallback = {
                "final_answer_kind": fallback_kind,
                "atoms": [
                    {
                        "atom_id": "a1",
                        "sub_question": question,
                        "operation": "lookup",
                        "answer_kind": fallback_kind,
                        "output_var": "answer",
                        "depends_on": [],
                        "done_criteria": (
                            f"Find one evidence-backed {fallback_kind} span."
                            if fallback_kind else
                            "Find one evidence-backed answer span."
                        ),
                    }
                ],
                "composition_rule": "single-hop lookup fallback",
                "uncertainty_points": [],
                "fallback_reason": str(e)[:240],
            }
            _current_semantic_plan.clear()
            _current_semantic_plan.update(fallback)
            _current_semantic_plan_question = (question or "").strip()
            _current_question = _current_semantic_plan_question
            _current_expected_answer_kind = (
                _normalize_answer_kind(fallback.get("final_answer_kind", ""))
                or _infer_answer_kind(_current_question)
            )
            return json.dumps(fallback, indent=2)

    @mcp.tool()
    async def bridge_disambiguate(
        question: str,
        downstream_clue: str,
        candidate_a: str,
        evidence_a: str,
        candidate_b: str,
        evidence_b: str,
        candidate_c: str = "",
        evidence_c: str = "",
    ) -> str:
        """Resolve ambiguous bridge entities using downstream evidence.

        Call this when multiple candidate bridge entities are plausible.
        Provide each candidate with its supporting evidence snippets, then
        this tool selects the best-supported candidate for the downstream clue.

        Args:
            question: Original user question.
            downstream_clue: Relation to verify (e.g., "signed by Barcelona").
            candidate_a: Candidate entity A.
            evidence_a: Evidence text for candidate A.
            candidate_b: Candidate entity B.
            evidence_b: Evidence text for candidate B.
            candidate_c: Optional third candidate entity.
            evidence_c: Optional evidence text for candidate C.

        Returns:
            JSON with winner, confidence, rationale, ranked candidates, and scores.
        """
        await _ensure_initialized()

        from llm_client import acall_llm_structured
        from pydantic import BaseModel, Field

        class BridgeDecision(BaseModel):
            winner: str = Field(description="Selected best candidate entity")
            confidence: float = Field(ge=0.0, le=1.0)
            rationale: str = Field(description="Short evidence-grounded explanation")
            ranked_candidates: list[str] = Field(description="Candidates best to worst")
            evidence_scores: dict[str, float] = Field(
                description="Per-candidate support score between 0 and 1"
            )

        candidates: list[dict[str, str]] = []
        for cand, ev in (
            (candidate_a, evidence_a),
            (candidate_b, evidence_b),
            (candidate_c, evidence_c),
        ):
            c = (cand or "").strip()
            e = (ev or "").strip()
            if c:
                candidates.append({"candidate": c, "evidence": e})

        if len(candidates) < 2:
            raise ValueError("Provide at least two non-empty candidates to disambiguate.")

        candidates_json = json.dumps(candidates, ensure_ascii=False)
        system_prompt = (
            "You are a strict evidence judge for bridge-entity disambiguation. "
            "Pick the candidate with the strongest direct support for the downstream clue. "
            "Prefer explicit evidence over weak association. Penalize contradictions, "
            "missing links, and guesses."
        )
        user_prompt = (
            f"Question: {question}\n"
            f"Downstream clue: {downstream_clue}\n"
            f"Candidates with evidence JSON:\n{candidates_json}\n\n"
            "Scoring rubric (0-1 per candidate):\n"
            "1) Direct downstream match strength\n"
            "2) Specific factual support (dates/names/relations)\n"
            "3) Contradiction penalty\n"
            "Return winner + ranked list + scores."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        llm = _state.get("agentic_llm")
        model = llm.model if llm else _state["config"].llm.model
        trace_id = f"digimon.bridge_disambiguate.{uuid.uuid4().hex[:8]}"

        try:
            decision, _meta = await acall_llm_structured(
                model,
                messages,
                response_model=BridgeDecision,
                task="digimon.bridge_disambiguate",
                trace_id=trace_id,
                max_budget=0,
            )
            # Ensure winner is one of provided candidates
            candidate_names = [c["candidate"] for c in candidates]
            if decision.winner not in candidate_names:
                decision.winner = candidate_names[0]
            return json.dumps(decision.model_dump(), indent=2)
        except Exception as e:
            # Fallback heuristic for robustness if inner LLM is unavailable
            clue_tokens = {t for t in re.findall(r"[a-z0-9]+", downstream_clue.lower()) if len(t) > 2}
            month_re = re.compile(
                r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
                flags=re.IGNORECASE,
            )
            year_re = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")

            scored: list[tuple[str, float]] = []
            for item in candidates:
                cand = item["candidate"]
                ev = (item["evidence"] or "").lower()
                ev_tokens = set(re.findall(r"[a-z0-9]+", ev))
                overlap = 0.0
                if clue_tokens:
                    overlap = len(clue_tokens.intersection(ev_tokens)) / len(clue_tokens)
                specificity = 0.15 if (month_re.search(ev) or year_re.search(ev)) else 0.0
                mention = 0.1 if cand.lower() in ev else 0.0
                score = min(1.0, overlap + specificity + mention)
                scored.append((cand, score))

            scored.sort(key=lambda x: x[1], reverse=True)
            winner = scored[0][0]
            result = {
                "winner": winner,
                "confidence": max(0.35, min(0.8, scored[0][1])),
                "rationale": (
                    "Fallback scorer selected the candidate with strongest downstream clue token overlap "
                    "and specific evidence markers."
                ),
                "ranked_candidates": [name for name, _ in scored],
                "evidence_scores": {name: round(score, 3) for name, score in scored},
                "fallback_reason": str(e)[:300],
            }
            return json.dumps(result, indent=2)

    @mcp.tool()
    async def todo_write(todos: list[dict[str, Any]]) -> str:
        """Replace the full TODO list. Each item must have id, content, and status.

        This is the only TODO management tool. Call it to set or update your
        plan. Pass the complete list every time — it replaces the previous state.
        When an atom is resolved, include its short answer in `answer` or
        `result` so later atoms can reuse it. Done atoms must be dependency-ready
        and supported by cached evidence; unsupported manual closures are rejected.

        Args:
            todos: List of TODO items. Each dict must contain:
                - id: Short identifier (e.g., "a1", "a2")
                - content: What this step needs to accomplish
                - status: One of "pending", "in_progress", "done", "blocked"
              Optional fields preserved for downstream atom execution:
                - answer/result/resolved_value/value: short resolved value
                - evidence_refs: chunk IDs or other evidence handles

        Returns:
            Confirmation with summary counts and compact status line.
        """
        if not isinstance(todos, list):
            raise ValueError("todos must be a list of dicts with id/content/status.")
        validated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        valid_statuses = {"pending", "in_progress", "done", "blocked"}
        status_aliases = {
            "started": "in_progress", "ongoing": "in_progress", "active": "in_progress",
            "complete": "done", "completed": "done", "resolved": "done",
            "incomplete": "pending", "waiting": "pending", "not_started": "pending",
        }
        for item in todos:
            if not isinstance(item, dict):
                raise ValueError(f"Each TODO must be a dict, got {type(item).__name__}.")
            tid = str(item.get("id") or item.get("atom_id") or "").strip()
            content = str(
                item.get("content") or item.get("task") or item.get("sub_question")
                or item.get("done_criteria") or item.get("result") or ""
            ).strip()
            status = str(item.get("status") or "pending").strip().lower()
            status = status_aliases.get(status, status)
            if not tid:
                raise ValueError("Each TODO must have a non-empty 'id'. Use 'id' or 'atom_id' key.")
            if not content:
                raise ValueError(f"TODO '{tid}' must have non-empty 'content'.")
            if status not in valid_statuses:
                raise ValueError(
                    f"TODO '{tid}' has invalid status '{status}'. "
                    f"Must be one of: {', '.join(sorted(valid_statuses))}."
                )
            if tid in seen_ids:
                raise ValueError(f"Duplicate TODO id: '{tid}'.")
            seen_ids.add(tid)
            normalized_item = {"id": tid, "content": content, "status": status}
            for extra_key in ("answer", "result", "resolved_value", "value", "output", "evidence_refs"):
                extra_value = item.get(extra_key)
                if extra_value is None:
                    continue
                normalized_item[extra_key] = extra_value
            atom = _semantic_plan_atom_by_id(tid)
            previous_todo = _todo_item_by_id(tid)
            if atom is not None and status == "done":
                normalized_item = await _validate_manual_todo_completion(
                    atom,
                    normalized_item,
                    previous_todo=previous_todo,
                )
            validated.append(normalized_item)
        _todos.clear()
        _todos.extend(validated)
        status_line = _todo_status_line()
        return json.dumps(
            {
                "status": "ok",
                "summary": _todo_summary(),
                "status_line": status_line,
            }
        )

    @mcp.tool()
    async def submit_answer(reasoning: str = "", answer: str = "") -> str:
        """Submit your final answer. Call once with your best answer.

        Args:
            reasoning: Why this is the correct answer. Reference the specific source text
                      and explain how it answers the question.
            answer: The precise answer to the question. Just the fact, no explanation.
                   For yes/no questions: "yes" or "no".

        Returns:
            Confirmation with submitted answer.
        """
        normalized_answer = (answer or "").strip()
        normalized_reasoning = (reasoning or "").strip()

        if not normalized_answer:
            raise ValueError(
                "Answer cannot be empty. Submit your best factual guess as a short span.",
            )
        if "\n" in normalized_answer or len(normalized_answer.split()) > 25:
            raise ValueError(
                "Answer is too long. Submit a concise factual answer (name/date/number/short phrase).",
            )
        if _ANSWER_REFUSAL_RE.search(normalized_answer):
            raise ValueError(
                "Refusal-style answers are not allowed. Submit your best factual guess.",
            )
        lowered_answer = normalized_answer.lower()
        if lowered_answer.startswith("not "):
            raise ValueError(
                "Negative/abstaining answers are not allowed. Submit a factual guess (name/date/number).",
            )
        if lowered_answer.startswith("no ") and lowered_answer != "no":
            raise ValueError(
                "Abstaining answers are not allowed. Submit a factual guess (name/date/number).",
            )

        # Answer-kind validation removed — semantic_plan's answer_kind prediction
        # is frequently wrong (e.g. "date" for count questions), and every false
        # rejection causes 70+ retry loops that burn budget. The LLM judge handles
        # format-agnostic scoring. Only empty/refusal checks above are kept.

        if not normalized_reasoning:
            raise ValueError(
                "Reasoning cannot be empty. Provide a concise evidence-grounded justification.",
            )

        pending_ids = _pending_todo_ids_for_submit()
        if pending_ids:
            raise ValueError(
                f"Cannot submit: {len(pending_ids)} todo atoms still pending: {pending_ids}. "
                "Complete all atoms before submitting. Use todo_write to mark them done with evidence.",
            )

        _reset_chunk_dedup()  # reset seen chunks for next question
        return json.dumps(
            {
                "status": "submitted",
                "answer": normalized_answer,
                "expected_answer_kind": _current_expected_answer_kind or None,
            }
        )


# =============================================================================
# PROGRESSIVE DISCLOSURE: search tool
# =============================================================================

@mcp.tool()
async def search_available_tools(query: str, top_k: int = 5) -> str:
    """Search for DIGIMON tools by keyword or capability.

    Use this when you need a tool that isn't in your current visible set.
    Returns matching tool names with descriptions and input schemas.
    In non-disclosure mode, returns a note that all tools are already loaded.

    Args:
        query: Free-text search (e.g. 'vector database', 'entity_vdb', 'chunk text')
        top_k: Maximum number of results to return (default 5)

    Returns:
        JSON list of matching tools with name, description, and parameters.
    """
    if not PROGRESSIVE_DISCLOSURE or len(_deferred_registry) == 0:
        return json.dumps({
            "note": "All tools are already loaded. Use list_operators for operator discovery.",
            "results": [],
        })
    results = search_available_tools_impl(query, _deferred_registry, top_k=top_k)
    return json.dumps({
        "results": results,
        "total_deferred_tools": len(_deferred_registry),
    }, indent=2)


# =============================================================================
# PROGRAMMATIC TOOL CALLING: execute_operator_chain
# =============================================================================

@mcp.tool()
async def execute_operator_chain(code: str) -> str:
    """Execute Python code that calls DIGIMON operators as async functions.

    Write Python code using `await operator_name(...)` to chain operators.
    Intermediate results stay in local variables -- only the final print()
    output is returned. This is much more token-efficient than calling
    operators one at a time.

    Available operators (all async, all return Python dicts — no json.loads needed):
    - entity_vdb_search(query_text, top_k=5)
    - entity_onehop(entity_ids, graph_reference_id)
    - entity_ppr(graph_reference_id, seed_entity_ids, damping=0.85)
    - entity_link(entity_names, dataset_name)
    - entity_tfidf(candidate_entity_ids, query_text)
    - entity_resolve_names_to_ids(entity_names, dataset_name)
    - entity_profile(entity_id, dataset_name)
    - entity_select_candidate(candidate_entity_ids, ...)
    - entity_string_search(query_text, dataset_name)
    - entity_neighborhood(entity_name, dataset_name)
    - relationship_onehop(entity_ids, graph_reference_id)
    - relationship_score_aggregator(entity_scores, graph_reference_id)
    - relationship_vdb_search(vdb_reference_id, query_text)
    - chunk_from_relationships(target_relationships, dataset_name)
    - chunk_occurrence(entity_names, dataset_name)
    - chunk_get_text_by_chunk_ids(chunk_ids, dataset_name)
    - chunk_get_text_by_entity_ids(entity_ids, dataset_name)
    - chunk_text_search(query_text, dataset_name)
    - chunk_vdb_search(query_text, dataset_name)
    - chunk_aggregator(relationship_scores, graph_reference_id)
    - search_then_expand_onehop(query_text, dataset_name)
    - extract_date_mentions(entity_names, dataset_name)
    - meta_generate_answer(query_text, context_chunks)
    - meta_extract_entities(query_text)
    - meta_decompose_question(query_text)
    - meta_synthesize_answers(query_text, sub_answers)
    - meta_pcst_optimize(entity_ids, entity_scores, ...)
    - subgraph_khop_paths(graph_reference_id, source_entity_id, target_entity_id)
    - subgraph_steiner_tree(graph_reference_id, entity_ids)
    - list_available_resources()
    - list_operators()
    - get_compatible_successors(operator_id)

    Example:
        entities = json.loads(await entity_vdb_search(query_text="Shield AI"))
        names = [e["entity_name"] for e in entities["similar_entities"][:5]]
        rels = json.loads(await relationship_onehop(
            entity_ids=names, graph_reference_id=""))
        chunks = json.loads(await chunk_occurrence(
            entity_names=names, dataset_name=""))
        answer = await meta_generate_answer(
            query_text="What contracts does Shield AI have?",
            context_chunks=[c["text_content"] for c in json.loads(chunks).get("chunks", [])]
        )
        print(answer)

    Args:
        code: Python code to execute. Use `await` for operator calls, `print()` for output.

    Returns:
        Captured stdout from print() calls. On error, returns the traceback text.
    """
    import io
    import traceback

    # Build namespace with all operator callables
    namespace = _build_operator_chain_namespace()

    # Capture stdout
    captured = io.StringIO()

    # Wrap user code in an async function so `await` works
    indented_code = "\n".join("    " + line for line in code.splitlines())
    wrapped = f"async def _ptc_main():\n{indented_code}\n"

    try:
        exec(compile(wrapped, "<execute_operator_chain>", "exec"), namespace)
        main_fn = namespace["_ptc_main"]

        # Redirect print to our capture buffer
        original_print = namespace.get("print", print)

        def captured_print(*args: object, **kwargs: object) -> None:
            """Print to capture buffer instead of stdout."""
            kwargs["file"] = captured  # type: ignore[assignment]
            original_print(*args, **kwargs)

        namespace["print"] = captured_print

        # Re-exec with captured print so the function closes over the right print
        exec(compile(wrapped, "<execute_operator_chain>", "exec"), namespace)
        main_fn = namespace["_ptc_main"]

        await main_fn()
    except Exception:
        captured.write(traceback.format_exc())

    result = captured.getvalue()
    return result if result else "(no output — did you forget to print()?)"


def _build_operator_chain_namespace() -> dict[str, Any]:
    """Build the exec namespace for execute_operator_chain.

    Collects all retrieval/query operator functions defined in this module
    and makes them available alongside json and other safe builtins.

    Returns:
        Dict mapping function names to their async callables, plus safe builtins.
    """
    # All operator functions that should be available in PTC code.
    # These are the same functions used by _init_direct_tools in the benchmark runner.
    _ptc_operators: list[str] = [
        "entity_vdb_search",
        "entity_string_search",
        "entity_neighborhood",
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
        "chunk_text_search",
        "chunk_vdb_search",
        "search_then_expand_onehop",
        "chunk_aggregator",
        "list_available_resources",
        "subgraph_khop_paths",
        "subgraph_steiner_tree",
        "meta_pcst_optimize",
        "meta_extract_entities",
        "meta_generate_answer",
        "meta_decompose_question",
        "meta_synthesize_answers",
        "list_operators",
        "get_compatible_successors",
    ]

    namespace: dict[str, Any] = {"json": json, "__builtins__": {}}

    # Add safe builtins
    import builtins
    safe_builtins = [
        "print", "len", "range", "enumerate", "zip", "map", "filter",
        "sorted", "reversed", "list", "dict", "set", "tuple", "str",
        "int", "float", "bool", "isinstance", "type", "hasattr", "getattr",
        "min", "max", "sum", "any", "all", "abs", "round",
        "ValueError", "TypeError", "KeyError", "IndexError", "Exception",
    ]
    for name in safe_builtins:
        obj = getattr(builtins, name, None)
        if obj is not None:
            namespace["__builtins__"][name] = obj  # type: ignore[index]

    # Bind operator functions from this module's globals.
    # Wrap each to auto-parse JSON results → Python dicts, so the agent
    # doesn't have to json.loads() every intermediate. This is the #1
    # source of PTC code errors.
    module_globals = globals()

    def _make_auto_parse_wrapper(fn: Any) -> Any:
        """Wrap an operator function to auto-parse JSON string results."""
        import functools

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            if isinstance(result, str):
                try:
                    return json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    return result  # Return raw string if not valid JSON
            return result

        return wrapper

    for op_name in _ptc_operators:
        fn = module_globals.get(op_name)
        if fn is not None and callable(fn):
            namespace[op_name] = _make_auto_parse_wrapper(fn)

    return namespace


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    if BENCHMARK_MODE:
        (
            visible_tool_names,
            applicability_label,
            unavailable_tool_names,
            degraded_tool_names,
        ) = asyncio.run(_benchmark_visible_mcp_tool_names_for_current_env())
        mode_name = os.environ.get("DIGIMON_BENCHMARK_MODE_NAME", "").strip()
        visible_tool_names_set = set(visible_tool_names)
        for tool_name in tuple(mcp._tool_manager._tools.keys()):
            if tool_name not in visible_tool_names_set:
                mcp.remove_tool(tool_name)
        _compact_tool_schemas()
        n_remaining = len(mcp._tool_manager._tools)
        print(
            f"Benchmark mode level {BENCHMARK_MODE}: {n_remaining} tools (compact schemas)",
            file=sys.stderr,
        )
        if mode_name:
            print(
                f"Benchmark mode profile {mode_name}: {len(visible_tool_names)} tools after mode filter",
                file=sys.stderr,
            )
        if applicability_label is not None:
            print(
                "Benchmark applicability "
                f"{applicability_label}: removed {len(unavailable_tool_names)} unavailable tools"
                + (
                    f", retained {len(degraded_tool_names)} degraded tools"
                    if degraded_tool_names
                    else ""
                ),
                file=sys.stderr,
            )
        if degraded_tool_names:
            print(
                "Benchmark applicability degraded tools retained: "
                + ", ".join(sorted(degraded_tool_names)),
                file=sys.stderr,
            )

    # Progressive disclosure: remove deferred tools and store their metadata
    # in _deferred_registry so search_available_tools can find them.
    if PROGRESSIVE_DISCLOSURE:
        deferred_count = 0
        for tool_name in tuple(mcp._tool_manager._tools.keys()):
            if should_defer_tool(tool_name):
                tool_obj = mcp._tool_manager._tools[tool_name]
                _deferred_registry.register(
                    name=tool_name,
                    description=tool_obj.description or "",
                    parameters=tool_obj.parameters if isinstance(tool_obj.parameters, dict) else {},
                )
                mcp.remove_tool(tool_name)
                deferred_count += 1
        n_visible = len(mcp._tool_manager._tools)
        print(
            f"Progressive disclosure: {n_visible} tools visible, "
            f"{deferred_count} deferred (searchable via search_available_tools)",
            file=sys.stderr,
        )

    mcp.run(transport="stdio")
