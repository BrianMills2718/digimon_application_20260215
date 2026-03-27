"""Unit tests for semantic-plan query rewriting in benchmark mode."""

from __future__ import annotations

import digimon_mcp_stdio_server as dms


def setup_function() -> None:
    """Reset question-local MCP state before each test."""
    dms._reset_chunk_dedup()


def teardown_function() -> None:
    """Reset question-local MCP state after each test."""
    dms._reset_chunk_dedup()


def _prime_lady_godiva_plan() -> None:
    """Seed semantic-plan globals with a two-atom Lady Godiva example."""
    dms._current_question = "When was Lady Godiva's birthplace abolished?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": "What is Lady Godiva's birthplace?",
                    "depends_on": [],
                    "operation": "lookup",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "When was that birthplace abolished?",
                    "depends_on": ["a1"],
                    "operation": "temporal",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a1", "content": "What is Lady Godiva's birthplace?", "status": "in_progress"},
            {"id": "a2", "content": "When was that birthplace abolished?", "status": "pending"},
        ]
    )


def test_rewrites_full_question_to_active_atom_query() -> None:
    """Full-question retrieval queries should collapse to the active atom."""
    _prime_lady_godiva_plan()

    effective, contract = dms._build_retrieval_query_contract(
        "When was Lady Godiva's birthplace abolished?",
        tool_name="chunk_text_search",
    )

    assert contract["active_atom_id"] == "a1"
    assert contract["rewritten"] is True
    assert "Lady Godiva" in effective
    assert "abolished" not in effective.lower()


def test_forwards_done_atom_answer_into_dependent_query() -> None:
    """Dependent atoms should inherit resolved upstream values."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"

    effective, contract = dms._build_retrieval_query_contract(
        "When was Lady Godiva's birthplace abolished?",
        tool_name="chunk_text_search",
    )

    assert contract["active_atom_id"] == "a2"
    assert contract["dependency_values_used"] == ["Mercia"]
    assert "Mercia" in effective
    assert "abolished" in effective.lower()


def test_extracts_done_atom_value_from_content_arrow_notation() -> None:
    """TODO content should still be usable when agent encodes result inline."""
    _prime_lady_godiva_plan()
    dms._todos[0] = {
        "id": "a1",
        "content": "What is Lady Godiva's birthplace? => Mercia",
        "status": "done",
    }
    dms._todos[1]["status"] = "in_progress"

    effective, contract = dms._build_retrieval_query_contract(
        "",
        tool_name="entity_vdb_search",
    )

    assert contract["dependency_values_used"] == ["Mercia"]
    assert effective.startswith("Mercia")


def test_extract_todo_result_value_prefers_structured_answer_field() -> None:
    """Resolved values should come from explicit TODO answer fields when present."""
    value = dms._extract_todo_result_value(
        {
            "id": "a1",
            "content": "What is Lady Godiva's birthplace?",
            "status": "done",
            "answer": "Mercia",
            "evidence_refs": ["chunk_12"],
        }
    )

    assert value == "Mercia"
