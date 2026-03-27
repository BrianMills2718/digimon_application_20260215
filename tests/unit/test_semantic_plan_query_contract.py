"""Unit tests for semantic-plan query rewriting in benchmark mode."""

from __future__ import annotations

import pytest

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
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "When was that birthplace abolished?",
                    "depends_on": ["a1"],
                    "operation": "temporal",
                    "answer_kind": "date",
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


def test_rewrites_off_atom_query_back_to_active_atom() -> None:
    """Guessed downstream bridge terms should not pull retrieval off the current atom."""
    _prime_lady_godiva_plan()

    effective, contract = dms._build_retrieval_query_contract(
        "Lady Godiva birthplace Coventry abolished",
        tool_name="chunk_text_search",
    )

    assert contract["active_atom_id"] == "a1"
    assert "Coventry" not in effective
    assert "abolished" not in effective.lower()


def test_preserves_explicit_entity_resolution_query() -> None:
    """String entity-resolution queries should not be rewritten back to the atom text."""
    _prime_lady_godiva_plan()

    effective, contract = dms._build_retrieval_query_contract(
        "Godiva Countess of Leicester",
        tool_name="entity_search",
    )

    assert contract["active_atom_id"] == "a1"
    assert "Godiva" in effective
    assert "Leicester" in effective
    assert "off_atom_query_rewritten_to_active_atom" not in contract["rewrite_reason"]


def test_apply_atom_completion_update_marks_atom_done_and_promotes_next() -> None:
    """Completing the active atom should advance the next dependency-ready atom."""
    _prime_lady_godiva_plan()

    atom = dms._semantic_plan_atom_by_id("a1")
    todo = dms._todo_item_by_id("a1")
    assert atom is not None
    assert todo is not None

    update = dms._apply_atom_completion_update(
        atom,
        todo,
        {
            "resolved_value": "Mercia",
            "confidence": 0.98,
            "evidence_refs": ["chunk_84"],
            "rationale": "Explicit bridge entity found.",
            "tool_name": "relationship_search",
            "method": "graph",
        },
    )

    assert todo["status"] == "done"
    assert todo["answer"] == "Mercia"
    assert dms._todo_item_by_id("a2")["status"] == "in_progress"
    assert update["event"] == "atom_completed"
    assert update["next_atom"] == "a2"


@pytest.mark.asyncio
async def test_maybe_complete_active_atom_from_payload_updates_todos(monkeypatch: pytest.MonkeyPatch) -> None:
    """A positive completion decision should update TODO state from tool payload."""
    _prime_lady_godiva_plan()

    captured_events: list[dict[str, object]] = []

    async def _fake_infer(atom, todo, payload, *, tool_name: str, method: str):
        assert atom["atom_id"] == "a1"
        assert todo["status"] == "in_progress"
        assert tool_name == "relationship_search"
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "Mercia",
            "confidence": 0.97,
            "evidence_refs": ["chunk_84"],
            "rationale": "Mercia is the bridge entity needed for the next atom.",
            "tool_name": tool_name,
            "method": method,
        }

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_infer)
    monkeypatch.setattr(dms, "_record_atom_lifecycle_event", lambda event: captured_events.append(dict(event)))

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "relationships": [
                {"src_id": "godiva", "tgt_id": "mercia", "description": "Godiva associated with Mercia"}
            ]
        },
        tool_name="relationship_search",
        method="graph",
    )

    assert update is not None
    assert update["event"] == "atom_completed"
    assert dms._todo_item_by_id("a1")["status"] == "done"
    assert dms._todo_item_by_id("a1")["answer"] == "Mercia"
    assert dms._todo_item_by_id("a2")["status"] == "in_progress"
    assert captured_events[0]["event"] == "atom_completed"


