# Core/AgentTools/subgraph_tools.py

import itertools
import json
import uuid
from typing import List, Tuple, Optional, Any, Union, Dict, Literal

import networkx as nx
from pydantic import BaseModel, Field

from Core.AgentSchema.context import GraphRAGContext
from Core.AgentSchema.tool_contracts import (
    SubgraphKHopPathsInputs,
    SubgraphKHopPathsOutputs,
    SubgraphSteinerTreeInputs,
    SubgraphSteinerTreeOutputs,
    SubgraphAgentPathInputs,
    SubgraphAgentPathOutputs,
    PathObject,
    PathSegment,
)
from Core.Common.Logger import logger
from Core.Common.Utils import clean_str


def _get_nx_graph(graph_instance) -> Optional[nx.Graph]:
    """Extract the underlying NetworkX graph from a graph instance."""
    if hasattr(graph_instance, '_graph') and hasattr(graph_instance._graph, 'graph') and isinstance(graph_instance._graph.graph, nx.Graph):
        return graph_instance._graph.graph
    if hasattr(graph_instance, '_graph') and isinstance(graph_instance._graph, nx.Graph):
        return graph_instance._graph
    if isinstance(graph_instance, nx.Graph):
        return graph_instance
    return None


def _path_to_path_object(nx_graph: nx.Graph, node_path: List[str]) -> PathObject:
    """Convert a list of node IDs from nx.all_simple_paths into a PathObject
    with alternating entity/relationship PathSegments."""
    segments = []
    for i, node_id in enumerate(node_path):
        # Add entity segment
        segments.append(PathSegment(
            item_id=node_id,
            item_type="entity",
            label=node_id,
        ))
        # Add relationship segment between consecutive nodes
        if i < len(node_path) - 1:
            next_node = node_path[i + 1]
            edge_data = nx_graph.get_edge_data(node_id, next_node) or {}
            rel_name = edge_data.get("relation_name", edge_data.get("type", "related_to"))
            segments.append(PathSegment(
                item_id=f"{node_id}->{next_node}",
                item_type="relationship",
                label=str(rel_name),
            ))

    return PathObject(
        path_id=f"path_{uuid.uuid4().hex[:8]}",
        segments=segments,
        start_node_id=node_path[0],
        end_node_id=node_path[-1] if len(node_path) > 1 else None,
        hop_count=len(node_path) - 1,
    )


def _entity_id_candidates(raw_id: str) -> List[str]:
    """Generate plausible node-id candidates from a free-form/typed entity id."""
    token = (raw_id or "").strip()
    if not token:
        return []

    seeds = [token]
    lower = token.lower()
    for prefix in ("entity:", "node:", "id:"):
        if lower.startswith(prefix):
            seeds.append(token[len(prefix):].strip())

    out: List[str] = []
    for seed in seeds:
        if not seed:
            continue
        variants = [
            seed,
            seed.replace("_", " "),
            seed.lower(),
            seed.lower().replace("_", " "),
            clean_str(seed),
            clean_str(seed.replace("_", " ")),
        ]
        for v in variants:
            v = (v or "").strip()
            if v and v not in out:
                out.append(v)
    return out


def _resolve_graph_node_id(nx_graph: nx.Graph, raw_id: str) -> Optional[str]:
    """Resolve a possibly-prefixed/free-form entity id to an existing graph node id."""
    for cand in _entity_id_candidates(raw_id):
        if cand in nx_graph:
            return cand
    return None


# --- Tool Implementation for: K-Hop Paths ---
# tool_id: "Subgraph.KHopPaths"

