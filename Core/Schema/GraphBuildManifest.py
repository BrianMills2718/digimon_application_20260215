"""Typed manifest describing what a persisted graph build actually contains.

The benchmark harness and tool exposure layer need a machine-readable source of
truth for graph topology, attribute richness, and derived artifacts. This model
captures that contract and persists it beside graph artifacts so later stages do
not have to guess from filenames or loosely-coupled config flags.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path

from pydantic import BaseModel, Field

from Config.GraphConfig import GraphConfig

MANIFEST_FILE_NAME = "graph_build_manifest.json"


class GraphTopologyKind(str, Enum):
    """Top-level graph topology families supported by DIGIMON."""

    ENTITY = "entity_graph"
    PASSAGE = "passage_graph"
    TREE = "tree_graph"


class GraphProfile(str, Enum):
    """Named attribute profiles for graph builds."""

    KG = "KG"
    TKG = "TKG"
    RKG = "RKG"
    PASSAGE = "PASSAGE"
    TREE = "TREE"


class GraphArtifactFlags(BaseModel):
    """Derived artifacts and enrichments that may exist beside the raw graph."""

    entity_vdb: bool = False
    relationship_vdb: bool = False
    chunk_vdb: bool = False
    sparse_matrices: bool = False
    communities: bool = False
    cooccurrence_edges: bool = False
    centrality_scores: bool = False
    entity_chunk_provenance: bool = False
    relationship_chunk_provenance: bool = False


class GraphConfigSnapshot(BaseModel):
    """Relevant graph-config switches captured with the build."""

    extract_two_step: bool
    enable_entity_type: bool
    enable_entity_description: bool
    enable_edge_name: bool
    enable_edge_description: bool
    enable_edge_keywords: bool
    enable_chunk_cooccurrence: bool
    use_community: bool


class GraphBuildManifest(BaseModel):
    """Persisted description of one graph build and its available capabilities."""

    manifest_version: int = 1
    dataset_name: str
    graph_type: str
    topology_kind: GraphTopologyKind
    graph_profile: GraphProfile
    node_fields: list[str] = Field(default_factory=list)
    edge_fields: list[str] = Field(default_factory=list)
    artifacts: GraphArtifactFlags = Field(default_factory=GraphArtifactFlags)
    config_flags: GraphConfigSnapshot
    generated_at_utc: str

    @classmethod
    def from_graph_config(
        cls,
        *,
        dataset_name: str,
        graph_type: str,
        graph_config: GraphConfig,
    ) -> "GraphBuildManifest":
        """Derive a manifest from the configured graph type and build flags."""

        topology_kind = _infer_topology_kind(graph_type)
        graph_profile = _infer_graph_profile(topology_kind=topology_kind, graph_config=graph_config)
        node_fields = _infer_node_fields(topology_kind=topology_kind, graph_config=graph_config)
        edge_fields = _infer_edge_fields(topology_kind=topology_kind, graph_config=graph_config)
        artifacts = _infer_artifacts(topology_kind=topology_kind, graph_config=graph_config)

        return cls(
            dataset_name=dataset_name,
            graph_type=graph_type,
            topology_kind=topology_kind,
            graph_profile=graph_profile,
            node_fields=node_fields,
            edge_fields=edge_fields,
            artifacts=artifacts,
            config_flags=GraphConfigSnapshot(
                extract_two_step=graph_config.extract_two_step,
                enable_entity_type=graph_config.enable_entity_type,
                enable_entity_description=graph_config.enable_entity_description,
                enable_edge_name=graph_config.enable_edge_name,
                enable_edge_description=graph_config.enable_edge_description,
                enable_edge_keywords=graph_config.enable_edge_keywords,
                enable_chunk_cooccurrence=graph_config.enable_chunk_cooccurrence,
                use_community=graph_config.use_community,
            ),
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    def save_to_dir(self, artifact_dir: str | Path) -> Path:
        """Persist the manifest beside the graph artifacts.

        This fails loudly if the artifact directory does not exist because a
        successful graph build should already have created its output location.
        """

        path = Path(artifact_dir)
        if not path.exists():
            raise FileNotFoundError(f"Artifact directory does not exist: {path}")

        manifest_path = path / MANIFEST_FILE_NAME
        manifest_path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest_path

    @classmethod
    def load_from_dir(cls, artifact_dir: str | Path) -> "GraphBuildManifest":
        """Load a previously persisted manifest from an artifact directory."""

        manifest_path = Path(artifact_dir) / MANIFEST_FILE_NAME
        if not manifest_path.exists():
            raise FileNotFoundError(f"Graph build manifest not found: {manifest_path}")
        return cls.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def write_graph_build_manifest(
    *,
    dataset_name: str,
    graph_type: str,
    graph_config: GraphConfig,
    artifact_path: str,
) -> str:
    """Persist a graph build manifest beside successful graph artifacts.

    The manifest is part of the build contract. If the graph claims success but
    there is no artifact directory to write into, this function fails loudly so
    later retrieval stages do not operate on undocumented graph state.
    """

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name=dataset_name,
        graph_type=graph_type,
        graph_config=graph_config,
    )
    manifest_path = manifest.save_to_dir(artifact_path)
    return str(manifest_path)


def _infer_topology_kind(graph_type: str) -> GraphTopologyKind:
    """Map a DIGIMON graph type string to a topology family."""

    if graph_type in {"er_graph", "rkg_graph"}:
        return GraphTopologyKind.ENTITY
    if graph_type == "passage_graph":
        return GraphTopologyKind.PASSAGE
    if graph_type in {"tree_graph", "tree_graph_balanced"}:
        return GraphTopologyKind.TREE
    raise ValueError(f"Unsupported graph type for manifest inference: {graph_type}")


def _infer_graph_profile(
    *,
    topology_kind: GraphTopologyKind,
    graph_config: GraphConfig,
) -> GraphProfile:
    """Infer the high-level profile name from the topology and build flags."""

    if topology_kind is GraphTopologyKind.PASSAGE:
        return GraphProfile.PASSAGE
    if topology_kind is GraphTopologyKind.TREE:
        return GraphProfile.TREE
    if graph_config.enable_edge_keywords:
        return GraphProfile.RKG
    if (
        graph_config.enable_entity_type
        or graph_config.enable_entity_description
        or graph_config.enable_edge_description
    ):
        return GraphProfile.TKG
    return GraphProfile.KG


def _infer_node_fields(
    *,
    topology_kind: GraphTopologyKind,
    graph_config: GraphConfig,
) -> list[str]:
    """Infer which node fields the graph build is expected to materialize."""

    if topology_kind is GraphTopologyKind.ENTITY:
        fields = ["entity_name", "source_id"]
        if graph_config.enable_entity_type:
            fields.append("entity_type")
        if graph_config.enable_entity_description:
            fields.append("description")
        return fields

    if topology_kind is GraphTopologyKind.PASSAGE:
        return ["entity_name", "description", "source_id"]

    return ["text", "embedding", "children", "layer"]


def _infer_edge_fields(
    *,
    topology_kind: GraphTopologyKind,
    graph_config: GraphConfig,
) -> list[str]:
    """Infer which edge fields the graph build is expected to materialize."""

    if topology_kind is GraphTopologyKind.ENTITY:
        fields = ["src_id", "tgt_id", "weight", "source_id"]
        if graph_config.enable_edge_name:
            fields.append("relation_name")
        if graph_config.enable_edge_description:
            fields.append("description")
        if graph_config.enable_edge_keywords:
            fields.append("keywords")
        return fields

    if topology_kind is GraphTopologyKind.PASSAGE:
        return ["src_id", "tgt_id", "source_id", "relation_name"]

    return ["parent_child"]


def _infer_artifacts(
    *,
    topology_kind: GraphTopologyKind,
    graph_config: GraphConfig,
) -> GraphArtifactFlags:
    """Infer the artifact flags that are created by raw graph construction alone."""

    return GraphArtifactFlags(
        communities=graph_config.use_community,
        cooccurrence_edges=graph_config.enable_chunk_cooccurrence,
        entity_chunk_provenance=topology_kind is GraphTopologyKind.ENTITY,
        relationship_chunk_provenance=topology_kind is GraphTopologyKind.ENTITY,
    )
