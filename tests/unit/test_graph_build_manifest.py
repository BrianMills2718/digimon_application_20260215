"""Regression tests for graph build manifest derivation and persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from Config.GraphConfig import GraphConfig
from Core.Schema.GraphBuildManifest import (
    GraphBuildManifest,
    GraphProfile,
    GraphTopologyKind,
    write_graph_build_manifest,
)


def test_entity_graph_manifest_infers_kg_profile_for_minimal_config() -> None:
    """Minimal ER graph config should produce a KG-style manifest."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(),
    )

    assert manifest.topology_kind is GraphTopologyKind.ENTITY
    assert manifest.graph_profile is GraphProfile.KG
    assert manifest.node_fields == ["entity_name", "source_id"]
    assert manifest.edge_fields == ["src_id", "tgt_id", "weight", "source_id"]
    assert manifest.artifacts.entity_chunk_provenance is True
    assert manifest.artifacts.relationship_chunk_provenance is True


def test_entity_graph_manifest_infers_rkg_profile_when_keywords_enabled() -> None:
    """Keyword-rich config should advertise the richest available entity-graph profile."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(
            enable_entity_type=True,
            enable_entity_description=True,
            enable_edge_name=True,
            enable_edge_description=True,
            enable_edge_keywords=True,
            enable_chunk_cooccurrence=True,
            use_community=True,
        ),
    )

    assert manifest.graph_profile is GraphProfile.RKG
    assert manifest.node_fields == ["entity_name", "source_id", "entity_type", "description"]
    assert manifest.edge_fields == [
        "src_id",
        "tgt_id",
        "weight",
        "source_id",
        "relation_name",
        "description",
        "keywords",
    ]
    assert manifest.artifacts.cooccurrence_edges is True
    assert manifest.artifacts.communities is True


def test_non_entity_graph_manifest_uses_topology_specific_profile() -> None:
    """Passage and tree builds should not masquerade as KG/TKG/RKG profiles."""

    passage_manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="passage_graph",
        graph_config=GraphConfig(type="passage_graph"),
    )
    tree_manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="tree_graph",
        graph_config=GraphConfig(type="tree_graph"),
    )

    assert passage_manifest.topology_kind is GraphTopologyKind.PASSAGE
    assert passage_manifest.graph_profile is GraphProfile.PASSAGE
    assert tree_manifest.topology_kind is GraphTopologyKind.TREE
    assert tree_manifest.graph_profile is GraphProfile.TREE


def test_write_graph_build_manifest_persists_json_to_existing_artifact_dir(tmp_path: Path) -> None:
    """Manifest persistence should write a stable JSON artifact beside the graph output."""

    manifest_path = write_graph_build_manifest(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(enable_edge_name=True),
        artifact_path=str(tmp_path),
    )

    loaded = GraphBuildManifest.load_from_dir(tmp_path)

    assert Path(manifest_path).exists()
    assert loaded.dataset_name == "MuSiQue"
    assert loaded.edge_fields == ["src_id", "tgt_id", "weight", "source_id", "relation_name"]


def test_write_graph_build_manifest_fails_loudly_when_artifact_dir_missing(tmp_path: Path) -> None:
    """A successful build must have a real artifact directory before manifest persistence."""

    missing_dir = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        write_graph_build_manifest(
            dataset_name="MuSiQue",
            graph_type="er_graph",
            graph_config=GraphConfig(),
            artifact_path=str(missing_dir),
        )
