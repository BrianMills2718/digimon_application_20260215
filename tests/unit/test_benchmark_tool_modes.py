"""Unit tests for shared benchmark-mode tool-surface filtering."""

from __future__ import annotations

import json

from Core.Common.benchmark_tool_modes import filter_tool_names_for_benchmark_mode
from llm_client import MCPAgentResult, MCPToolCallRecord
from eval.run_agent_benchmark import (
    _extract_full_submit_records,
    _atom_lifecycle_provenance,
    _conversation_trace_has_pending_todos,
    _derive_submit_observability,
    _helper_trace_provenance,
    _read_atom_lifecycle_events_since,
    _read_helper_trace_events_since,
    _preserve_terminal_answer_after_submit_validation,
    _submit_tool_call_accepted,
)


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


def test_preserve_terminal_answer_clears_freeform_answer_after_failed_submit() -> None:
    """Rejected submit attempts must not leave behind a scored free-form answer."""
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

    assert _preserve_terminal_answer_after_submit_validation(
        "Saint Joseph of the Fields",
        answer_source="freeform",
        derived_submit=derived,
        submit_forced_accept_on_budget_exhaustion=False,
        finalization_fallback_succeeded=False,
    ) == ""


def test_preserve_terminal_answer_keeps_forced_accept_metadata_answer() -> None:
    """Forced-final acceptance metadata should still produce a scored answer."""
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

    assert _preserve_terminal_answer_after_submit_validation(
        "918",
        answer_source="metadata",
        derived_submit=derived,
        submit_forced_accept_on_budget_exhaustion=True,
        finalization_fallback_succeeded=False,
    ) == "918"


def test_conversation_trace_detects_pending_todos() -> None:
    """Forced-final freeform answers should be suppressible when atoms remain pending."""
    assert _conversation_trace_has_pending_todos(
        [
            {"role": "user", "content": "[TODO_STATE] [TODO: 0/2 done] [ ] a1 | [ ] a2"},
            {"role": "assistant", "content": "Saint Joseph"},
        ]
    )


def test_conversation_trace_ignores_fully_completed_todos() -> None:
    """Completed TODO state should not trigger forced-terminal suppression."""
    assert not _conversation_trace_has_pending_todos(
        [
            {"role": "user", "content": "[TODO_STATE] [TODO: 2/2 done] [x] a1 | [x] a2"},
            {"role": "assistant", "content": "Nazareth"},
        ]
    )