async def subgraph_khop_paths_tool(
    params: SubgraphKHopPathsInputs,
    graphrag_context: GraphRAGContext,
) -> SubgraphKHopPathsOutputs:
    """
    Finds k-hop paths in a graph between start and end entity sets
    using nx.all_simple_paths with a cutoff of k_hops.
    If end_entity_ids is None, finds all paths of length k from start entities.
    """
    logger.info(
        f"Executing Subgraph.KHopPaths: starts={params.start_entity_ids}, "
        f"ends={params.end_entity_ids}, k={params.k_hops}, graph='{params.graph_reference_id}'"
    )

    graph_instance = graphrag_context.get_graph_instance(params.graph_reference_id)
    if graph_instance is None:
        logger.error(f"Subgraph.KHopPaths: Graph '{params.graph_reference_id}' not found")
        return SubgraphKHopPathsOutputs(discovered_paths=[])

    nx_graph = _get_nx_graph(graph_instance)
    if nx_graph is None:
        logger.error("Subgraph.KHopPaths: Could not access NetworkX graph")
        return SubgraphKHopPathsOutputs(discovered_paths=[])

    max_paths = params.max_paths_to_return or 10
    discovered_paths: List[PathObject] = []

    resolved_starts: List[str] = []
    for start_id in params.start_entity_ids:
        resolved = _resolve_graph_node_id(nx_graph, start_id)
        if not resolved:
            logger.warning(
                f"Subgraph.KHopPaths: Start entity '{start_id}' not in graph (after normalization)"
            )
            continue
        resolved_starts.append(resolved)

    resolved_ends: Optional[List[str]] = None
    if params.end_entity_ids:
        resolved_ends = []
        for end_id in params.end_entity_ids:
            resolved = _resolve_graph_node_id(nx_graph, end_id)
            if not resolved:
                logger.warning(
                    f"Subgraph.KHopPaths: End entity '{end_id}' not in graph (after normalization)"
                )
                continue
            resolved_ends.append(resolved)

    if resolved_ends:
        # Find paths between each (start, end) pair
        for start_id in resolved_starts:
            for end_id in resolved_ends:
                if start_id == end_id:
                    continue
                try:
                    paths_gen = nx.all_simple_paths(
                        nx_graph, start_id, end_id, cutoff=params.k_hops
                    )
                    for path in itertools.islice(paths_gen, max_paths - len(discovered_paths)):
                        discovered_paths.append(_path_to_path_object(nx_graph, path))
                        if len(discovered_paths) >= max_paths:
                            break
                except nx.NetworkXError as e:
                    logger.warning(f"Subgraph.KHopPaths: NetworkX error for {start_id}->{end_id}: {e}")
                if len(discovered_paths) >= max_paths:
                    break
            if len(discovered_paths) >= max_paths:
                break
    else:
        # No end entities: find k-hop ego neighborhoods
        for start_id in resolved_starts:
            # Get all nodes within k hops
            ego = nx.ego_graph(nx_graph, start_id, radius=params.k_hops)
            # Find paths to all reachable nodes in the ego graph
            for target in ego.nodes():
                if target == start_id:
                    continue
                try:
                    paths_gen = nx.all_simple_paths(
                        nx_graph, start_id, target, cutoff=params.k_hops
                    )
                    for path in itertools.islice(paths_gen, 2):  # limit per target
                        discovered_paths.append(_path_to_path_object(nx_graph, path))
                        if len(discovered_paths) >= max_paths:
                            break
                except nx.NetworkXError:
                    pass
                if len(discovered_paths) >= max_paths:
                    break
            if len(discovered_paths) >= max_paths:
                break

    logger.info(f"Subgraph.KHopPaths: Found {len(discovered_paths)} paths")
    return SubgraphKHopPathsOutputs(discovered_paths=discovered_paths)


# --- Tool Implementation for: Subgraph Operator - SteinerTree ---
# tool_id: "Subgraph.SteinerTree"

async def subgraph_steiner_tree_tool(
    params: SubgraphSteinerTreeInputs,
    graphrag_context: GraphRAGContext,
) -> SubgraphSteinerTreeOutputs:
    """
    Computes an approximate Steiner tree connecting the given terminal nodes.
    Uses nx.algorithms.approximation.steiner_tree.
    """
    logger.info(
        f"Executing Subgraph.SteinerTree: terminals={params.terminal_node_ids}, "
        f"graph='{params.graph_reference_id}'"
    )

    graph_instance = graphrag_context.get_graph_instance(params.graph_reference_id)
    if graph_instance is None:
        logger.error(f"Subgraph.SteinerTree: Graph '{params.graph_reference_id}' not found")
        return SubgraphSteinerTreeOutputs(steiner_tree_edges=[])

    nx_graph = _get_nx_graph(graph_instance)
    if nx_graph is None:
        logger.error("Subgraph.SteinerTree: Could not access NetworkX graph")
        return SubgraphSteinerTreeOutputs(steiner_tree_edges=[])

    # Filter terminal nodes to those that exist in the graph (normalize prefixed IDs).
    valid_terminals: List[str] = []
    for raw_terminal in params.terminal_node_ids:
        resolved = _resolve_graph_node_id(nx_graph, raw_terminal)
        if not resolved:
            continue
        if resolved not in valid_terminals:
            valid_terminals.append(resolved)
    if len(valid_terminals) < 2:
        logger.warning(
            "Subgraph.SteinerTree: Need >= 2 valid terminal nodes, got %d. raw_terminals=%s",
            len(valid_terminals),
            params.terminal_node_ids,
        )
        return SubgraphSteinerTreeOutputs(steiner_tree_edges=[])

    try:
        # NetworkX steiner_tree fails on disconnected graphs even if terminals
        # are all in the same component. Extract the connected component first.
        if not nx.is_connected(nx_graph):
            # Find the component containing the first terminal
            component_nodes = nx.node_connected_component(nx_graph, valid_terminals[0])
            # Filter terminals to those in the same component
            valid_terminals = [n for n in valid_terminals if n in component_nodes]
            if len(valid_terminals) < 2:
                logger.warning("Subgraph.SteinerTree: Terminals are in different components")
                return SubgraphSteinerTreeOutputs(steiner_tree_edges=[])
            work_graph = nx_graph.subgraph(component_nodes).copy()
        else:
            work_graph = nx_graph

        # Use weight attribute if specified and present, otherwise use None (unweighted)
        weight_attr = params.edge_weight_attribute
        if not weight_attr:
            # Check if edges have numeric 'weight' attribute
            sample_edge = next(iter(work_graph.edges(data=True)), None)
            if sample_edge:
                w = sample_edge[2].get("weight")
                if isinstance(w, (int, float)):
                    weight_attr = "weight"
                else:
                    weight_attr = None
            else:
                weight_attr = None

        steiner = nx.algorithms.approximation.steiner_tree(
            work_graph, valid_terminals,
            weight=weight_attr,
        )
    except Exception as e:
        logger.error(f"Subgraph.SteinerTree: Algorithm error: {e}", exc_info=True)
        return SubgraphSteinerTreeOutputs(steiner_tree_edges=[])

    edges = []
    for u, v, data in steiner.edges(data=True):
        edge_dict = {"source": u, "target": v}
        if params.edge_weight_attribute and params.edge_weight_attribute in data:
            edge_dict["weight"] = data[params.edge_weight_attribute]
        elif "weight" in data:
            edge_dict["weight"] = data["weight"]
        # Include relation name if available
        if "relation_name" in data:
            edge_dict["relation_name"] = data["relation_name"]
        edges.append(edge_dict)

    logger.info(f"Subgraph.SteinerTree: Steiner tree has {len(edges)} edges connecting {len(valid_terminals)} terminals")
    return SubgraphSteinerTreeOutputs(steiner_tree_edges=edges)


