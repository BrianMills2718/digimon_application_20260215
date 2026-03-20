"""Benchmark helpers for consuming persisted graph build manifests.

These helpers keep benchmark-time graph capability checks lightweight and
truthful. The benchmark harness should filter tools from the persisted manifest
instead of re-deriving graph richness from scattered config flags and files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from Core.Schema.GraphBuildManifest import GraphBuildManifest, GraphTopologyKind

_ENTITY_GRAPH_ONLY_TOOL_NAMES = {
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
    "chunk_get_text_by_entity_ids",
    "search_then_expand_onehop",
    "subgraph_khop_paths",
    "subgraph_steiner_tree",
    "meta_pcst_optimize",
}
_COMMUNITY_TOOL_NAMES = {"community_from_entity", "community_from_level"}
_ENTITY_DESCRIPTION_TOOL_NAMES = {"entity_tfidf"}
_RELATION_TEXT_TOOL_NAMES = {"relationship_vdb_search"}
_ENTITY_PROVENANCE_TOOL_NAMES = {"chunk_occurrence", "chunk_get_text_by_entity_ids"}
_RELATION_PROVENANCE_TOOL_NAMES = {"chunk_from_relationships"}


def load_required_graph_manifest(
    *,
    dataset_name: str,
    graph_type: str,
    working_dir: str,
) -> GraphBuildManifest:
    """Load the persisted build manifest for a dataset/graph type pair.

    This fails loudly if the manifest is missing because benchmark-time tool
    availability should be driven by an explicit build artifact, not by guesswork.
    """

    artifact_dir = Path(working_dir) / dataset_name / graph_type
    return GraphBuildManifest.load_from_dir(artifact_dir)


def filter_tool_names_by_graph_manifest(
    tool_names: Iterable[str],
    manifest: GraphBuildManifest,
) -> list[str]:
    """Return the subset of tool names that the manifest says are applicable."""

    allowed = list(tool_names)
    allowed_set = set(allowed)

    if manifest.topology_kind is not GraphTopologyKind.ENTITY:
        allowed_set -= _ENTITY_GRAPH_ONLY_TOOL_NAMES

    if "description" not in manifest.node_fields:
        allowed_set -= _ENTITY_DESCRIPTION_TOOL_NAMES

    edge_text_fields = {"relation_name", "description", "keywords"}
    if not edge_text_fields.intersection(manifest.edge_fields):
        allowed_set -= _RELATION_TEXT_TOOL_NAMES

    if not manifest.artifacts.entity_chunk_provenance:
        allowed_set -= _ENTITY_PROVENANCE_TOOL_NAMES

    if not manifest.artifacts.relationship_chunk_provenance:
        allowed_set -= _RELATION_PROVENANCE_TOOL_NAMES

    if not manifest.artifacts.communities:
        allowed_set -= _COMMUNITY_TOOL_NAMES

    return [tool_name for tool_name in allowed if tool_name in allowed_set]