def test_read_helper_trace_events_since_filters_to_current_question(tmp_path) -> None:
    """Helper trace harvesting should ignore unrelated question events."""
    trace_path = tmp_path / "results" / ".helper_decision_trace.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"question": "Question A", "status": "ok", "fallback_used": False}),
                json.dumps({"question": "Question B", "status": "ok", "fallback_used": True}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = _read_helper_trace_events_since(
        project_root=str(tmp_path),
        offset=0,
        question="Question B",
    )

    assert len(events) == 1
    assert events[0]["question"] == "Question B"


def test_helper_trace_provenance_counts_helper_fallbacks() -> None:
    """Helper trace summary should surface nested fallback usage explicitly."""
    provenance = _helper_trace_provenance(
        [
            {
                "requested_model": "gemini/gemini-2.5-flash",
                "resolved_model": "openrouter/openai/gpt-5.4-mini",
                "fallback_used": True,
                "status": "ok",
            },
            {
                "requested_model": "deepseek/deepseek-chat",
                "resolved_model": "deepseek/deepseek-chat",
                "fallback_used": False,
                "status": "error",
            },
        ]
    )

    assert provenance["helper_fallback_used"] is True
    assert provenance["helper_fallback_event_count"] == 1
    assert provenance["helper_error_count"] == 1
    assert provenance["helper_models_used"] == [
        "deepseek/deepseek-chat",
        "gemini/gemini-2.5-flash",
        "openrouter/openai/gpt-5.4-mini",
    ]


def test_derive_submit_observability_surfaces_pending_atoms() -> None:
    """Submit observability should retain pending atom IDs from validator rejections."""
    derived = _derive_submit_observability(
        [
            {
                "tool": "submit_answer",
                "result_preview": json.dumps(
                    {
                        "status": "rejected",
                        "pending_atoms": 2,
                        "pending_ids": ["A1", "A2"],
                        "todo_status_line": "[TODO: 0/2 done] [ ] A1 | [ ] A2",
                        "validation_error": {"reason_code": "pending_atoms"},
                    }
                ),
            }
        ]
    )

    assert derived["submit_answer_succeeded"] is False
    assert derived["submit_pending_atom_count"] == 2
    assert derived["submit_pending_atom_ids"] == ["A1", "A2"]
    assert derived["submit_todo_status_line"] == "[TODO: 0/2 done] [ ] A1 | [ ] A2"


def test_derive_submit_observability_prefers_full_submit_payload_over_truncated_preview() -> None:
    """Full submit payloads should recover pending IDs even when previews are truncated."""
    derived = _derive_submit_observability(
        [
            {
                "tool": "submit_answer",
                "result_preview": '{"status":"rejected","pending_atoms":1,"pending_ids":["A1"]',
                "result_full": json.dumps(
                    {
                        "status": "rejected",
                        "pending_atoms": 1,
                        "pending_ids": ["A1"],
                        "todo_status_line": "[TODO: 1/2 done] [x] A1 | [>] A2",
                        "validation_error": {"reason_code": "pending_atoms"},
                    }
                ),
            }
        ]
    )

    assert derived["submit_pending_atom_count"] == 1
    assert derived["submit_pending_atom_ids"] == ["A1"]


def test_extract_full_submit_records_recovers_untruncated_submit_results() -> None:
    """MCPAgentResult-backed tool records should preserve full submit payloads for diagnosis."""
    raw = MCPAgentResult(
        tool_calls=[
            MCPToolCallRecord(
                server="srv",
                tool="submit_answer",
                arguments={"answer": "12"},
                result=json.dumps(
                    {
                        "status": "rejected",
                        "pending_atoms": 1,
                        "pending_ids": ["a2"],
                        "validation_error": {"reason_code": "pending_atoms"},
                    }
                ),
            )
        ]
    )

    records = _extract_full_submit_records(raw, [])

    assert len(records) == 1
    assert records[0]["tool"] == "submit_answer"
    assert '"pending_ids": ["a2"]' in records[0]["result_full"]


def test_read_atom_lifecycle_events_since_prefers_benchmark_trace_id(tmp_path) -> None:
    """Atom lifecycle harvesting should use benchmark trace IDs when present."""
    trace_path = tmp_path / "results" / ".atom_lifecycle_events.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"question": "Question A", "benchmark_trace_id": "trace-a", "event": "atom_completed"}),
                json.dumps({"question": "Question B", "benchmark_trace_id": "trace-b", "event": "atom_judged_unresolved"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = _read_atom_lifecycle_events_since(
        project_root=str(tmp_path),
        offset=0,
        question="Question A",
        benchmark_trace_id="trace-b",
    )

    assert len(events) == 1
    assert events[0]["benchmark_trace_id"] == "trace-b"


def test_atom_lifecycle_provenance_counts_mutations() -> None:
    """Atom lifecycle summary should expose completion and unresolved counts."""
    provenance = _atom_lifecycle_provenance(
        [
            {"event": "atom_completed", "atom_id": "a1"},
            {"event": "atom_judged_unresolved", "atom_id": "a2"},
            {"event": "atom_manual_rejected", "atom_id": "a2"},
        ]
    )

    assert provenance["atom_lifecycle_event_count"] == 3
    assert provenance["atom_completed_event_count"] == 1
    assert provenance["atom_unresolved_event_count"] == 1
    assert provenance["atom_manual_rejected_event_count"] == 1
