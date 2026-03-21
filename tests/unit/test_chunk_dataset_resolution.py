"""Regression tests for chunk-grounding dataset resolution."""

from __future__ import annotations

from types import SimpleNamespace

from Core.AgentTools.chunk_tools import _resolve_chunk_dataset_name


def test_resolve_chunk_dataset_name_prefers_graph_source_dataset() -> None:
    """Aliased graph artifacts should ground chunks from the recorded source dataset."""

    graph_instance = SimpleNamespace(source_dataset_name="MuSiQue")

    resolved = _resolve_chunk_dataset_name(
        graph_instance,
        "MuSiQue_tkg_smoke_ERGraph",
    )

    assert resolved == "MuSiQue"


def test_resolve_chunk_dataset_name_falls_back_to_graph_id_suffix_stripping() -> None:
    """Legacy graphs should still resolve chunk datasets from their graph IDs."""

    graph_instance = SimpleNamespace()

    resolved = _resolve_chunk_dataset_name(
        graph_instance,
        "Synthetic_Test_ERGraph",
    )

    assert resolved == "Synthetic_Test"
