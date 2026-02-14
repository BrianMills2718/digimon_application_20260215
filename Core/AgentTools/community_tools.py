# Core/AgentTools/community_tools.py

import json
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from Core.AgentSchema.context import GraphRAGContext
from Core.Common.Logger import logger

from Core.AgentSchema.tool_contracts import (
    CommunityDetectFromEntitiesInputs,
    CommunityDetectFromEntitiesOutputs,
    CommunityGetLayerInputs,
    CommunityGetLayerOutputs,
    CommunityData
)

# --- Tool Implementation for: Community Detection from Entities ---
# tool_id: "Community.DetectFromEntities"

async def community_detect_from_entities_tool(
    params: CommunityDetectFromEntitiesInputs,
    graphrag_context: GraphRAGContext
) -> CommunityDetectFromEntitiesOutputs:
    """
    Detects communities containing specified seed entities by reading
    the community schema from the graph's storage layer.
    """
    logger.info(
        f"Executing Community.DetectFromEntities: seeds={params.seed_entity_ids}, "
        f"graph='{params.graph_reference_id}'"
    )

    graph_instance = graphrag_context.get_graph_instance(params.graph_reference_id)
    if graph_instance is None:
        logger.error(f"Community.DetectFromEntities: Graph '{params.graph_reference_id}' not found")
        return CommunityDetectFromEntitiesOutputs(relevant_communities=[])

    # Get community schema from the graph's storage
    # community_schema() returns Dict[str, LeidenInfo]
    try:
        if hasattr(graph_instance, 'community_schema'):
            community_schema = await graph_instance.community_schema()
        elif hasattr(graph_instance, '_graph') and hasattr(graph_instance._graph, 'get_community_schema'):
            community_schema = await graph_instance._graph.get_community_schema()
        else:
            logger.error("Community.DetectFromEntities: No community schema method available on graph")
            return CommunityDetectFromEntitiesOutputs(relevant_communities=[])
    except Exception as e:
        logger.error(f"Community.DetectFromEntities: Error getting community schema: {e}", exc_info=True)
        return CommunityDetectFromEntitiesOutputs(relevant_communities=[])

    if not community_schema:
        logger.warning("Community.DetectFromEntities: Empty community schema")
        return CommunityDetectFromEntitiesOutputs(relevant_communities=[])

    seed_set = set(params.seed_entity_ids)

    # Filter communities whose node sets intersect with seed entities
    matching = []
    for cluster_key, leiden_info in community_schema.items():
        # leiden_info.nodes is a list (or set) of entity names
        comm_nodes = set(leiden_info.nodes) if not isinstance(leiden_info.nodes, set) else leiden_info.nodes
        overlap = comm_nodes & seed_set
        if overlap:
            matching.append((cluster_key, leiden_info, len(overlap)))

    # Sort by overlap count descending, then by occurrence
    matching.sort(key=lambda x: (x[2], x[1].occurrence), reverse=True)

    max_communities = params.max_communities_to_return or 5
    matching = matching[:max_communities]

    relevant_communities = []
    for cluster_key, leiden_info, _ in matching:
        # CommunityData inherits from LeidenInfo (dataclass) — construct with base fields
        # then set community_id separately since LeidenInfo.__init__ doesn't accept it
        comm = CommunityData(
            level=leiden_info.level,
            title=leiden_info.title or f"Cluster {cluster_key}",
            nodes=set(leiden_info.nodes) if isinstance(leiden_info.nodes, list) else leiden_info.nodes,
            edges=leiden_info.edges,
            chunk_ids=set(leiden_info.chunk_ids) if isinstance(leiden_info.chunk_ids, list) else leiden_info.chunk_ids,
            occurrence=leiden_info.occurrence,
            sub_communities=leiden_info.sub_communities,
        )
        comm.community_id = cluster_key
        relevant_communities.append(comm)

    logger.info(f"Community.DetectFromEntities: Found {len(relevant_communities)} communities")
    return CommunityDetectFromEntitiesOutputs(relevant_communities=relevant_communities)


# --- Tool Implementation for: Community Get Layer ---
# tool_id: "Community.GetLayer"

async def community_get_layer_tool(
    params: CommunityGetLayerInputs,
    graphrag_context: GraphRAGContext
) -> CommunityGetLayerOutputs:
    """
    Returns all communities at or below a specified layer depth
    from the hierarchical community structure.
    """
    logger.info(
        f"Executing Community.GetLayer: hierarchy='{params.community_hierarchy_reference_id}', "
        f"max_depth={params.max_layer_depth}"
    )

    graph_instance = graphrag_context.get_graph_instance(params.community_hierarchy_reference_id)
    if graph_instance is None:
        logger.error(f"Community.GetLayer: Graph '{params.community_hierarchy_reference_id}' not found")
        return CommunityGetLayerOutputs(communities_in_layers=[])

    # Get community schema
    try:
        if hasattr(graph_instance, 'community_schema'):
            community_schema = await graph_instance.community_schema()
        elif hasattr(graph_instance, '_graph') and hasattr(graph_instance._graph, 'get_community_schema'):
            community_schema = await graph_instance._graph.get_community_schema()
        else:
            logger.error("Community.GetLayer: No community schema method available")
            return CommunityGetLayerOutputs(communities_in_layers=[])
    except Exception as e:
        logger.error(f"Community.GetLayer: Error getting community schema: {e}", exc_info=True)
        return CommunityGetLayerOutputs(communities_in_layers=[])

    if not community_schema:
        logger.warning("Community.GetLayer: Empty community schema")
        return CommunityGetLayerOutputs(communities_in_layers=[])

    # Filter communities where level <= max_layer_depth
    communities_in_layers = []
    for cluster_key, leiden_info in community_schema.items():
        try:
            level_val = int(leiden_info.level) if leiden_info.level != "" else 0
        except (ValueError, TypeError):
            level_val = 0

        if level_val <= params.max_layer_depth:
            comm = CommunityData(
                level=leiden_info.level,
                title=leiden_info.title or f"Cluster {cluster_key}",
                nodes=set(leiden_info.nodes) if isinstance(leiden_info.nodes, list) else leiden_info.nodes,
                edges=leiden_info.edges,
                chunk_ids=set(leiden_info.chunk_ids) if isinstance(leiden_info.chunk_ids, list) else leiden_info.chunk_ids,
                occurrence=leiden_info.occurrence,
                sub_communities=leiden_info.sub_communities,
            )
            comm.community_id = cluster_key
            communities_in_layers.append(comm)

    # Sort by level then occurrence
    communities_in_layers.sort(key=lambda c: (str(c.level), -c.occurrence))

    logger.info(f"Community.GetLayer: Found {len(communities_in_layers)} communities at depth <= {params.max_layer_depth}")
    return CommunityGetLayerOutputs(communities_in_layers=communities_in_layers)