# --- Tool Implementation for: Subgraph Operator - AgentPath ---
# tool_id: "Subgraph.AgentPath"

async def subgraph_agent_path_tool(
    params: SubgraphAgentPathInputs,
    graphrag_context: GraphRAGContext,
) -> SubgraphAgentPathOutputs:
    """
    Uses an LLM to rank/filter candidate paths by relevance to a user question.
    Formats paths as readable text, asks the LLM to pick the most relevant ones.
    """
    logger.info(
        f"Executing Subgraph.AgentPath: question='{params.user_question[:80]}...', "
        f"{len(params.candidate_paths)} candidate paths"
    )

    if not params.candidate_paths:
        return SubgraphAgentPathOutputs(relevant_paths=[])

    max_to_return = params.max_paths_to_return or 5

    # Format paths as readable strings for the LLM
    path_descriptions = []
    for i, path_obj in enumerate(params.candidate_paths):
        segments_str = " -> ".join(
            seg.label or seg.item_id for seg in path_obj.segments
        )
        path_descriptions.append(f"Path {i+1}: {segments_str}")

    paths_text = "\n".join(path_descriptions)

    prompt = f"""Given the following question, rank the paths below by relevance.
Return a JSON array of path numbers (1-indexed) in order of relevance, most relevant first.
Only include paths that are genuinely relevant to answering the question.
Return at most {max_to_return} path numbers.

Question: {params.user_question}

Paths:
{paths_text}

Return ONLY a JSON array of integers, e.g. [3, 1, 5]. No other text."""

    # Get LLM provider from context
    llm = graphrag_context.llm_provider
    if llm is None:
        logger.warning("Subgraph.AgentPath: No LLM provider, returning all paths truncated")
        return SubgraphAgentPathOutputs(relevant_paths=params.candidate_paths[:max_to_return])

    try:
        response = await llm.aask(prompt)
        # Parse the JSON array from the response
        # Handle cases where LLM wraps in markdown code blocks
        resp_text = response.strip()
        if resp_text.startswith("```"):
            resp_text = resp_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        ranked_indices = json.loads(resp_text)

        if not isinstance(ranked_indices, list):
            raise ValueError(f"Expected list, got {type(ranked_indices)}")

        relevant_paths = []
        for idx in ranked_indices[:max_to_return]:
            # Convert 1-indexed to 0-indexed
            path_idx = int(idx) - 1
            if 0 <= path_idx < len(params.candidate_paths):
                relevant_paths.append(params.candidate_paths[path_idx])

        logger.info(f"Subgraph.AgentPath: LLM selected {len(relevant_paths)} relevant paths")
        return SubgraphAgentPathOutputs(relevant_paths=relevant_paths)

    except Exception as e:
        logger.error(f"Subgraph.AgentPath: LLM ranking failed: {e}", exc_info=True)
        # Fallback: return first max_to_return paths
        return SubgraphAgentPathOutputs(relevant_paths=params.candidate_paths[:max_to_return])
