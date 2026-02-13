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
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

# --- Initialize MCP Server ---
mcp = FastMCP("digimon-kgrag", instructions="""
DIGIMON KG-RAG Tools: Build knowledge graphs from documents and query them.

Typical workflow:
1. corpus_prepare - Prepare text files into a corpus
2. graph_build_er (or rk, tree, passage) - Build a knowledge graph
3. entity_vdb_build - Build a vector index of entities
4. entity_vdb_search - Search for relevant entities
5. chunk_get_text - Get source text for entities
6. graph_analyze - Get graph statistics
7. graph_visualize - Export graph structure

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
    from Core.Provider.LiteLLMProvider import LiteLLMProvider
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentSchema.context import GraphRAGContext

    config_path = os.path.join(project_root, "Option", "Config2.yaml")
    config = Config.from_yaml_file(config_path)

    llm = LiteLLMProvider(config.llm)
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
    _state["initialized"] = True


def _format_result(result: Any) -> str:
    """Convert tool output to readable string."""
    if hasattr(result, "model_dump"):
        d = result.model_dump(exclude_none=True, exclude={"graph_instance"})
        return json.dumps(d, indent=2, default=str)
    elif isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    return str(result)


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

@mcp.tool()
async def corpus_prepare(input_directory: str, dataset_name: str) -> str:
    """Prepare .txt files from a directory into a Corpus.json for DIGIMON processing.

    Args:
        input_directory: Path to directory containing .txt files (relative to project root or absolute)
        dataset_name: Name for this dataset (used to namespace all artifacts)
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


# =============================================================================
# GRAPH CONSTRUCTION TOOLS
# =============================================================================

@mcp.tool()
async def graph_build_er(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build an Entity-Relationship (ER) knowledge graph from a prepared corpus.
    Extracts entities and their relationships using LLM. Best for general-purpose KG.

    Args:
        dataset_name: Name of the dataset (must have corpus prepared first)
        force_rebuild: Force rebuild even if graph exists
    """
    await _ensure_initialized()
    from Core.AgentTools.graph_construction_tools import build_er_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildERGraphInputs

    inputs = BuildERGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
    )
    result = await build_er_graph(inputs, _state["config"], _state["llm"],
                                   _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


@mcp.tool()
async def graph_build_rk(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build an RK (Relationship-Keyword) graph. Like ER but with keyword-enriched edges.

    Args:
        dataset_name: Name of the dataset
        force_rebuild: Force rebuild even if graph exists
    """
    await _ensure_initialized()
    from Core.AgentTools.graph_construction_tools import build_rk_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildRKGraphInputs

    inputs = BuildRKGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
    )
    result = await build_rk_graph(inputs, _state["config"], _state["llm"],
                                   _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


@mcp.tool()
async def graph_build_tree(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build a hierarchical Tree graph (RAPTOR-style). Clusters chunks and creates summaries at multiple levels.

    Args:
        dataset_name: Name of the dataset
        force_rebuild: Force rebuild even if graph exists
    """
    await _ensure_initialized()
    from Core.AgentTools.graph_construction_tools import build_tree_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildTreeGraphInputs

    inputs = BuildTreeGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
    )
    result = await build_tree_graph(inputs, _state["config"], _state["llm"],
                                     _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


@mcp.tool()
async def graph_build_tree_balanced(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build a balanced Tree graph using K-Means clustering for more uniform cluster sizes.

    Args:
        dataset_name: Name of the dataset
        force_rebuild: Force rebuild even if graph exists
    """
    await _ensure_initialized()
    from Core.AgentTools.graph_construction_tools import build_tree_graph_balanced
    from Core.AgentSchema.graph_construction_tool_contracts import BuildTreeGraphBalancedInputs

    inputs = BuildTreeGraphBalancedInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
    )
    result = await build_tree_graph_balanced(inputs, _state["config"], _state["llm"],
                                              _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


@mcp.tool()
async def graph_build_passage(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build a Passage graph where nodes are text passages linked by shared entities.

    Args:
        dataset_name: Name of the dataset
        force_rebuild: Force rebuild even if graph exists
    """
    await _ensure_initialized()
    from Core.AgentTools.graph_construction_tools import build_passage_graph
    from Core.AgentSchema.graph_construction_tool_contracts import BuildPassageGraphInputs

    inputs = BuildPassageGraphInputs(
        target_dataset_name=dataset_name,
        force_rebuild=force_rebuild,
    )
    result = await build_passage_graph(inputs, _state["config"], _state["llm"],
                                        _state["encoder"], _state["chunk_factory"])
    await _register_graph_if_built(result)
    return _format_result(result)


# =============================================================================
# ENTITY TOOLS
# =============================================================================

@mcp.tool()
async def entity_vdb_build(graph_reference_id: str, vdb_collection_name: str,
                           force_rebuild: bool = False) -> str:
    """Build a vector database index from entities in a graph. Required before entity_vdb_search.

    Args:
        graph_reference_id: ID of the graph (e.g. 'Fictional_Test_ERGraph')
        vdb_collection_name: Name for the VDB collection (e.g. 'Fictional_Test_entities')
        force_rebuild: Force rebuild even if VDB exists
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


@mcp.tool()
async def entity_vdb_search(vdb_reference_id: str, query_text: str,
                            top_k: int = 5) -> str:
    """Search for entities similar to a query using vector similarity.

    Args:
        vdb_reference_id: ID of the entity VDB to search
        query_text: Natural language search query
        top_k: Number of results to return
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
# RELATIONSHIP TOOLS
# =============================================================================

@mcp.tool()
async def relationship_onehop(entity_ids: list[str], graph_reference_id: str) -> str:
    """Get one-hop relationships for given entities.

    Args:
        entity_ids: Entity IDs to find relationships for
        graph_reference_id: ID of the graph
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


# =============================================================================
# CHUNK TOOLS
# =============================================================================

@mcp.tool()
async def chunk_get_text(graph_reference_id: str, entity_ids: list[str],
                         max_chunks_per_entity: int = 5) -> str:
    """Get source text chunks associated with specific entities.

    Args:
        graph_reference_id: ID of the graph containing the entities
        entity_ids: List of entity names/IDs to get text for
        max_chunks_per_entity: Max chunks per entity
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
    return _format_result(result)


# =============================================================================
# GRAPH ANALYSIS TOOLS
# =============================================================================

@mcp.tool()
async def graph_analyze(graph_id: str) -> str:
    """Get statistics and metrics about a built graph (node count, edge count, centrality, clustering, etc).

    Args:
        graph_id: ID of the graph to analyze
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
    """
    await _ensure_initialized()
    from Core.AgentTools.graph_visualization_tools import visualize_graph

    inputs = {"graph_id": graph_id, "output_format": output_format}
    result = visualize_graph(inputs, _state["context"])
    return _format_result(result)


# =============================================================================
# CONTEXT INSPECTION TOOLS
# =============================================================================

@mcp.tool()
async def list_available_resources() -> str:
    """List all currently available graphs, VDBs, and datasets in the session context."""
    await _ensure_initialized()
    ctx = _state["context"]
    return json.dumps({
        "graphs": ctx.list_graphs() if hasattr(ctx, "list_graphs") else [],
        "vdbs": ctx.list_vdbs() if hasattr(ctx, "list_vdbs") else [],
        "working_dir": str(_state["config"].working_dir),
        "data_root": str(_state["config"].data_root),
    }, indent=2)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
