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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# --- Initialize MCP Server ---
mcp = FastMCP("digimon-kgrag", instructions="""
DIGIMON KG-RAG Tools: Build knowledge graphs from documents and query them.

## Two Execution Modes

### Mode 1: Individual Operator Tools (fine-grained control)
Call operators directly for custom pipelines. The calling agent decides the sequence.

Typical workflow:
1. corpus_prepare - Prepare .txt files into a corpus
2. graph_build_er (or rk, tree, tree_balanced, passage) - Build a knowledge graph
3. entity_vdb_build - Build a vector index of entities
4. entity_vdb_search / entity_ppr / entity_tfidf - Find relevant entities
5. relationship_onehop / relationship_vdb_search - Find relationships
6. chunk_get_text / chunk_from_relationships / chunk_occurrence - Get text chunks
7. meta_generate_answer - Generate answer from retrieved context

### Mode 2: Named Method Pipelines (one-call execution)
Use execute_method to run a complete retrieval pipeline end-to-end.
Call list_methods first to see all 10 available methods and their requirements.

### Mode 3: Full Auto (auto_compose)
Use auto_compose with just a query and dataset name. An LLM picks the best
retrieval method based on query characteristics and available resources.

## Graph Types (call list_graph_types for details)
- **er**: General-purpose entity-relationship graph. Works with all methods.
- **rk**: Keyword-enriched relationships. Best for LightRAG.
- **tree/tree_balanced**: Hierarchical clustering. Best for summarization.
- **passage**: Passage-level nodes. Best for document-centric retrieval.

## Retrieval Methods (call list_methods for details)
- **basic_local**: VDB → one-hop → co-occurrence. Simple, fast.
- **basic_global**: Community reports. For broad/thematic questions.
- **lightrag**: Relationship VDB search. Needs RK graph.
- **fastgraphrag**: PPR + sparse matrices. For multi-hop topology.
- **hipporag**: LLM entity extraction → PPR. For out-of-vocabulary entities.
- **tog**: Iterative LLM exploration. For complex multi-hop reasoning.
- **gr**: Dual VDB + PCST optimization. For compact informative subgraphs.
- **dalk**: Entity linking + path filtering. For specific knowledge paths.
- **kgp**: TF-IDF + iterative reasoning. For rich text descriptions.
- **med**: Steiner tree subgraph. For domain-specific connected subgraphs.

## Tips
- Use return_context_only=True in execute_method when you want to synthesize
  the answer yourself instead of letting DIGIMON's LLM generate it.
- Call list_available_resources to see what graphs and VDBs exist.
- Graph building requires corpus_prepare first.
- VDB building requires a graph to be built first.
- Pass auto_build=True to execute_method to auto-build all missing prerequisites:
  entity VDB, relationship VDB, sparse matrices, and community structure.
  Community building calls LLM (most expensive auto-build step).
- Default graph build now uses single-step extraction (extract_two_step=false),
  which extracts entity types, entity descriptions, and relation descriptions.
  Graphs built with the old default (extract_two_step=true) have empty descriptions;
  rebuild them to get descriptions.

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

    # Optional: create agentic LLM via llm_client for meta operators
    if getattr(config, "agentic_model", None):
        try:
            from Core.Provider.LLMClientAdapter import LLMClientAdapter
            _state["agentic_llm"] = LLMClientAdapter(config.agentic_model)
            logger.info(f"Agentic LLM initialized: {config.agentic_model}")
        except ImportError:
            logger.warning("llm_client not available — agentic_model ignored, using default LLM")

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
    Extracts entities (with types and descriptions) and relationships using LLM.
    Best for general-purpose KG. Uses single-step delimiter extraction by default,
    which produces entity types, entity descriptions, and relation descriptions.

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
# COMMUNITY TOOLS
# =============================================================================

@mcp.tool()
async def build_communities(dataset_name: str, force_rebuild: bool = False) -> str:
    """Run Leiden clustering on an existing graph and generate community reports.

    Required by basic_global method. This calls LLM to generate community summaries,
    so it's more expensive than VDB builds but much cheaper than graph rebuilds.

    Args:
        dataset_name: Name of the dataset (must have graph built)
        force_rebuild: Force rebuild even if community data exists on disk
    """
    await _ensure_initialized()
    ctx = _state["context"]
    config = _state["config"]
    llm = _state.get("agentic_llm") or _state["llm"]

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


@mcp.tool()
async def community_detect_from_entities(graph_reference_id: str,
                                          seed_entity_ids: list[str],
                                          max_communities: int = 5) -> str:
    """Find communities containing the given seed entities.

    Args:
        graph_reference_id: ID of the graph with community structure
        seed_entity_ids: Entity IDs to find communities for
        max_communities: Maximum communities to return
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

@mcp.tool()
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


# =============================================================================
# AUTO-COMPOSE (LLM-driven method selection)
# =============================================================================

@mcp.tool()
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

    from Core.Composition.auto_compose import select_method

    # Determine model and API key for method selection
    config = _state["config"]
    model = getattr(config, "agentic_model", None) or config.llm.model
    api_key = getattr(config.llm, "api_key", None)

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
        api_key=api_key,
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
    }

    return json.dumps(result, indent=2, default=str)


