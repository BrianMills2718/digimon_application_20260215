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


def test_normalize_semantic_plan_language_rewrites_entity_identified_placeholder() -> None:
    """Semantic-plan output should rewrite synthetic dependency placeholders into readable atoms."""
    plan = {
        "final_answer_kind": "date",
        "atoms": [
            {
                "atom_id": "a1",
                "sub_question": "What is Lady Godiva's birthplace?",
                "operation": "lookup",
                "answer_kind": "entity",
                "output_var": "birthplace",
                "depends_on": [],
                "done_criteria": "Find Lady Godiva's birthplace.",
            },
            {
                "atom_id": "a2",
                "sub_question": "When was the entity identified as 'birthplace' abolished?",
                "operation": "temporal",
                "answer_kind": "date",
                "output_var": "abolished_date",
                "depends_on": ["a1"],
                "done_criteria": "Find when the entity identified as 'birthplace' was abolished.",
            },
        ],
    }

    normalized = dms._normalize_semantic_plan_language(plan)

    assert normalized["atoms"][1]["sub_question"] == "When was that birthplace abolished?"
    assert normalized["atoms"][1]["done_criteria"] == "Find when that birthplace was abolished."


def test_normalize_semantic_plan_language_rewrites_dollar_placeholder() -> None:
    """Dollar-prefixed output vars should also normalize into readable dependent phrasing."""
    plan = {
        "final_answer_kind": "date",
        "atoms": [
            {
                "atom_id": "a1",
                "sub_question": "What is Lady Godiva's birthplace?",
                "operation": "lookup",
                "answer_kind": "entity",
                "output_var": "birthplace",
                "depends_on": [],
                "done_criteria": "Find Lady Godiva's birthplace.",
            },
            {
                "atom_id": "a2",
                "sub_question": "When was $birthplace abolished?",
                "operation": "temporal",
                "answer_kind": "date",
                "output_var": "abolished_date",
                "depends_on": ["a1"],
                "done_criteria": "Find when $birthplace was abolished.",
            },
        ],
    }

    normalized = dms._normalize_semantic_plan_language(plan)

    assert normalized["atoms"][1]["sub_question"] == "When was that birthplace abolished?"
    assert normalized["atoms"][1]["done_criteria"] == "Find when that birthplace was abolished."


def test_pending_todo_ids_for_submit_reports_unfinished_atoms() -> None:
    """Final submission should stay blocked until all semantic-plan atoms are done."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"

    assert dms._pending_todo_ids_for_submit() == ["a2"]


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


def test_best_entity_search_match_for_atom_prefers_subject_overlap() -> None:
    """Subject-resolution should prefer Godiva over lexical distractors like Leicester."""
    _prime_lady_godiva_plan()

    best = dms._best_entity_search_match_for_atom(
        {
            "matches": [
                {"entity_name": "leicester", "match_score": 99},
                {"entity_name": "birthplace", "match_score": 99},
                {"entity_name": "godiva", "match_score": 97},
            ]
        },
        atom=dms._semantic_plan_atom_by_id("a1"),
    )

    assert best is not None
    assert best["entity_name"] == "godiva"


def test_best_entity_search_match_for_atom_ignores_title_only_match() -> None:
    """Title-only matches like 'lady' should lose to the actual subject name."""
    _prime_lady_godiva_plan()

    best = dms._best_entity_search_match_for_atom(
        {
            "matches": [
                {"entity_name": "lady", "match_score": 99},
                {"entity_name": "godiva", "match_score": 99},
            ]
        },
        atom=dms._semantic_plan_atom_by_id("a1"),
    )

    assert best is not None
    assert best["entity_name"] == "godiva"


def test_chunk_relevance_for_downstream_date_atom_prefers_endpoint_evidence() -> None:
    """Temporal endpoint chunks should outrank generic context once the dependency is resolved."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"

    score_endpoint = dms._chunk_relevance_score_for_atom(
        {"chunk_id": "chunk_83", "text": "Within six months Edward had deprived her of all authority in Mercia in 918."},
        atom=dms._semantic_plan_atom_by_id("a2"),
        dependency_values=["Mercia"],
    )
    score_generic = dms._chunk_relevance_score_for_atom(
        {"chunk_id": "chunk_84", "text": "Godiva and Leofric founded a cell in 1052 in Mercia."},
        atom=dms._semantic_plan_atom_by_id("a2"),
        dependency_values=["Mercia"],
    )

    assert score_endpoint > score_generic


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


