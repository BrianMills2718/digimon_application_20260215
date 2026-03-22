"""Unit tests for benchmark-time graph-manifest loading and tool filtering."""

from __future__ import annotations

from pathlib import Path

import pytest

from Config.GraphConfig import GraphConfig
from Core.Common.tool_applicability import (
    RuntimeResourceSnapshot,
    ToolApplicabilityStatus,
)
from Core.Schema.GraphBuildManifest import GraphBuildManifest
from eval.graph_manifest import (
    build_runtime_resource_snapshot_from_operator_context,
    evaluate_tool_names_by_graph_manifest,
    filter_tool_names_by_graph_manifest,
    load_required_graph_manifest,
)


def test_filter_tool_names_by_graph_manifest_keeps_degraded_tools_but_hides_unavailable_ones() -> None:
    """Soft-preference gaps should degrade tools, while hard gaps should hide them."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(),
    )
    runtime_resources = RuntimeResourceSnapshot(
        graph_loaded=True,
        doc_store_available=True,
    )
    tool_names = [
        "entity_string_search",
        "entity_tfidf",
        "relationship_vdb_search",
        "chunk_from_relationships",
        "chunk_occurrence",
        "chunk_text_search",
    ]
    decisions = evaluate_tool_names_by_graph_manifest(
        tool_names,
        manifest,
        runtime_resources,
    )
    decision_by_name = {decision.tool_name: decision for decision in decisions}

    filtered = filter_tool_names_by_graph_manifest(
        tool_names,
        manifest,
        runtime_resources,
    )

    assert "entity_string_search" in filtered
    assert "entity_tfidf" in filtered
    assert "chunk_from_relationships" in filtered
    assert "chunk_occurrence" in filtered
    assert "chunk_text_search" in filtered
    assert "relationship_vdb_search" not in filtered
    assert decision_by_name["entity_string_search"].status is ToolApplicabilityStatus.AVAILABLE
    assert decision_by_name["entity_tfidf"].status is ToolApplicabilityStatus.DEGRADED
    assert decision_by_name["relationship_vdb_search"].status is ToolApplicabilityStatus.UNAVAILABLE


def test_entity_resolve_names_to_ids_is_available_but_degraded_without_entity_vdb() -> None:
    """Exact graph matching should keep entity resolution available without VDB support."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(),
    )

    decisions = evaluate_tool_names_by_graph_manifest(
        ["entity_resolve_names_to_ids"],
        manifest,
        RuntimeResourceSnapshot(graph_loaded=True),
    )

    assert len(decisions) == 1
    assert decisions[0].tool_name == "entity_resolve_names_to_ids"
    assert decisions[0].status is ToolApplicabilityStatus.DEGRADED
    assert "artifact=entity_vdb" in decisions[0].missing_soft_preferences
    assert "runtime=entity_vdb_loaded" in decisions[0].missing_soft_preferences


def test_filter_tool_names_by_graph_manifest_handles_generator_inputs() -> None:
    """Filtering helpers should materialize iterables before multiple passes."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(),
    )

    filtered = filter_tool_names_by_graph_manifest(
        (
            tool_name
            for tool_name in [
                "entity_string_search",
                "chunk_text_search",
                "relationship_vdb_search",
            ]
        ),
        manifest,
        RuntimeResourceSnapshot(
            graph_loaded=True,
            doc_store_available=True,
        ),
    )

    assert filtered == [
        "entity_string_search",
        "chunk_text_search",
    ]


def test_entity_ppr_stays_available_without_sparse_matrices() -> None:
    """Direct graph PPR should not be hidden just because sparse matrices are absent."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="er_graph",
        graph_config=GraphConfig(),
    )

    decisions = evaluate_tool_names_by_graph_manifest(
        ["entity_ppr"],
        manifest,
        RuntimeResourceSnapshot(graph_loaded=True),
    )

    assert len(decisions) == 1
    assert decisions[0].status is ToolApplicabilityStatus.AVAILABLE


def test_filter_tool_names_by_graph_manifest_removes_entity_graph_tools_for_passage_build() -> None:
    """Passage builds should not expose entity-graph traversal tools."""

    manifest = GraphBuildManifest.from_graph_config(
        dataset_name="MuSiQue",
        graph_type="passage_graph",
        graph_config=GraphConfig(type="passage_graph"),
    )
    runtime_resources = RuntimeResourceSnapshot(
        graph_loaded=True,
        doc_store_available=True,
    )

    filtered = filter_tool_names_by_graph_manifest(
        [
            "entity_string_search",
            "relationship_onehop",
            "chunk_text_search",
            "chunk_vdb_search",
        ],
        manifest,
        runtime_resources,
    )

    assert filtered == ["chunk_text_search"]


def test_build_runtime_resource_snapshot_from_operator_context_reads_loaded_resources() -> None:
    """OperatorContext-like objects should translate cleanly into runtime snapshots."""

    class _StubOperatorContext:
        """Minimal operator-context stub for runtime resource testing."""

        def __init__(self) -> None:
            self.graph = object()
            self.doc_chunks = object()
            self.entities_vdb = object()
            self.relations_vdb = None
            self.chunks_vdb = object()
            self.community = None
            self.llm = object()
            self.sparse_matrices = {"entity_to_rel": object(), "rel_to_chunk": object()}

    snapshot = build_runtime_resource_snapshot_from_operator_context(
        _StubOperatorContext()
    )

    assert snapshot == RuntimeResourceSnapshot(
        graph_loaded=True,
        doc_store_available=True,
        entity_vdb_loaded=True,
        relationship_vdb_loaded=False,
        chunk_vdb_loaded=True,
        sparse_matrices_loaded=True,
        communities_loaded=False,
        llm_available=True,
    )


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
