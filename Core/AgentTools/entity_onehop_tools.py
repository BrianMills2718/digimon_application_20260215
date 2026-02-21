# Core/AgentTools/entity_onehop_tools.py

"""
Entity One-Hop Neighbors Tool

This tool extracts all one-hop neighbor entities for given seed entities.
Used in methods like LightRAG for expanding entity context.
"""

import asyncio
import re
from typing import Dict, Any, List, Set, Optional
import networkx as nx
from Core.Common.Logger import logger
from Core.Common.Utils import clean_str
from Core.AgentSchema.tool_contracts import EntityOneHopInput, EntityOneHopOutput
from Core.AgentSchema.context import GraphRAGContext


_TITLE_TOKENS = {
    "mr", "mrs", "ms", "dr", "sir", "lady", "saint",
    "count", "countess", "duke", "duchess", "king", "queen",
}

_STOP_TOKENS = {"of", "the", "a", "an", "in", "on", "at", "for", "by", "to"}

# State-name variants that commonly appear in questions but not in graph nodes.
_STATE_NAME_TO_ABBR = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
    "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne",
    "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or",
    "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
}

_MULTIWORD_STATE_NAMES = sorted(
    (name for name in _STATE_NAME_TO_ABBR if " " in name),
    key=len,
    reverse=True,
)


def _collapse_spaces(text: str) -> str:
    return " ".join(text.split())


def _replace_state_names(text: str) -> str:
    """Normalize full state names to abbreviations (e.g. 'new york' -> 'ny')."""
    out = text
    for state_name in _MULTIWORD_STATE_NAMES:
        out = re.sub(rf"\b{re.escape(state_name)}\b", _STATE_NAME_TO_ABBR[state_name], out)
    tokens = [_STATE_NAME_TO_ABBR.get(tok, tok) for tok in out.split()]
    return " ".join(tokens)


def _resolve_entity_id(entity_id: str, graph: nx.Graph) -> tuple[Optional[str], str]:
    """Resolve user-provided entity id to a graph node id with lightweight normalization."""
    cleaned = clean_str(entity_id)
    collapsed = _collapse_spaces(cleaned)

    candidates: list[tuple[str, str]] = [
        (cleaned, "clean_str"),
        (collapsed, "collapsed_whitespace"),
    ]

    state_variant = _replace_state_names(collapsed)
    if state_variant != collapsed:
        candidates.append((state_variant, "state_abbreviation"))

    tokens = [t for t in state_variant.split() if t]
    no_titles = [t for t in tokens if t not in _TITLE_TOKENS]
    if no_titles:
        no_titles_text = " ".join(no_titles)
        candidates.append((no_titles_text, "title_removed"))

        core_tokens = [t for t in no_titles if t not in _STOP_TOKENS]
        if core_tokens:
            candidates.append((" ".join(core_tokens), "stopwords_removed"))
            # Single-token candidates catch cases like "godiva, countess of leicester" -> "godiva".
            candidates.append((core_tokens[0], "first_core_token"))
            candidates.append((core_tokens[-1], "last_core_token"))

    seen: set[str] = set()
    for candidate, reason in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if candidate in graph:
            return candidate, reason

    return None, "not_found"


