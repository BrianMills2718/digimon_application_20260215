#!/usr/bin/env python3
"""
DIGIMON MCP Server (stdio) for Claude Code

Exposes DIGIMON's KG-RAG tools via the official MCP protocol (stdio transport).
This allows Claude Code to act as the agent, calling tools directly.

Usage:
    python digimon_mcp_stdio_server.py

Add to ~/.claude/mcp_servers.json to use with Claude Code.
"""

import json
import logging
import os
import pickle
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

logger = logging.getLogger(__name__)

# Benchmark mode levels:
#   0 / unset: all tools exposed (including build, pipeline shortcuts, etc.)
#   1+: prune non-retrieval tools (graph build, corpus_prepare, graph_analyze,
#        auto_compose, execute_method, list_methods, build_sparse_matrices, etc.)
#        — agent must compose operators individually
_bm_raw = os.environ.get("DIGIMON_BENCHMARK_MODE", "").strip().lower()
if _bm_raw in ("1", "2", "true", "yes"):
    BENCHMARK_MODE = 1
else:
    BENCHMARK_MODE = 0

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
}

# Short descriptions for benchmark mode — the system prompt already explains
# tool usage in detail, so verbose docstrings in the schema are redundant tokens.
_BENCHMARK_SHORT_DESCS: dict[str, str] = {
    "entity_vdb_search": "Semantic vector search over entities.",
    "entity_onehop": "Get all neighbor entities of a given entity.",
    "entity_ppr": "Personalized PageRank from seed entities.",
    "entity_link": "Match entity names to graph nodes.",
    "entity_tfidf": "Find entities by TF-IDF keyword matching.",
    "relationship_onehop": "Get typed relationships for an entity.",
    "relationship_score_aggregator": "Aggregate entity scores into relationship scores.",
    "relationship_vdb_search": "Semantic vector search over relationships.",
    "chunk_from_relationships": "Get text chunks for given relationships.",
    "chunk_occurrence": "Find chunks where two entities co-occur.",
    "chunk_get_text": "Get source text for given entities.",
    "chunk_text_search": "Keyword search over source text chunks.",
    "chunk_aggregator": "Score chunks by relationship/PPR scores via sparse matrices.",
    "subgraph_khop_paths": "Find all paths between entities within k hops.",
    "subgraph_steiner_tree": "Minimal subgraph connecting a set of entities.",
    "meta_pcst_optimize": "Prize-collecting Steiner tree optimization (algorithmic).",
    "list_available_resources": "List loaded graphs, VDBs, and sparse matrices.",
    "submit_answer": "Submit your final answer. Call once with your best answer.",
}


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