@pytest.mark.asyncio
async def test_unresolved_atom_decision_does_not_advance_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unresolved decision should leave TODO state unchanged."""
    _prime_lady_godiva_plan()

    captured_events: list[dict[str, object]] = []

    async def _fake_infer(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.31,
            "rationale": "Relationship evidence is too weak to infer birthplace.",
            "tool_name": tool_name,
            "method": method,
        }

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_infer)
    monkeypatch.setattr(dms, "_record_atom_lifecycle_event", lambda event: captured_events.append(dict(event)))

    update = await dms._maybe_complete_active_atom_from_payload(
        {"relationships": [{"src_id": "godiva", "tgt_id": "mercia"}]},
        tool_name="relationship_search",
        method="graph",
    )

    assert update is not None
    assert update["event"] == "atom_judged_unresolved"
    assert dms._todo_item_by_id("a1")["status"] == "in_progress"
    assert dms._todo_item_by_id("a2")["status"] == "pending"
    assert captured_events[0]["event"] == "atom_judged_unresolved"


@pytest.mark.asyncio
async def test_bridge_inference_advances_entity_atom(monkeypatch: pytest.MonkeyPatch) -> None:
    """A downstream-compatible bridge candidate should advance the current atom."""
    _prime_lady_godiva_plan()

    captured_events: list[dict[str, object]] = []

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.22,
            "rationale": "No explicit birthplace relation is present.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        assert tool_name == "entity_info"
        assert payload["connected_entities"][:3] == ["leicester", "england", "mercia"]
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "Mercia",
            "confidence": 0.91,
            "evidence_refs": ["entity:godiva", "chunk_84"],
            "rationale": "Mercia is the only connected place that fits the downstream abolition clue.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "bridge_inference",
        }

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)
    monkeypatch.setattr(dms, "_record_atom_lifecycle_event", lambda event: captured_events.append(dict(event)))

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "entity_id": "godiva",
            "canonical_name": "godiva",
            "connected_entities": ["leicester", "england", "mercia"],
            "evidence_refs": ["entity:godiva", "chunk_84"],
        },
        tool_name="entity_info",
        method="profile",
    )

    assert update is not None
    assert update["event"] == "atom_completed"
    assert update["resolution_mode"] == "bridge_inference"
    assert dms._todo_item_by_id("a1")["status"] == "done"
    assert dms._todo_item_by_id("a1")["answer"] == "Mercia"
    assert dms._todo_item_by_id("a2")["status"] == "in_progress"
    assert captured_events[0]["event"] == "atom_completed"


@pytest.mark.asyncio
async def test_entity_search_string_auto_profiles_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    """High-confidence string matches should auto-profile the subject before another free-form turn."""
    _prime_lady_godiva_plan()

    captured_events: list[dict[str, object]] = []

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        assert entity_name == "godiva"
        assert graph_reference_id == "MuSiQue_ERGraph"
        return (
            '{"entity_id":"godiva","canonical_name":"godiva",'
            '"connected_entities":["leicester","england","mercia"],'
            '"evidence_refs":["entity:godiva","chunk_84"]}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        assert tool_name == "entity_info"
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.14,
            "rationale": "Profile alone does not explicitly state birthplace.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        assert payload["connected_entities"][-1] == "mercia"
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "Mercia",
            "confidence": 0.88,
            "evidence_refs": ["entity:godiva", "chunk_84"],
            "rationale": "Mercia is the connected polity that fits the downstream abolition clue.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "bridge_inference",
        }

    monkeypatch.setattr(dms, "entity_profile", _fake_entity_profile)
    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)
    monkeypatch.setattr(dms, "_record_atom_lifecycle_event", lambda event: captured_events.append(dict(event)))

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "matches": [
                {
                    "entity_name": "godiva",
                    "canonical_name": "godiva",
                    "match_score": 94,
                }
            ],
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "dataset_name": "MuSiQue",
        },
        tool_name="entity_search",
        method="string",
    )

    assert update is not None
    assert update["event"] == "atom_completed"
    assert dms._todo_item_by_id("a1")["answer"] == "Mercia"
    assert dms._todo_item_by_id("a2")["status"] == "in_progress"
    assert captured_events[0]["event"] == "atom_completed"