def test_entity_search_rewrites_chunk_like_resolution_query_back_to_subject() -> None:
    """Chunk-sized string-resolution queries should collapse back to the active atom subject."""
    _prime_lady_godiva_plan()

    effective, contract = dms._build_retrieval_query_contract(
        "Leofric Earl of Mercia Godiva Countess of Leicester abbey founded as a cell of Croyland Abbey 1052",
        tool_name="entity_search",
    )

    assert contract["active_atom_id"] == "a1"
    assert "full_question_rewritten_to_active_atom" not in contract["rewrite_reason"]
    assert "off_atom_query_rewritten_to_active_atom" in contract["rewrite_reason"]
    assert "Lady Godiva" in effective
    assert "1052" not in effective
    assert "Leofric" not in effective


def test_internal_probe_query_bypass_preserves_downstream_query() -> None:
    """Internal bridge probes must not be rewritten back to the active atom."""
    _prime_lady_godiva_plan()

    with dms._query_contract_bypass("bridge_probe"):
        effective, contract = dms._build_retrieval_query_contract(
            "Mercia abolished",
            tool_name="chunk_text_search",
        )

    assert effective == "Mercia abolished"
    assert contract["rewrite_reason"] == ["internal_bypass:bridge_probe"]


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
    call_order: list[str] = []

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        call_order.append("profile")
        assert entity_name == "godiva"
        assert graph_reference_id == "MuSiQue_ERGraph"
        return (
            '{"entity_id":"godiva","canonical_name":"godiva",'
            '"connected_entities":["leicester","england","mercia"],'
            '"evidence_refs":["entity:godiva","chunk_84"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        call_order.append("relationship")
        assert entity_ids == ["godiva"]
        assert graph_reference_id == "MuSiQue_ERGraph"
        return (
            '{"one_hop_relationships":['
            '{"src_id":"godiva","tgt_id":"leicester","description":"countess of leicester"},'
            '{"src_id":"godiva","tgt_id":"mercia","description":"wife of Leofric, Earl of Mercia"}'
            ']}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        assert tool_name in {"entity_info", "relationship_search"}
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.14,
            "rationale": "Profile alone does not explicitly state birthplace.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        connected_entities = payload.get("connected_entities")
        if isinstance(connected_entities, list):
            assert connected_entities[-1] == "mercia"
        else:
            relationship_targets = [
                rel.get("tgt_id")
                for rel in payload.get("one_hop_relationships", [])
                if isinstance(rel, dict)
            ]
            assert "mercia" in relationship_targets
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
    monkeypatch.setattr(dms, "relationship_onehop", _fake_relationship_onehop)
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
    assert call_order == ["profile", "relationship"]


@pytest.mark.asyncio
async def test_entity_search_string_prefers_relationship_bridge_over_profile_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subject auto-profiling should compare profile and relationship bridge candidates before advancing."""
    _prime_lady_godiva_plan()

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        return (
            '{"entity_id":"godiva","canonical_name":"godiva",'
            '"connected_entities":["england","leicester"],'
            '"evidence_refs":["chunk_82"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        return (
            '{"one_hop_relationships":['
            '{"src_id":"godiva","tgt_id":"england","description":"countess lived in england"},'
            '{"src_id":"godiva","tgt_id":"mercia","description":"wife of Leofric, Earl of Mercia"}'
            ']}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.10,
            "rationale": "Need bridge disambiguation.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        if tool_name == "entity_info":
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "England",
                "confidence": 0.80,
                "evidence_refs": ["chunk_82"],
                "rationale": "Profile connected England to Godiva.",
                "tool_name": tool_name,
                "method": method,
                "resolution_mode": "bridge_probe",
            }
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "Mercia",
            "confidence": 0.80,
            "evidence_refs": ["chunk_84"],
            "rationale": "Relationship graph provides the stronger bridge.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "bridge_probe",
        }

    monkeypatch.setattr(dms, "entity_profile", _fake_entity_profile)
    monkeypatch.setattr(dms, "relationship_onehop", _fake_relationship_onehop)
    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "matches": [
                {
                    "entity_name": "godiva",
                    "canonical_name": "godiva",
                    "match_score": 95,
                }
            ],
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "dataset_name": "MuSiQue",
        },
        tool_name="entity_search",
        method="string",
    )

    assert update is not None
    assert update["resolved_value"] == "Mercia"
    assert dms._todo_item_by_id("a1")["answer"] == "Mercia"


@pytest.mark.asyncio
async def test_bridge_probe_uses_downstream_discriminant_not_subject_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge probes should combine downstream and subject queries instead of collapsing them."""
    _prime_lady_godiva_plan()

    observed_queries: list[str] = []

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        observed_queries.append(query_text)
        if query_text == "Mercia abolished":
            return '{"chunks":[{"chunk_id":"chunk_83","text":"Mercia was abolished in 918."}]}'
        if query_text == "Mercia godiva":
            return '{"chunks":[{"chunk_id":"chunk_84","text":"Godiva, Countess of Leicester, was associated with Mercia."}]}'
        return '{"chunks":[]}'

    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    probe_results = await dms._probe_bridge_candidates_with_text(
        ["England", "Mercia"],
        current_atom=dms._semantic_plan_atom_by_id("a1"),
        payload={
            "canonical_name": "godiva",
            "resolved_dataset_name": "MuSiQue",
        },
        downstream_atom=dms._semantic_plan_atom_by_id("a2"),
    )

    assert observed_queries == [
        "England abolished",
        "England godiva",
        "Mercia abolished",
        "Mercia godiva",
    ]
    assert probe_results[0]["candidate"] == "Mercia"
    assert probe_results[0]["downstream_score"] >= 3.0
    assert probe_results[0]["subject_score"] >= 2.0


@pytest.mark.asyncio
async def test_bridge_probe_strips_output_var_placeholders_from_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planner output-var placeholders should not leak into bridge probe queries."""
    _prime_lady_godiva_plan()
    dms._semantic_plan_atom_by_id("a2")["sub_question"] = (
        "When was the entity 'birthplace_of_lady_godiva' abolished?"
    )

    observed_queries: list[str] = []

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        observed_queries.append(query_text)
        return '{"chunks":[]}'

    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    await dms._probe_bridge_candidates_with_text(
        ["England", "Mercia"],
        current_atom=dms._semantic_plan_atom_by_id("a1"),
        payload={
            "canonical_name": "godiva",
            "resolved_dataset_name": "MuSiQue",
        },
        downstream_atom=dms._semantic_plan_atom_by_id("a2"),
    )

    assert observed_queries == [
        "England abolished",
        "England godiva",
        "Mercia abolished",
        "Mercia godiva",
    ]


@pytest.mark.asyncio
async def test_bridge_probe_normalizes_abolition_to_abolished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge probes should normalize abolition-style wording to the evidence verb form."""
    _prime_lady_godiva_plan()
    dms._semantic_plan_atom_by_id("a2")["sub_question"] = (
        "What is the abolition date of Lady Godiva's birthplace, which is {{birthplace}}?"
    )

    observed_queries: list[str] = []

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        observed_queries.append(query_text)
        return '{"chunks":[]}'

    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    await dms._probe_bridge_candidates_with_text(
        ["England", "Mercia"],
        current_atom=dms._semantic_plan_atom_by_id("a1"),
        payload={
            "canonical_name": "godiva",
            "resolved_dataset_name": "MuSiQue",
        },
        downstream_atom=dms._semantic_plan_atom_by_id("a2"),
    )

    assert observed_queries == [
        "England abolished date",
        "England godiva",
        "Mercia abolished date",
        "Mercia godiva",
    ]


@pytest.mark.asyncio
async def test_bridge_probe_requires_subject_and_downstream_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate with only downstream evidence should lose to one that also links back to the subject."""
    _prime_lady_godiva_plan()

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        if query_text == "England abolished":
            return '{"chunks":[{"chunk_id":"chunk_82","text":"England abolished treason penalties in 1870."}]}'
        if query_text == "England godiva":
            return '{"chunks":[{"chunk_id":"chunk_84","text":"Godiva founded an abbey with Leofric of Mercia."}]}'
        if query_text == "Mercia abolished":
            return '{"chunks":[{"chunk_id":"chunk_83","text":"Mercia was abolished in 918."}]}'
        if query_text == "Mercia godiva":
            return '{"chunks":[{"chunk_id":"chunk_84","text":"Godiva, wife of Leofric, was associated with Mercia."}]}'
        return '{"chunks":[]}'

    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    probe_results = await dms._probe_bridge_candidates_with_text(
        ["England", "Mercia"],
        current_atom=dms._semantic_plan_atom_by_id("a1"),
        payload={
            "canonical_name": "godiva",
            "resolved_dataset_name": "MuSiQue",
        },
        downstream_atom=dms._semantic_plan_atom_by_id("a2"),
    )

    assert [item["candidate"] for item in probe_results] == ["Mercia", "England"]
    assert probe_results[0]["subject_score"] > probe_results[1]["subject_score"]


@pytest.mark.asyncio
async def test_bridge_inference_accepts_probe_winner_at_configured_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge auto-advance should accept the top probe winner at the configured score gap."""
    _prime_lady_godiva_plan()

    async def _fake_probe(candidates, *, current_atom, payload, downstream_atom):
        return [
            {
                "candidate": "Mercia",
                "score": 10.5,
                "downstream_score": 5.0,
                "subject_score": 5.5,
                "chunk_id": "chunk_649",
            },
            {
                "candidate": "Leicester",
                "score": 10.0,
                "downstream_score": 5.0,
                "subject_score": 5.0,
                "chunk_id": "chunk_84",
            },
        ]

    monkeypatch.setattr(dms, "_probe_bridge_candidates_with_text", _fake_probe)

    update = await dms._infer_bridge_candidate_with_llm(
        dms._semantic_plan_atom_by_id("a1"),
        dms._todo_item_by_id("a1"),
        {
            "canonical_name": "godiva",
            "entity_id": "godiva",
            "resolved_dataset_name": "MuSiQue",
            "connected_entities": ["Mercia", "Leicester"],
        },
        tool_name="entity_info",
        method="profile",
    )

    assert update is not None
    assert update["event"] == "atom_autocomplete"
    assert update["resolved_value"] == "Mercia"
    assert update["resolution_mode"] == "bridge_probe"


@pytest.mark.asyncio
async def test_validate_manual_todo_completion_rejects_mismatched_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manual done states should be rejected when cached evidence supports a different answer."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"
    dms._seen_chunk_text["chunk_918"] = "Within six months Edward had deprived her of all authority in Mercia in 918."

    async def _fake_infer(atom, todo, payload, *, tool_name: str, method: str):
        assert atom["atom_id"] == "a2"
        return {
            "event": "atom_autocomplete",
            "atom_id": "a2",
            "resolved_value": "918",
            "confidence": 0.95,
            "evidence_refs": ["chunk_918"],
            "rationale": "The chunk explicitly states Mercia lost authority in 918.",
            "tool_name": tool_name,
            "method": method,
        }

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_infer)

    with pytest.raises(ValueError, match="supports '918' instead"):
        await dms._validate_manual_todo_completion(
            dms._semantic_plan_atom_by_id("a2"),
            {
                "id": "a2",
                "content": "When was that birthplace abolished?",
                "status": "done",
                "answer": "1052",
            },
            previous_todo=dms._todo_item_by_id("a2"),
        )


@pytest.mark.asyncio
async def test_cached_atom_validation_payload_drives_manual_done_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cached payloads should be reused to reject unsupported manual done transitions."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"
    dms._store_atom_validation_payload(
        dms._semantic_plan_atom_by_id("a2"),
        {
            "chunks": [
                {"chunk_id": "chunk_918", "text": "Within six months Edward had deprived her of all authority in Mercia in 918."}
            ],
            "evidence_refs": ["chunk_918"],
        },
        tool_name="chunk_retrieve",
        method="by_entities",
    )

    async def _fake_infer(atom, todo, payload, *, tool_name: str, method: str):
        if atom["atom_id"] == "a1":
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "Mercia",
                "confidence": 0.99,
                "evidence_refs": ["chunk_84"],
                "rationale": "Bridge entity resolved.",
                "tool_name": tool_name,
                "method": method,
            }
        return {
            "event": "atom_autocomplete",
            "atom_id": "a2",
            "resolved_value": "918",
            "confidence": 0.95,
            "evidence_refs": ["chunk_918"],
            "rationale": "Mercia endpoint date is 918.",
            "tool_name": tool_name,
            "method": method,
        }

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_infer)

    with pytest.raises(ValueError, match="supports '918' instead"):
        await dms._validate_manual_todo_completion(
            dms._semantic_plan_atom_by_id("a2"),
            {
                "id": "a2",
                "content": "When was that birthplace abolished?",
                "status": "done",
                "answer": "1052",
                "evidence_refs": ["chunk_918"],
            },
            previous_todo=dms._todo_item_by_id("a2"),
        )
