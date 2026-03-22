"""Unit tests for shared benchmark-mode tool-surface filtering."""

from __future__ import annotations

from Core.Common.benchmark_tool_modes import filter_tool_names_for_benchmark_mode


def test_filter_tool_names_for_benchmark_mode_leaves_unrestricted_modes_unchanged() -> None:
    """Modes without an explicit whitelist should preserve the incoming tool order."""

    tool_names = ["entity_string_search", "chunk_text_search", "submit_answer"]

    assert filter_tool_names_for_benchmark_mode(tool_names, "hybrid") == tool_names


def test_filter_tool_names_for_benchmark_mode_applies_baseline_whitelist() -> None:
    """Baseline mode should expose only non-graph retrieval plus submission tools."""

    filtered = filter_tool_names_for_benchmark_mode(
        [
            "entity_string_search",
            "chunk_text_search",
            "chunk_vdb_search",
            "submit_answer",
            "list_available_resources",
        ],
        "baseline",
    )

    assert filtered == [
        "chunk_text_search",
        "chunk_vdb_search",
        "submit_answer",
        "list_available_resources",
    ]


def test_filter_tool_names_for_benchmark_mode_applies_fixed_graph_whitelist() -> None:
    """Fixed-graph mode should expose only the intended narrow graph pipeline."""

    filtered = filter_tool_names_for_benchmark_mode(
        [
            "entity_string_search",
            "entity_neighborhood",
            "entity_profile",
            "chunk_vdb_search",
            "chunk_text_search",
            "chunk_get_text_by_chunk_ids",
            "list_available_resources",
            "submit_answer",
        ],
        "fixed_graph",
    )

    assert filtered == [
        "entity_string_search",
        "entity_neighborhood",
        "entity_profile",
        "chunk_text_search",
        "chunk_get_text_by_chunk_ids",
        "list_available_resources",
        "submit_answer",
    ]
