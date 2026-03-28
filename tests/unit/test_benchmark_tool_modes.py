"""Unit tests for shared benchmark-mode tool-surface filtering."""

from __future__ import annotations

from Core.Common.benchmark_tool_modes import filter_tool_names_for_benchmark_mode
from eval.run_agent_benchmark import _derive_submit_observability, _submit_tool_call_accepted


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


def test_submit_tool_call_accepted_requires_explicit_submitted_status() -> None:
    """Only explicit submit confirmations should count as accepted final answers."""
    assert _submit_tool_call_accepted(
        {"tool": "submit_answer", "result_preview": '{"status": "submitted", "answer": "918"}'}
    )


def test_submit_tool_call_accepted_rejects_pending_atom_errors() -> None:
    """Pending-atom submit rejections must not be counted as successful submits."""
    assert not _submit_tool_call_accepted(
        {
            "tool": "submit_answer",
            "result_preview": (
                '{"error":"Cannot submit","pending_atoms":2,"pending_ids":["A1","A2"]}'
            ),
        }
    )


def test_derive_submit_observability_rejects_failed_submit_calls() -> None:
    """Observed failed submit calls must override any stale success metadata."""
    derived = _derive_submit_observability(
        [
            {
                "tool": "submit_answer",
                "result_preview": (
                    '{"error":"Cannot submit","pending_atoms":2,"pending_ids":["A1","A2"]}'
                ),
            }
        ]
    )

    assert derived["submit_answer_call_count"] == 1
    assert derived["submit_answer_attempted"] is True
    assert derived["submit_answer_succeeded"] is False
    assert derived["submit_validator_accepted"] is False
    assert derived["required_submit_missing"] is True
    assert derived["submit_completion_mode"] == "missing_required_submit"


def test_extract_answer_from_freeform_content_still_returns_last_short_line() -> None:
    """Plain-text fallback extraction should keep working after submit helper edits."""
    from eval.run_agent_benchmark import _extract_answer_from_freeform_content

    assert (
        _extract_answer_from_freeform_content("Reasoning here.\nFinal line answer\n")
        == "Final line answer"
    )