# =============================================================================
# RELATIONSHIP VDB BUILD + SEARCH
# =============================================================================

@mcp.tool()
async def relationship_vdb_build(graph_reference_id: str, vdb_collection_name: str,
                                  force_rebuild: bool = False) -> str:
    """Build a vector database index from relationships in a graph. Required before relationship_vdb_search.

    Args:
        graph_reference_id: ID of the graph (e.g. 'Fictional_Test_ERGraph')
        vdb_collection_name: Name for the VDB collection (e.g. 'Fictional_Test_relations')
        force_rebuild: Force rebuild even if VDB exists
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

@mcp.tool()
async def build_sparse_matrices(dataset_name: str, force_rebuild: bool = False) -> str:
    """Build sparse CSR matrices mapping entities→relationships→chunks for a graph.

    Required by fastgraphrag and hipporag methods. Persists matrices to disk.

    Args:
        dataset_name: Name of the dataset (must have graph built)
        force_rebuild: Force rebuild even if matrices exist on disk
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
    """
    await _ensure_initialized()
    from Core.Operators.meta.extract_entities import meta_extract_entities as _extract
    from Core.Schema.SlotTypes import SlotKind, SlotValue

    inputs = {"query": SlotValue(kind=SlotKind.QUERY_TEXT, data=query_text, producer="mcp")}
    result = await _extract(inputs=inputs, ctx=_build_operator_context(), params={})

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

    result = await _generate(inputs=inputs, ctx=_build_operator_context(), params=params)

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
    result = await _pcst(inputs=inputs, ctx=_build_operator_context(), params={})

    sg = result.get("subgraph")
    if sg and hasattr(sg, "data"):
        sg_data = sg.data
        return json.dumps({
            "nodes": list(sg_data.nodes) if sg_data.nodes else [],
            "edges": [(e[0], e[1]) if isinstance(e, tuple) else e for e in (sg_data.edges or [])],
        }, indent=2, default=str)
    return json.dumps({"nodes": [], "edges": []})


def _build_operator_context() -> Any:
    """Build an OperatorContext from the global MCP state for meta operator calls."""
    from Core.Operators._context import OperatorContext

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

    return OperatorContext(
        graph=graph,
        entities_vdb=entities_vdb,
        relations_vdb=relations_vdb,
        doc_chunks=doc_chunks,
        llm=_state.get("agentic_llm") or _state["llm"],
        config=_state["config"],
    )


# =============================================================================
# METHOD-LEVEL TOOLS
# =============================================================================

@mcp.tool()
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


@mcp.tool()
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

    composer = _state["composer"]

    # Build the execution plan
    plan = composer.build_plan(
        method_name=method_name,
        query=query,
        return_context_only=return_context_only,
        dataset=dataset_name,
    )

    # Build OperatorContext for pipeline execution
    op_ctx = await _build_operator_context_for_dataset(dataset_name)

    # Validate prerequisites before running
    profile = composer.get_profile(method_name)
    if profile:
        missing = _check_prerequisites(profile, op_ctx, dataset_name)
        if missing and auto_build:
            built = await _auto_build_prerequisites(profile, op_ctx, dataset_name)
            # Re-build context after auto-build
            op_ctx = await _build_operator_context_for_dataset(dataset_name)
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
        }, indent=2)

    return json.dumps(result, indent=2, default=str)


async def _auto_build_prerequisites(profile, op_ctx, dataset_name: str) -> list[str]:
    """Auto-build missing VDBs for a method. Returns list of what was built."""
    built = []

    if op_ctx.graph is None:
        logger.warning(f"auto_build: No graph for '{dataset_name}' — cannot build VDBs")
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


async def _build_operator_context_for_dataset(dataset_name: str) -> Any:
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
    if hasattr(ctx, "list_vdbs"):
        for vdb_id in ctx.list_vdbs():
            vdb_inst = ctx.get_vdb_instance(vdb_id)
            if vdb_inst:
                if "entities" in vdb_id and entities_vdb is None:
                    entities_vdb = vdb_inst
                elif "relation" in vdb_id and relations_vdb is None:
                    relations_vdb = vdb_inst

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

    return OperatorContext(
        graph=graph,
        entities_vdb=entities_vdb,
        relations_vdb=relations_vdb,
        doc_chunks=doc_chunks,
        community=community,
        llm=_state.get("agentic_llm") or _state["llm"],
        config=retriever_config,
        sparse_matrices=sparse_matrices,
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
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
