"""Regression tests for graph build manifest derivation and persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from Config.GraphConfig import GraphConfig
from Core.Schema.GraphBuildManifest import (
    GraphBuildManifest,
    write_graph_build_manifest,
)
from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode, GraphTopologyKind


def test_entity_graph_manifest_infers_legacy_minimal_fields_for_default_config() -> None:
    """Default config should preserve the current minimal legacy field surface."""

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
    assert manifest.schema_contract.mode is GraphSchemaMode.OPEN
    assert manifest.source_dataset_name == "MuSiQue"
    assert manifest.available_input_chunk_count is None
    assert manifest.selected_input_chunk_count is None
    assert manifest.requested_input_chunk_limit is None


def test_entity_graph_manifest_uses_explicit_kg_profile_contract() -> None:
    """Explicit KG profile should advertise the profile-locked relation-name surface."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(graph_profile=GraphProfile.KG),
    )

    assert manifest.graph_profile is GraphProfile.KG
    assert manifest.config_flags.extract_two_step is True
    assert manifest.config_flags.strict_extraction_slot_discipline is False
    assert manifest.edge_fields == ["src_id", "tgt_id", "weight", "source_id", "relation_name"]


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


def test_entity_graph_manifest_persists_explicit_schema_contract() -> None:
    """Manifest should record the declared schema guidance used for the build."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(
            graph_profile=GraphProfile.TKG,
            schema_mode=GraphSchemaMode.GUIDED,
            schema_entity_types=["person", "organization"],
            schema_relation_types=["employed_by", "located_in"],
        ),
    )

    assert manifest.graph_profile is GraphProfile.TKG
    assert manifest.schema_contract.mode is GraphSchemaMode.GUIDED
    assert manifest.schema_contract.entity_types == ["person", "organization"]
    assert manifest.schema_contract.relation_types == ["employed_by", "located_in"]


def test_entity_graph_manifest_persists_strict_slot_discipline_flag() -> None:
    """Manifest config flags should record the stricter extraction prompt contract."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(
            graph_profile=GraphProfile.TKG,
            strict_extraction_slot_discipline=True,
        ),
    )

    assert manifest.config_flags.strict_extraction_slot_discipline is True


def test_entity_graph_manifest_persists_grounded_entity_preference_flag() -> None:
    """Manifest config flags should record the grounded-entity prompt preference."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(
            graph_profile=GraphProfile.TKG,
            prefer_grounded_named_entities=True,
        ),
    )

    assert manifest.config_flags.prefer_grounded_named_entities is True


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
        source_dataset_name="MuSiQue_source",
        available_input_chunk_count=100,
        selected_input_chunk_count=25,
        requested_input_chunk_limit=25,
    )

    loaded = GraphBuildManifest.load_from_dir(tmp_path)

    assert Path(manifest_path).exists()
    assert loaded.dataset_name == "MuSiQue"
    assert loaded.source_dataset_name == "MuSiQue_source"
    assert loaded.edge_fields == ["src_id", "tgt_id", "weight", "source_id", "relation_name"]
    assert loaded.available_input_chunk_count == 100
    assert loaded.selected_input_chunk_count == 25
    assert loaded.requested_input_chunk_limit == 25


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