# --- Initialize MCP Server ---
mcp = FastMCP("digimon-kgrag", instructions="""
DIGIMON KG-RAG Tools: Build knowledge graphs from documents and query them.

## Core: 26 Typed Operators

DIGIMON's core value is 26 composable operators across 6 categories:
entity (7), relationship (4), chunk (3), subgraph (3), community (2), meta (7).
Each operator has typed I/O slots, cost tiers, and prerequisite flags.
Call `list_operators` for the full catalog, `get_compatible_successors` to explore chains.

## Three Execution Modes

### Mode 1: Individual Operators (client composes)
Call operators directly for custom pipelines. Use `list_operators` +
`get_compatible_successors` to discover valid chains. Typical flow:
corpus_prepare → graph_build_er → entity_vdb_build → entity_vdb_search →
relationship_onehop → chunk_occurrence → meta_generate_answer

### Mode 2: Reference Pipelines (10 pre-composed shortcuts)
Call `list_methods` to see profiles, then `execute_method` to run end-to-end.
Pass `auto_build=True` to auto-build missing prerequisites.

### Mode 3: Full Auto (auto_compose)
`auto_compose(query, dataset, auto_build=True)` — an LLM picks the best
method based on query characteristics and available resources.

## Config

Two model roles: `llm.model` (graph building, cheap) vs `agentic_model`
(mid-pipeline reasoning — entity extraction, answer generation, iterative steps).
- `get_config` — inspect current models, paths
- `set_agentic_model` — override the reasoning model at runtime

## Graph Types (call list_graph_types for details)
- **er**: General-purpose entity-relationship graph. Works with all methods.
- **rk**: Keyword-enriched relationships. Best for LightRAG.
- **tree/tree_balanced**: Hierarchical clustering. Best for summarization.
- **passage**: Passage-level nodes. Best for document-centric retrieval.

## Cross-Modal Analysis
Convert between graph, table, and vector representations:
- `list_modality_conversions` — discover all 15 conversion paths
- `convert_modality` — convert data between modalities (graph/table/vector)
- `validate_conversion` — measure round-trip preservation quality
- `select_analysis_mode` — LLM recommends best modality for a research question

## Tips
- Use `return_context_only=True` in execute_method when you want to synthesize
  the answer yourself instead of letting DIGIMON's LLM generate it.
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


async def _ensure_initialized():
    """Lazy initialization of DIGIMON components."""
    if "initialized" in _state:
        return

    project_root = _get_project_root()
    os.chdir(project_root)

    from Option.Config2 import Config
    from Core.Provider.LLMClientAdapter import LLMClientAdapter
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentSchema.context import GraphRAGContext

    config_path = os.path.join(project_root, "Option", "Config2.yaml")
    config = Config.from_yaml_file(config_path)

    fallback = getattr(config.llm, 'fallback_models', None) or []
    llm = LLMClientAdapter(
        config.llm.model,
        fallback_models=fallback,
        num_retries=3,
    )
    encoder = get_rag_embedding(config=config)
    chunk_factory = ChunkFactory(config)

    context = GraphRAGContext(
        target_dataset_name="mcp_session",
        main_config=config,
        llm_provider=llm,
        embedding_provider=encoder,
        chunk_storage_manager=chunk_factory,
    )

    _state["config"] = config
    _state["llm"] = llm
    _state["encoder"] = encoder
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

            # Load VDBs from disk if they exist, rebuild only if needed
            from Core.Index.FaissIndex import FaissIndex
            from Core.AgentTools.index_config_helper import create_faiss_index_config

            for vdb_id in [vdb_name, f"{preload_dataset}_chunks"]:
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
                            context.add_vdb_instance(vdb_id, vdb)
                            logger.info(f"Pre-loaded VDB from disk: {vdb_id}")
                            continue
                    except Exception as ve:
                        logger.warning(f"VDB disk load failed for {vdb_id}: {ve}")

                # Rebuild if disk load failed or didn't exist
                if "entities" in vdb_id:
                    await entity_vdb_build(graph_id, vdb_id)
                elif "chunks" in vdb_id:
                    await chunk_vdb_build(preload_dataset)

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


def _dedup_chunk(chunk_id: str, text: str) -> tuple[bool, str]:
    """Track a chunk. Returns (is_new, text_or_reference).

    If the chunk was already returned in this session, returns a short reference
    instead of the full text so the agent knows it exists but doesn't waste
    context window on repeated content.
    """
    if chunk_id in _seen_chunks:
        preview = _seen_chunks[chunk_id]
        return False, f"[already in context: {preview!r}...]"
    _seen_chunks[chunk_id] = text[:80]
    return True, text


def _reset_chunk_dedup() -> None:
    """Reset seen chunks — call between questions."""
    _seen_chunks.clear()


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
        # Set namespace so chunk lookups work
        if hasattr(graph_instance, "_graph") and hasattr(graph_instance._graph, "namespace"):
            dataset_name = result.graph_id
            for suffix in ["_ERGraph", "_RKGraph", "_TreeGraphBalanced", "_TreeGraph", "_PassageGraph"]:
                if dataset_name.endswith(suffix):
                    dataset_name = dataset_name[: -len(suffix)]
                    break
            graph_instance._graph.namespace = _state["chunk_factory"].get_namespace(dataset_name)

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
async def entity_vdb_search(vdb_reference_id: str, query_text: str,
                            top_k: int = 5) -> str:
    """Search for entities similar to a query using vector similarity.

    Args:
        vdb_reference_id: ID of the entity VDB to search
        query_text: Natural language search query
        top_k: Number of results to return

    Returns:
        similar_entities: list of {entity_name: str, score: float, node_id: str}
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_tools import entity_vdb_search_tool
    from Core.AgentSchema.tool_contracts import EntityVDBSearchInputs

    inputs = EntityVDBSearchInputs(
        vdb_reference_id=vdb_reference_id,
        query_text=query_text,
        top_k_results=top_k,
    )
    result = await entity_vdb_search_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def entity_onehop(entity_ids: list[str], graph_reference_id: str) -> str:
    """Find one-hop neighbor entities in the graph.

    Args:
        entity_ids: List of entity IDs to find neighbors for
        graph_reference_id: ID of the graph to search

    Returns:
        neighbors: {entity_id: [{...}]}, total_neighbors_found: int, message: str
    """
    await _ensure_initialized()
    from Core.AgentTools.entity_onehop_tools import entity_onehop_neighbors_tool

    inputs = {
        "entity_ids": entity_ids,
        "graph_reference_id": graph_reference_id,
    }
    result = await entity_onehop_neighbors_tool(inputs, _state["context"])
    return _format_result(result)


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
async def entity_link(source_entities: list[str], vdb_reference_id: str,
                      similarity_threshold: float = 0.5) -> str:
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

    inputs = EntityLinkInputs(
        source_entities=source_entities,
        knowledge_base_reference_id=vdb_reference_id,
        similarity_threshold=similarity_threshold,
    )
    result = await entity_link_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def entity_tfidf(candidate_entity_ids: list[str], query_text: str,
                       graph_reference_id: str, top_k: int = 10) -> str:
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

    inputs = EntityTFIDFInputs(
        candidate_entity_ids=candidate_entity_ids,
        query_text=query_text,
        graph_reference_id=graph_reference_id,
        top_k=top_k,
    )
    result = await entity_tfidf_tool(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# RELATIONSHIP TOOLS
# =============================================================================

@mcp.tool()
async def relationship_onehop(entity_ids: list[str], graph_reference_id: str) -> str:
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

    inputs = RelationshipOneHopNeighborsInputs(
        entity_ids=entity_ids,
        graph_reference_id=graph_reference_id,
    )
    result = await relationship_one_hop_neighbors_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def relationship_score_aggregator(
    entity_scores: dict, graph_reference_id: str,
    top_k: int = 10, aggregation_method: str = "sum"
) -> str:
    """Aggregate entity scores (e.g. from PPR) onto relationships and return top-k.

    Args:
        entity_scores: Dict mapping entity_id to score
        graph_reference_id: ID of the graph
        top_k: Number of top relationships to return
        aggregation_method: How to combine scores: 'sum', 'average', or 'max'

    Returns:
        scored_relationships: list of [{relationship_id: str, source_node_id: str, target_node_id: str, type: str}, score: float]
    """
    await _ensure_initialized()
    from Core.AgentTools.relationship_tools import relationship_score_aggregator_tool
    from Core.AgentSchema.tool_contracts import RelationshipScoreAggregatorInputs

    inputs = RelationshipScoreAggregatorInputs(
        entity_scores=entity_scores,
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
                                    document_collection_id: str,
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

    input_data = {
        "target_relationships": target_relationships,
        "document_collection_id": document_collection_id,
        "top_k_total": top_k,
    }
    result = await chunk_from_relationships_tool(input_data, _state["context"])
    return _format_result(result)


@mcp.tool()
async def chunk_occurrence(target_entity_pairs: list[dict],
                           document_collection_id: str,
                           top_k: int = 5) -> str:
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

    inputs = ChunkOccurrenceInputs(
        target_entity_pairs_in_relationship=target_entity_pairs,
        document_collection_id=document_collection_id,
        top_k_chunks=top_k,
    )
    result = await chunk_occurrence_tool(inputs, _state["context"])
    return _format_result(result)


@mcp.tool()
async def chunk_get_text(graph_reference_id: str, entity_ids: list[str],
                         max_chunks_per_entity: int = 5) -> str:
    """Get source text chunks associated with specific entities.

    Args:
        graph_reference_id: ID of the graph containing the entities
        entity_ids: List of entity names/IDs to get text for
        max_chunks_per_entity: Max chunks per entity

    Returns:
        retrieved_chunks: list of {entity_id?: str, chunk_id: str, text_content: str}, status_message: str
    """
    await _ensure_initialized()
    from Core.AgentTools.chunk_tools import chunk_get_text_for_entities_tool
    from Core.AgentSchema.tool_contracts import ChunkGetTextForEntitiesInput

    inputs = ChunkGetTextForEntitiesInput(
        graph_reference_id=graph_reference_id,
        entity_ids=entity_ids,
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
                deduped.append(d)
            else:
                deduped.append(chunk.model_dump(exclude_none=True) if hasattr(chunk, "model_dump") else {})
        return json.dumps({
            "retrieved_chunks": deduped,
            "status_message": f"Retrieved {len(deduped)} chunks for {len(entity_ids)} entities",
        }, indent=2, default=str)

    return _format_result(result)


@mcp.tool()
async def chunk_text_search(query_text: str, dataset_name: str,
                             top_k: int = 10,
                             entity_names: list[str] = None) -> str:
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
    """
    await _ensure_initialized()
    from Core.Operators.chunk.text_search import chunk_text_search as _text_search
    from Core.Schema.SlotTypes import EntityRecord, SlotKind, SlotValue

    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp")}

    # Optionally add entity filter
    if entity_names:
        # Look up entity source_ids from the graph
        ctx = _state["context"]
        entity_records = []
        graph_id = None
        if hasattr(ctx, "list_graphs"):
            for gid in ctx.list_graphs():
                if dataset_name in gid:
                    graph_id = gid
                    break
        if graph_id:
            gi = ctx.get_graph_instance(graph_id)
            if gi and hasattr(gi, "_graph") and hasattr(gi._graph, "graph"):
                nx_graph = gi._graph.graph
                for name in entity_names:
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

    op_ctx = await _build_operator_context_for_dataset(dataset_name)
    result = await _text_search(inputs=inputs, ctx=op_ctx, params={"top_k": top_k})

    chunks = result.get("chunks")
    if chunks and hasattr(chunks, "data"):
        deduped = []
        for c in chunks.data:
            is_new, text = _dedup_chunk(c.chunk_id, c.text)
            deduped.append({"chunk_id": c.chunk_id, "text": text, "score": c.score})
        return json.dumps({
            "chunks": [
                entry for entry in deduped
            ]
        }, indent=2, default=str)
    return json.dumps({"chunks": []})


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
    from Core.AgentTools.chunk_vdb_tools import chunk_vdb_build_tool

    result = await chunk_vdb_build_tool(
        dataset_name=dataset_name,
        graphrag_context=_state["context"],
        vdb_collection_name=vdb_collection_name or None,
        force_rebuild=force_rebuild,
    )
    return json.dumps(result, indent=2, default=str)

if not BENCHMARK_MODE:
    chunk_vdb_build = mcp.tool()(chunk_vdb_build)


@mcp.tool()
async def chunk_vdb_search(query_text: str, dataset_name: str,
                            top_k: int = 10) -> str:
    """Semantic embedding search over document chunks. Finds passages similar in meaning to the query.

    Use alongside chunk_text_search for dual retrieval — embedding search catches
    semantic matches that keyword search misses, and vice versa.

    Args:
        query_text: Natural language search query
        dataset_name: Dataset whose chunk VDB to search
        top_k: Number of top chunks to return

    Returns:
        chunks: list of {chunk_id: str, text: str, score: float}
    """
    await _ensure_initialized()
    from Core.Operators.chunk.vdb import chunk_vdb as _chunk_vdb_op
    from Core.Schema.SlotTypes import SlotKind, SlotValue

    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp")}
    op_ctx = await _build_operator_context_for_dataset(dataset_name)

    if op_ctx.chunks_vdb is None:
        return json.dumps({"error": "Chunk VDB not built. Run chunk_vdb_build first.", "chunks": []})

    result = await _chunk_vdb_op(inputs=inputs, ctx=op_ctx, params={"top_k": top_k})

    chunks = result.get("chunks")
    if chunks and hasattr(chunks, "data"):
        deduped = []
        for c in chunks.data:
            is_new, text = _dedup_chunk(c.chunk_id, c.text)
            deduped.append({"chunk_id": c.chunk_id, "text": text, "score": c.score})
        return json.dumps({"chunks": deduped}, indent=2, default=str)
    return json.dumps({"chunks": []})


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
# AUTO-COMPOSE (LLM-driven method selection)
# =============================================================================

async def auto_compose(query: str, dataset_name: str,
                       auto_build: bool = True,
                       return_context_only: bool = False) -> str:
    """Automatically select and run the best retrieval method for a query.

    An LLM analyzes the query characteristics and available resources,
    picks from the 10 named methods, then executes it end-to-end.

    Three client modes (increasing control):
    1. auto_compose — DIGIMON picks the method (this tool)
    2. execute_method — client picks from 10 methods
    3. Individual operator tools — client composes everything

    Args:
        query: The question to answer
        dataset_name: Name of the dataset (must have graph built)
        auto_build: Auto-build missing prerequisites (VDBs, sparse matrices, communities)
        return_context_only: If True, return raw context instead of generated answer
    """
    await _ensure_initialized()
    _ensure_composer()

    trace_id = f"digimon.auto_compose.{dataset_name}.{uuid.uuid4().hex[:8]}"

    from Core.Composition.auto_compose import select_method

    # Determine model for method selection
    config = _state["config"]
    model = getattr(config, "agentic_model", None) or config.llm.model

    # Tag the agentic LLM with this trace_id for the method selection call
    llm = _state.get("agentic_llm") or _state["llm"]
    if hasattr(llm, "set_trace_id"):
        llm.set_trace_id(trace_id)

    # Get current resources
    resources_json = await list_available_resources()

    # LLM selects the method
    composer = _state["composer"]
    decision = await select_method(
        query=query,
        dataset_name=dataset_name,
        composer=composer,
        model=model,
        resources=resources_json,
        auto_build=auto_build,
        trace_id=trace_id,
    )

    logger.info(
        f"auto_compose: selected '{decision.method_name}' "
        f"(confidence={decision.confidence:.2f}) — {decision.reasoning}"
    )

    # Execute the selected method
    result_json = await execute_method(
        method_name=decision.method_name,
        query=query,
        dataset_name=dataset_name,
        return_context_only=return_context_only,
        auto_build=auto_build,
    )

    # Attach composition metadata to the result
    result = json.loads(result_json)
    result["_composition"] = {
        "method_selected": decision.method_name,
        "reasoning": decision.reasoning,
        "confidence": decision.confidence,
        "trace_id": trace_id,
    }

    return json.dumps(result, indent=2, default=str)

if not BENCHMARK_MODE:
    auto_compose = mcp.tool()(auto_compose)


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
async def relationship_vdb_search(vdb_reference_id: str, query_text: str,
                                   top_k: int = 10,
                                   score_threshold: float = None) -> str:
    """Search for relationships similar to a query using vector similarity.

    Args:
        vdb_reference_id: ID of the relationship VDB to search
        query_text: Natural language search query
        top_k: Number of results to return
        score_threshold: Minimum similarity score (optional)

    Returns:
        similar_relationships: list of [relationship_id: str, description: str, score: float]
    """
    await _ensure_initialized()
    from Core.AgentTools.relationship_tools import relationship_vdb_search_tool
    from Core.AgentSchema.tool_contracts import RelationshipVDBSearchInputs

    inputs = RelationshipVDBSearchInputs(
        vdb_reference_id=vdb_reference_id,
        query_text=query_text,
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
    _ensure_composer()

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
    _ensure_composer()

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


# =============================================================================
# METHOD-LEVEL TOOLS
# =============================================================================

async def list_methods() -> str:
    """List all 10 available retrieval methods with rich metadata.

    Returns profiles including operator chains, requirements (VDB, community,
    sparse matrices), cost tiers, and guidance on when to use each method.
    Use this to decide which method to pass to execute_method.
    """
    await _ensure_initialized()
    _ensure_composer()

    profiles = _state["composer"].get_method_profiles()
    return json.dumps([
        {
            "name": p.name,
            "description": p.description,
            "operator_chain": p.operator_chain,
            "requires_entity_vdb": p.requires_entity_vdb,
            "requires_relationship_vdb": p.requires_relationship_vdb,
            "requires_community": p.requires_community,
            "requires_sparse_matrices": p.requires_sparse_matrices,
            "cost_tier": p.cost_tier,
            "has_loop": p.has_loop,
            "uses_llm_operators": p.uses_llm_operators,
            "good_for": p.good_for,
        }
        for p in profiles
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


async def execute_method(method_name: str, query: str, dataset_name: str,
                          return_context_only: bool = False,
                          auto_build: bool = False) -> str:
    """Run a named retrieval method pipeline end-to-end.

    This executes a complete retrieval pipeline (e.g., basic_local runs:
    entity VDB search -> relationship one-hop -> chunk co-occurrence -> answer).

    Use list_methods to see all available methods and their requirements.

    Args:
        method_name: One of: basic_local, basic_global, lightrag, fastgraphrag,
                     hipporag, tog, gr, dalk, kgp, med
        query: The question to answer
        dataset_name: Name of the dataset (must have graph + VDB built)
        return_context_only: If True, return raw retrieved context instead of
                           a generated answer. Useful when the calling agent
                           wants to synthesize the answer itself.
        auto_build: If True, automatically build all missing prerequisites before
                   running: entity VDB, relationship VDB, sparse matrices, and
                   community structure. Community building calls LLM (most expensive).
    """
    await _ensure_initialized()
    _ensure_composer()

    trace_id = f"digimon.execute_method.{method_name}.{dataset_name}.{uuid.uuid4().hex[:8]}"

    composer = _state["composer"]

    # Build the execution plan
    plan = composer.build_plan(
        method_name=method_name,
        query=query,
        return_context_only=return_context_only,
        dataset=dataset_name,
    )

    # Build OperatorContext for pipeline execution
    op_ctx = await _build_operator_context_for_dataset(dataset_name, trace_id=trace_id)

    # Validate prerequisites before running
    profile = composer.get_profile(method_name)
    if profile:
        missing = _check_prerequisites(profile, op_ctx, dataset_name)
        if missing and auto_build:
            built = await _auto_build_prerequisites(profile, op_ctx, dataset_name)
            # Re-build context after auto-build
            op_ctx = await _build_operator_context_for_dataset(dataset_name, trace_id=trace_id)
            missing = _check_prerequisites(profile, op_ctx, dataset_name)
            if missing:
                return json.dumps({
                    "error": f"Method '{method_name}' still missing prerequisites after auto-build",
                    "built": built,
                    "still_missing": missing,
                    "hint": "Check logs for build errors. You can also try building prerequisites individually.",
                }, indent=2)
        elif missing:
            return json.dumps({
                "error": f"Method '{method_name}' cannot run: missing prerequisites",
                "missing": missing,
                "hint": "Build the required resources first, or pass auto_build=True to auto-build VDBs.",
            }, indent=2)

    # Execute the plan
    from Core.Composition.PipelineExecutor import PipelineExecutionError
    try:
        result = await composer.execute(plan, op_ctx)
    except PipelineExecutionError as e:
        return json.dumps({
            "error": f"Pipeline execution failed: {e}",
            "method": method_name,
            "dataset": dataset_name,
            "trace_id": trace_id,
        }, indent=2)

    if isinstance(result, dict):
        result["_trace_id"] = trace_id
    return json.dumps(result, indent=2, default=str)

if not BENCHMARK_MODE:
    list_methods = mcp.tool()(list_methods)
    execute_method = mcp.tool()(execute_method)


async def _auto_build_prerequisites(profile, op_ctx, dataset_name: str) -> list[str]:
    """Auto-build missing prerequisites for a method. Returns list of what was built."""
    built = []

    if op_ctx.graph is None:
        # Try to load/build graph from disk (graph_build_er detects existing artifacts)
        logger.info(f"auto_build: No graph in context for '{dataset_name}' — attempting graph_build_er")
        try:
            result_json = await graph_build_er(dataset_name=dataset_name)
            result = json.loads(result_json)
            if result.get("status") == "success":
                built.append("graph")
                logger.info(f"auto_build: Graph loaded/built for '{dataset_name}' ({result.get('node_count')} nodes)")
            else:
                logger.warning(f"auto_build: graph_build_er failed: {result}")
                return built
        except Exception as e:
            logger.warning(f"auto_build: graph_build_er raised: {e}")
            return built
        # Re-derive op_ctx now that graph is loaded
        op_ctx = await _build_operator_context_for_dataset(dataset_name)
        if op_ctx.graph is None:
            logger.warning(f"auto_build: Graph still None after build — giving up")
            return built

    # Determine graph_id from context
    ctx = _state["context"]
    graph_id = None
    if hasattr(ctx, "list_graphs"):
        for gid in ctx.list_graphs():
            if dataset_name in gid:
                graph_id = gid
                break
    if not graph_id:
        logger.warning(f"auto_build: Could not find graph_id for '{dataset_name}'")
        return built

    if profile.requires_entity_vdb and op_ctx.entities_vdb is None:
        logger.info(f"auto_build: Building entity VDB for '{dataset_name}'")
        from Core.AgentTools.entity_vdb_tools import entity_vdb_build_tool
        from Core.AgentSchema.tool_contracts import EntityVDBBuildInputs
        inputs = EntityVDBBuildInputs(
            graph_reference_id=graph_id,
            vdb_collection_name=f"{dataset_name}_entities",
            force_rebuild=False,
        )
        await entity_vdb_build_tool(inputs, ctx)
        built.append("entity_vdb")

    if profile.requires_relationship_vdb and op_ctx.relations_vdb is None:
        logger.info(f"auto_build: Building relationship VDB for '{dataset_name}'")
        from Core.AgentTools.relationship_tools import relationship_vdb_build_tool
        from Core.AgentSchema.tool_contracts import RelationshipVDBBuildInputs
        inputs = RelationshipVDBBuildInputs(
            graph_reference_id=graph_id,
            vdb_collection_name=f"{dataset_name}_relations",
            force_rebuild=False,
        )
        await relationship_vdb_build_tool(inputs, ctx)
        built.append("relationship_vdb")

    if profile.requires_sparse_matrices and not op_ctx.sparse_matrices:
        logger.info(f"auto_build: Building sparse matrices for '{dataset_name}'")
        result_json = await build_sparse_matrices(dataset_name, force_rebuild=False)
        result = json.loads(result_json)
        if result.get("status") in ("success", "loaded_from_disk"):
            built.append("sparse_matrices")
        else:
            logger.warning(f"auto_build: Failed to build sparse matrices: {result.get('error')}")

    if profile.requires_community and op_ctx.community is None:
        logger.info(f"auto_build: Building communities for '{dataset_name}'")
        result_json = await build_communities(dataset_name, force_rebuild=False)
        result = json.loads(result_json)
        if result.get("status") == "success":
            built.append("community")
        else:
            logger.warning(f"auto_build: Failed to build communities: {result.get('error')}")

    if built:
        logger.info(f"auto_build: Built {built} for '{dataset_name}'")

    return built


def _ensure_composer() -> None:
    """Lazily initialize the OperatorComposer."""
    if "composer" not in _state:
        from Core.Operators.registry import REGISTRY
        from Core.Composition.OperatorComposer import OperatorComposer

        _state["composer"] = OperatorComposer(REGISTRY)


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
        for vdb_id in ctx.list_vdbs():
            vdb_inst = ctx.get_vdb_instance(vdb_id)
            if vdb_inst:
                if "entities" in vdb_id and entities_vdb is None:
                    entities_vdb = vdb_inst
                elif "relation" in vdb_id and relations_vdb is None:
                    relations_vdb = vdb_inst
                elif "chunks" in vdb_id and chunks_vdb is None:
                    chunks_vdb = vdb_inst

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


def _check_prerequisites(profile, op_ctx, dataset_name: str) -> list[str]:
    """Check if OperatorContext has what a method profile requires.

    Returns list of missing prerequisite descriptions (empty = all good).
    """
    missing = []

    if op_ctx.graph is None:
        missing.append(f"No graph found for dataset '{dataset_name}'. Build one first (e.g., graph_build_er).")

    if profile.requires_entity_vdb and op_ctx.entities_vdb is None:
        missing.append("Entity VDB required but not built. Run entity_vdb_build first.")

    if profile.requires_relationship_vdb and op_ctx.relations_vdb is None:
        missing.append("Relationship VDB required but not built. Run relationship_vdb_build first.")

    if profile.requires_community and op_ctx.community is None:
        missing.append("Community structure required but not available. Run community detection on the graph first.")

    if profile.requires_sparse_matrices and not op_ctx.sparse_matrices:
        missing.append("Sparse matrices (entity_to_rel, rel_to_chunk) required but not built.")

    return missing


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
    @mcp.tool()
    async def submit_answer(reasoning: str, answer: str) -> str:
        """Submit your final answer. Call once with your best answer.

        Args:
            reasoning: Why this is the correct answer. Reference the specific source text
                      and explain how it answers the question.
            answer: The precise answer to the question. Just the fact, no explanation.
                   For yes/no questions: "yes" or "no".

        Returns:
            Confirmation with submitted answer.
        """
        _reset_chunk_dedup()  # reset seen chunks for next question
        return json.dumps({"status": "submitted", "answer": answer})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    if BENCHMARK_MODE:
        for tool_name in _BENCHMARK_HIDDEN_TOOLS:
            try:
                mcp.remove_tool(tool_name)
            except Exception:
                pass  # tool wasn't registered (already hidden by other guards)
        _compact_tool_schemas()
        n_remaining = len(mcp._tool_manager._tools)
        print(f"Benchmark mode: {n_remaining} tools (compact schemas)", file=sys.stderr)
    mcp.run(transport="stdio")