def entity_onehop_neighbors(input_data: Dict[str, Any], context: GraphRAGContext) -> Dict[str, Any]:
    """
    Find one-hop neighbor entities for given entity IDs.
    
    Args:
        input_data: Dictionary containing EntityOneHopInput fields
        context: GraphRAGContext containing graph instances
        
    Returns:
        Dictionary containing EntityOneHopOutput fields
    """
    try:
        # Validate input
        validated_input = EntityOneHopInput(**input_data)
    except Exception as e:
        logger.error(f"Failed to validate Entity.Onehop input: {e}")
        return {
            "neighbors": {},
            "total_neighbors_found": 0,
            "message": f"Invalid input parameters: {str(e)}"
        }
    
    entity_ids = validated_input.entity_ids
    graph_id = validated_input.graph_reference_id
    include_edge_attrs = validated_input.include_edge_attributes
    neighbor_limit = validated_input.neighbor_limit_per_entity
    
    # Get graph instance
    graph_instance = context.get_graph_instance(graph_id)
    if graph_instance is None:
        logger.warning(f"Graph '{graph_id}' not found in context")
        return {
            "neighbors": {},
            "total_neighbors_found": 0,
            "message": f"Graph '{graph_id}' not found in context"
        }
    
    # Extract NetworkX graph
    graph = None
    if hasattr(graph_instance, '_graph'):
        storage = graph_instance._graph
        if hasattr(storage, 'graph'):
            graph = storage.graph
        elif hasattr(storage, '_graph'):
            graph = storage._graph
        elif isinstance(storage, nx.Graph):
            graph = storage
    elif hasattr(graph_instance, 'graph'):
        graph = graph_instance.graph
    elif isinstance(graph_instance, nx.Graph):
        graph = graph_instance
    
    if graph is None:
        logger.error(f"Could not extract NetworkX graph from graph instance '{graph_id}'")
        return {
            "neighbors": {},
            "total_neighbors_found": 0,
            "message": f"Could not extract graph data from '{graph_id}'"
        }
    
    # Find one-hop neighbors for each entity
    neighbors_dict = {}
    all_neighbors = set()
    
    for entity_id in entity_ids:
        # Resolve common alias/normalization mismatches before graph lookup.
        resolved_id, resolve_reason = _resolve_entity_id(entity_id, graph)
        if resolved_id is None:
            cleaned_id = clean_str(entity_id)
            logger.warning(
                f"Entity '{entity_id}' (cleaned: '{cleaned_id}') not found in graph '{graph_id}'",
            )
            neighbors_dict[entity_id] = []
            continue
        if resolve_reason != "clean_str":
            logger.info(
                f"Resolved entity '{entity_id}' -> '{resolved_id}' via {resolve_reason}",
            )

        # Get neighbors using cleaned_id for graph lookups
        try:
            if graph.is_directed():
                # For directed graphs, get both successors and predecessors
                successors = list(graph.successors(resolved_id))
                predecessors = list(graph.predecessors(resolved_id))
                neighbor_ids = list(set(successors + predecessors))
            else:
                # For undirected graphs
                neighbor_ids = list(graph.neighbors(resolved_id))

            # Apply neighbor limit if specified
            if neighbor_limit is not None and len(neighbor_ids) > neighbor_limit:
                # Sort by degree centrality to get most connected neighbors
                neighbor_degrees = [(n, graph.degree(n)) for n in neighbor_ids]
                neighbor_degrees.sort(key=lambda x: x[1], reverse=True)
                neighbor_ids = [n[0] for n in neighbor_degrees[:neighbor_limit]]

            # Build neighbor information
            neighbor_info = []
            for neighbor_id in neighbor_ids:
                neighbor_data = {
                    "entity_id": neighbor_id,
                    "node_attributes": dict(graph.nodes[neighbor_id]) if neighbor_id in graph else {}
                }

                # Include edge attributes if requested
                if include_edge_attrs:
                    edge_attrs = []

                    if graph.is_directed():
                        # Check both directions
                        if graph.has_edge(resolved_id, neighbor_id):
                            edge_attrs.append({
                                "direction": "outgoing",
                                "attributes": dict(graph[resolved_id][neighbor_id])
                            })
                        if graph.has_edge(neighbor_id, resolved_id):
                            edge_attrs.append({
                                "direction": "incoming",
                                "attributes": dict(graph[neighbor_id][resolved_id])
                            })
                    else:
                        # Undirected graph
                        if graph.has_edge(resolved_id, neighbor_id):
                            edge_attrs.append({
                                "attributes": dict(graph[resolved_id][neighbor_id])
                            })

                    neighbor_data["edge_attributes"] = edge_attrs

                neighbor_info.append(neighbor_data)
                all_neighbors.add(neighbor_id)

            neighbors_dict[entity_id] = neighbor_info
            
        except Exception as e:
            logger.error(f"Error finding neighbors for entity '{entity_id}': {e}")
            neighbors_dict[entity_id] = []
    
    # Create output
    result = {
        "neighbors": neighbors_dict,
        "total_neighbors_found": len(all_neighbors),
        "message": f"Successfully found neighbors for {len(neighbors_dict)} entities"
    }
    
    # Log summary
    logger.info(f"Entity.Onehop found {len(all_neighbors)} unique neighbors for {len(entity_ids)} entities in graph '{graph_id}'")
    
    return result


# Async wrapper for compatibility with async orchestrator
async def entity_onehop_neighbors_tool(input_data: Dict[str, Any], context: GraphRAGContext) -> Dict[str, Any]:
    """Async wrapper for entity_onehop_neighbors."""
    return entity_onehop_neighbors(input_data, context)
