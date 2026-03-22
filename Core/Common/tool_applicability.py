"""Typed models and evaluation helpers for tool applicability decisions.

This module separates three concerns that were previously conflated during
benchmark-time tool filtering:

- what a graph build produced (`GraphBuildManifest`)
- what resources are currently loaded (`RuntimeResourceSnapshot`)
- what a tool fundamentally requires (`ToolApplicabilityContract`)

The evaluator returns `available`, `degraded`, or `unavailable` so callers can
choose whether to hide only invalid tools or also apply stricter policy later.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from Core.Schema.GraphBuildManifest import GraphBuildManifest
from Core.Schema.GraphBuildTypes import GraphTopologyKind

ArtifactFlagName = Literal[
    "entity_vdb",
    "relationship_vdb",
    "chunk_vdb",
    "sparse_matrices",
    "communities",
    "cooccurrence_edges",
    "centrality_scores",
    "entity_chunk_provenance",
    "relationship_chunk_provenance",
]

RuntimeResourceName = Literal[
    "graph_loaded",
    "doc_store_available",
    "entity_vdb_loaded",
    "relationship_vdb_loaded",
    "chunk_vdb_loaded",
    "sparse_matrices_loaded",
    "communities_loaded",
    "llm_available",
]


class ToolApplicabilityStatus(str, Enum):
    """High-level applicability outcome for a tool on one build/runtime pair."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class RuntimeResourceSnapshot(BaseModel):
    """Runtime-loaded resources that may or may not be available right now."""

    graph_loaded: bool = False
    doc_store_available: bool = False
    entity_vdb_loaded: bool = False
    relationship_vdb_loaded: bool = False
    chunk_vdb_loaded: bool = False
    sparse_matrices_loaded: bool = False
    communities_loaded: bool = False
    llm_available: bool = False


class ToolApplicabilityContract(BaseModel):
    """Typed hard and soft requirements for one retrieval tool surface."""

    required_topology_kinds: tuple[GraphTopologyKind, ...] = Field(default_factory=tuple)
    required_node_fields: tuple[str, ...] = Field(default_factory=tuple)
    required_edge_fields: tuple[str, ...] = Field(default_factory=tuple)
    required_artifacts: tuple[ArtifactFlagName, ...] = Field(default_factory=tuple)
    required_runtime_resources: tuple[RuntimeResourceName, ...] = Field(default_factory=tuple)
    soft_node_fields: tuple[str, ...] = Field(default_factory=tuple)
    soft_edge_fields: tuple[str, ...] = Field(default_factory=tuple)
    soft_artifacts: tuple[ArtifactFlagName, ...] = Field(default_factory=tuple)
    soft_runtime_resources: tuple[RuntimeResourceName, ...] = Field(default_factory=tuple)


class ToolApplicabilityDecision(BaseModel):
    """Applicability outcome plus the missing requirements that explain it."""

    tool_name: str
    status: ToolApplicabilityStatus
    missing_hard_requirements: list[str] = Field(default_factory=list)
    missing_soft_preferences: list[str] = Field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """Return whether this tool should remain exposed under default policy."""

        return self.status is not ToolApplicabilityStatus.UNAVAILABLE


def runtime_resource_snapshot_from_operator_context(ctx: Any) -> RuntimeResourceSnapshot:
    """Build a runtime snapshot from an OperatorContext-like object.

    The caller is responsible for constructing the dataset-specific operator
    context. This helper only translates the loaded resources into a typed
    snapshot so benchmark and MCP surfaces can reason about them consistently.
    """

    sparse_matrices = getattr(ctx, "sparse_matrices", None) or {}
    sparse_matrices_loaded = (
        isinstance(sparse_matrices, dict)
        and "entity_to_rel" in sparse_matrices
        and "rel_to_chunk" in sparse_matrices
    )
    return RuntimeResourceSnapshot(
        graph_loaded=getattr(ctx, "graph", None) is not None,
        doc_store_available=getattr(ctx, "doc_chunks", None) is not None,
        entity_vdb_loaded=getattr(ctx, "entities_vdb", None) is not None,
        relationship_vdb_loaded=getattr(ctx, "relations_vdb", None) is not None,
        chunk_vdb_loaded=getattr(ctx, "chunks_vdb", None) is not None,
        sparse_matrices_loaded=sparse_matrices_loaded,
        communities_loaded=getattr(ctx, "community", None) is not None,
        llm_available=getattr(ctx, "llm", None) is not None,
    )


def evaluate_tool_applicability(
    *,
    tool_name: str,
    contract: ToolApplicabilityContract,
    manifest: GraphBuildManifest,
    runtime_resources: RuntimeResourceSnapshot,
) -> ToolApplicabilityDecision:
    """Evaluate one tool contract against build truth and runtime truth."""

    missing_hard: list[str] = []
    missing_soft: list[str] = []

    if (
        contract.required_topology_kinds
        and manifest.topology_kind not in contract.required_topology_kinds
    ):
        allowed = ", ".join(kind.value for kind in contract.required_topology_kinds)
        missing_hard.append(f"topology in {{{allowed}}}")

    node_fields = set(manifest.node_fields)
    edge_fields = set(manifest.edge_fields)

    for field_name in contract.required_node_fields:
        if field_name not in node_fields:
            missing_hard.append(f"node_field={field_name}")
    for field_name in contract.required_edge_fields:
        if field_name not in edge_fields:
            missing_hard.append(f"edge_field={field_name}")
    for artifact_name in contract.required_artifacts:
        if not bool(getattr(manifest.artifacts, artifact_name)):
            missing_hard.append(f"artifact={artifact_name}")
    for resource_name in contract.required_runtime_resources:
        if not bool(getattr(runtime_resources, resource_name)):
            missing_hard.append(f"runtime={resource_name}")

    for field_name in contract.soft_node_fields:
        if field_name not in node_fields:
            missing_soft.append(f"node_field={field_name}")
    for field_name in contract.soft_edge_fields:
        if field_name not in edge_fields:
            missing_soft.append(f"edge_field={field_name}")
    for artifact_name in contract.soft_artifacts:
        if not bool(getattr(manifest.artifacts, artifact_name)):
            missing_soft.append(f"artifact={artifact_name}")
    for resource_name in contract.soft_runtime_resources:
        if not bool(getattr(runtime_resources, resource_name)):
            missing_soft.append(f"runtime={resource_name}")

    if missing_hard:
        status = ToolApplicabilityStatus.UNAVAILABLE
    elif missing_soft:
        status = ToolApplicabilityStatus.DEGRADED
    else:
        status = ToolApplicabilityStatus.AVAILABLE

    return ToolApplicabilityDecision(
        tool_name=tool_name,
        status=status,
        missing_hard_requirements=missing_hard,
        missing_soft_preferences=missing_soft,
    )
