"""Unit tests for benchmark-time graph-manifest loading and tool filtering."""

from __future__ import annotations

from pathlib import Path

import pytest

from Config.GraphConfig import GraphConfig
from Core.Schema.GraphBuildManifest import GraphBuildManifest
from eval.graph_manifest import (
    filter_tool_names_by_graph_manifest,
    load_required_graph_manifest,
)


def test_filter_tool_names_by_graph_manifest_removes_rich_tools_for_minimal_kg() -> None:
    """Minimal KG-style builds should not expose tools needing richer graph text fields."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(),
    )

    filtered = filter_tool_names_by_graph_manifest(
        [
            "entity_string_search",
            "entity_tfidf",
            "relationship_vdb_search",
            "chunk_from_relationships",
            "chunk_occurrence",
            "chunk_text_search",
        ],
        manifest,
    )

    assert "entity_string_search" in filtered
    assert "chunk_from_relationships" in filtered
    assert "chunk_occurrence" in filtered
    assert "chunk_text_search" in filtered
    assert "entity_tfidf" not in filtered
    assert "relationship_vdb_search" not in filtered


def test_filter_tool_names_by_graph_manifest_removes_entity_graph_tools_for_passage_build() -> None:
    """Passage builds should not expose entity-graph traversal tools."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="passage_graph",
        graph_config=GraphConfig(type="passage_graph"),
    )

    filtered = filter_tool_names_by_graph_manifest(
        [
            "entity_string_search",
            "relationship_onehop",
            "chunk_text_search",
            "chunk_vdb_search",
        ],
        manifest,
    )

    assert filtered == ["chunk_text_search", "chunk_vdb_search"]


def test_load_required_graph_manifest_reads_persisted_manifest(tmp_path: Path) -> None:
    """Manifest loader should resolve dataset and graph type to the persisted JSON artifact."""

    artifact_dir = tmp_path / "MuSiQue" / "er_graph"
    artifact_dir.mkdir(parents=True)
    GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(enable_edge_name=True),
    ).save_to_dir(artifact_dir)

    loaded = load_required_graph_manifest(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        working_dir=str(tmp_path),
    )

    assert loaded.dataset_name == "MuSiQue"
    assert loaded.graph_type == "er_graph"
    assert "relation_name" in loaded.edge_fields


def test_load_required_graph_manifest_fails_loudly_when_missing(tmp_path: Path) -> None:
    """Benchmarks should not guess graph capabilities when the manifest is missing."""

    with pytest.raises(FileNotFoundError):
        load_required_graph_manifest(
            dataset_name="MuSiQue",
            graph_type="er_graph",
            working_dir=str(tmp_path),
        )
