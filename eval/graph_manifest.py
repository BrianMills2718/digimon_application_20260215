"""Benchmark helpers for consuming persisted graph build manifests.

These helpers now evaluate benchmark tools against both persisted build truth
and live runtime-loaded resources. The goal is to stop hand-maintaining
multiple partial notions of "capability" in the benchmark harness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from Core.Common.tool_applicability import (
    RuntimeResourceSnapshot,
    ToolApplicabilityContract,
    ToolApplicabilityDecision,
    evaluate_tool_applicability,
    runtime_resource_snapshot_from_operator_context,
)
from Core.Schema.GraphBuildManifest import GraphBuildManifest, GraphTopologyKind

_BENCHMARK_TOOL_CONTRACTS: dict[str, ToolApplicabilityContract] = {
    "entity_vdb_search": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("entity_vdb",),
        required_runtime_resources=("graph_loaded", "entity_vdb_loaded"),
    ),
    "entity_string_search": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "entity_neighborhood": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "entity_onehop": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "entity_ppr": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "entity_link": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("entity_vdb",),
        required_runtime_resources=("entity_vdb_loaded",),
        soft_runtime_resources=("graph_loaded",),
    ),
    "entity_resolve_names_to_ids": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
        soft_artifacts=("entity_vdb",),
        soft_runtime_resources=("entity_vdb_loaded",),
    ),
    "entity_profile": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
        soft_node_fields=("entity_type", "description"),
    ),
    "entity_select_candidate": ToolApplicabilityContract(),
    "entity_tfidf": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
        soft_node_fields=("description",),
    ),
    "relationship_onehop": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "relationship_score_aggregator": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("sparse_matrices",),
        required_runtime_resources=("graph_loaded", "sparse_matrices_loaded"),
    ),
    "relationship_vdb_search": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("relationship_vdb",),
        required_runtime_resources=("graph_loaded", "relationship_vdb_loaded"),
        soft_edge_fields=("description", "keywords"),
    ),
    "chunk_from_relationships": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("relationship_chunk_provenance",),
        required_runtime_resources=("graph_loaded", "doc_store_available"),
    ),
    "chunk_occurrence": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("entity_chunk_provenance",),
        required_runtime_resources=("graph_loaded", "doc_store_available"),
    ),
    "chunk_get_text_by_chunk_ids": ToolApplicabilityContract(
        required_runtime_resources=("doc_store_available",),
    ),
    "chunk_get_text_by_entity_ids": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("entity_chunk_provenance",),
        required_runtime_resources=("graph_loaded", "doc_store_available"),
    ),
    "extract_date_mentions": ToolApplicabilityContract(),
    "extract_date_mentions_from_artifacts": ToolApplicabilityContract(),
    "chunk_text_search": ToolApplicabilityContract(
        required_runtime_resources=("doc_store_available",),
    ),
    "chunk_vdb_search": ToolApplicabilityContract(
        required_artifacts=("chunk_vdb",),
        required_runtime_resources=("chunk_vdb_loaded",),
    ),
    "search_then_expand_onehop": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded", "doc_store_available"),
    ),
    "chunk_aggregator": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("sparse_matrices",),
        required_runtime_resources=("graph_loaded", "doc_store_available", "sparse_matrices_loaded"),
    ),
    "list_available_resources": ToolApplicabilityContract(),
    "subgraph_khop_paths": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "subgraph_steiner_tree": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_runtime_resources=("graph_loaded",),
    ),
    "meta_pcst_optimize": ToolApplicabilityContract(),
    "community_from_entity": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("communities",),
        required_runtime_resources=("graph_loaded", "communities_loaded"),
    ),
    "community_from_level": ToolApplicabilityContract(
        required_topology_kinds=(GraphTopologyKind.ENTITY,),
        required_artifacts=("communities",),
        required_runtime_resources=("graph_loaded", "communities_loaded"),
    ),
    "semantic_plan": ToolApplicabilityContract(),
    "todo_write": ToolApplicabilityContract(),
    "bridge_disambiguate": ToolApplicabilityContract(),
    "submit_answer": ToolApplicabilityContract(),
}


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


def build_runtime_resource_snapshot_from_operator_context(ctx: Any) -> RuntimeResourceSnapshot:
    """Convert an OperatorContext-like object into benchmark applicability state."""

    return runtime_resource_snapshot_from_operator_context(ctx)


def evaluate_tool_names_by_graph_manifest(
    tool_names: Iterable[str],
    manifest: GraphBuildManifest,
    runtime_resources: RuntimeResourceSnapshot,
) -> list[ToolApplicabilityDecision]:
    """Evaluate benchmark tool names against build and runtime truth."""

    decisions: list[ToolApplicabilityDecision] = []
    for tool_name in tool_names:
        contract = _BENCHMARK_TOOL_CONTRACTS.get(tool_name, ToolApplicabilityContract())
        decisions.append(
            evaluate_tool_applicability(
                tool_name=tool_name,
                contract=contract,
                manifest=manifest,
                runtime_resources=runtime_resources,
            )
        )
    return decisions


def filter_tool_names_by_graph_manifest(
    tool_names: Iterable[str],
    manifest: GraphBuildManifest,
    runtime_resources: RuntimeResourceSnapshot,
) -> list[str]:
    """Return the subset of tool names whose hard requirements are satisfied."""

    decisions = evaluate_tool_names_by_graph_manifest(
        tool_names,
        manifest,
        runtime_resources,
    )
    allowed_set = {decision.tool_name for decision in decisions if decision.is_usable}
    return [tool_name for tool_name in tool_names if tool_name in allowed_set]
