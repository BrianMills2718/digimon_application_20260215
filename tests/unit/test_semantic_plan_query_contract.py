"""Unit tests for semantic-plan query rewriting in benchmark mode."""

from __future__ import annotations
from types import SimpleNamespace

import llm_client
import pytest
from pydantic import BaseModel

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


def test_query_contract_applies_atom_recovery_hint_to_active_atom() -> None:
    """Active-atom retrieval should reuse the latest recovery hint when the query is still generic."""
    _prime_lady_godiva_plan()
    dms._atom_recovery_hints["a1"] = {
        "atom_id": "a1",
        "diagnosis": "Graph profile alone does not resolve the birthplace.",
        "suggested_query": "Lady Godiva Mercia birthplace",
        "target_tool_name": "chunk_retrieve",
        "target_method": "semantic",
        "next_action": "Search source chunks linking Lady Godiva directly to Mercia.",
        "avoid_values": ["England"],
        "confidence": 0.88,
        "fingerprint": "demo",
    }

    effective, contract = dms._build_retrieval_query_contract(
        "When was Lady Godiva's birthplace abolished?",
        tool_name="chunk_text_search",
    )

    assert effective == "Lady Godiva Mercia birthplace"
    assert contract["recovery_hint"]["suggested_query"] == "Lady Godiva Mercia birthplace"
    assert "atom_reflection_query_override" in contract["rewrite_reason"]


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


def test_normalize_semantic_plan_language_maps_output_var_dependency_ids() -> None:
    """Planner dependencies should reference atom IDs even when the model emits output vars."""
    plan = {
        "final_answer_kind": "number",
        "atoms": [
            {
                "atom_id": "a1",
                "sub_question": "What series has an episode titled 'The Bag or the Bat'?",
                "operation": "lookup",
                "answer_kind": "entity",
                "output_var": "series_with_episode",
                "depends_on": [],
                "done_criteria": "Resolve the series.",
            },
            {
                "atom_id": "a2",
                "sub_question": "How many episodes are in season 5 of the series_with_episode?",
                "operation": "relation",
                "answer_kind": "number",
                "output_var": "episode_count_s5",
                "depends_on": ["series_with_episode"],
                "done_criteria": "Count episodes for season 5 of the series_with_episode.",
            },
        ],
    }

    normalized = dms._normalize_semantic_plan_language(plan)

    assert normalized["atoms"][1]["depends_on"] == ["a1"]
    assert "series_with_episode" not in normalized["atoms"][1]["sub_question"]


def test_infer_answer_kind_uses_text_for_how_were_questions() -> None:
    """Method/action questions should infer text rather than entity/number."""
    assert (
        dms._infer_answer_kind(
            "How were the people from whom new coins were a proclamation of independence expelled?"
        )
        == "text"
    )


def test_normalize_answer_kind_supports_text_aliases() -> None:
    """Semantic-plan normalization should preserve phrase-style answer kinds."""
    assert dms._normalize_answer_kind("text") == "text"
    assert dms._normalize_answer_kind("phrase") == "text"
    assert dms._normalize_answer_kind("method") == "text"


def test_between_endpoint_guard_rejects_endpoint_answers() -> None:
    """A between-country atom must not accept either endpoint itself."""
    atom = {
        "atom_id": "a2",
        "sub_question": "What is the country between Thailand and A Lim's country?",
        "answer_kind": "entity",
        "depends_on": ["a1"],
    }
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update({"atoms": [atom]})
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a1", "content": "Resolve A Lim's country", "status": "done", "answer": "Laos"},
            {"id": "a2", "content": "Resolve the between-country", "status": "in_progress"},
        ]
    )

    assert dms._answer_matches_between_endpoint(atom, "Laos") is True
    assert dms._answer_matches_between_endpoint(atom, "Thailand") is True
    assert dms._answer_matches_between_endpoint(atom, "Myanmar") is False


def test_pending_todo_ids_for_submit_reports_unfinished_atoms() -> None:
    """Final submission should stay blocked until all semantic-plan atoms are done."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"

    assert dms._pending_todo_ids_for_submit() == ["a2"]


def test_pending_submit_validation_payload_reports_unfinished_atoms() -> None:
    """Normal submit guard should report unresolved semantic-plan atoms structurally."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1]["status"] = "in_progress"

    payload = dms._pending_submit_validation_payload()

    assert payload is not None
    assert payload["status"] == "rejected"
    assert payload["pending_atoms"] == 1
    assert payload["pending_ids"] == ["a2"]
    assert payload["validation_error"]["reason_code"] == "pending_atoms"
    assert payload["recovery_policy"]["new_evidence_required_before_retry"] is True


def test_pending_submit_validation_payload_allows_completed_plans() -> None:
    """Submit guard should clear once all semantic-plan atoms are complete."""
    _prime_lady_godiva_plan()
    dms._todos[0].update({"status": "done", "answer": "Mercia"})
    dms._todos[1].update({"status": "done", "answer": "918"})

    assert dms._pending_submit_validation_payload() is None


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


def test_compact_search_query_preserves_quoted_title_anchor() -> None:
    """Quoted titles should survive compaction intact instead of losing stopwords."""
    compact = dms._compact_search_query('Identify the series that includes "The Bag or the Bat".')

    assert "The Bag or the Bat" in compact
    assert "Bag Bat" not in compact


def test_compact_search_query_preserves_single_quoted_anchor_phrase() -> None:
    """Single-quoted anchors with internal apostrophes should also be preserved."""
    compact = dms._compact_search_query("Identify 'A Lim's country'")

    assert "A Lim's country" in compact
    assert compact != "Lim country"


def test_query_contract_preserves_quoted_title_from_active_atom() -> None:
    """Active-atom rewriting should retain exact quoted titles for retrieval."""
    dms._current_question = "How many episodes are in season 5 of the series with The Bag or the Bat?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": "Identify the series that includes 'The Bag or the Bat'.",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                }
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {
                "id": "a1",
                "content": "Identify the series that includes 'The Bag or the Bat'.",
                "status": "in_progress",
            }
        ]
    )

    effective, contract = dms._build_retrieval_query_contract(
        "How many episodes are in season 5 of the series with The Bag or the Bat?",
        tool_name="chunk_text_search",
    )

    assert contract["active_atom_id"] == "a1"
    assert "The Bag or the Bat" in effective
    assert "Bag Bat" not in effective


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


def test_entity_search_preserves_cached_alias_query_for_namesake_probe() -> None:
    """Alias probes grounded in cached evidence should survive entity-query rewriting."""
    dms._current_question = "What is the birthplace of the person after whom São José dos Campos was named?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": "Who is the person after whom São José dos Campos was named?",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "What is the birthplace of that person?",
                    "depends_on": ["a1"],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {
                "id": "a1",
                "content": "Who is the person after whom São José dos Campos was named?",
                "status": "in_progress",
            },
            {
                "id": "a2",
                "content": "What is the birthplace of that person?",
                "status": "pending",
            },
        ]
    )
    dms._atom_validation_payloads["a1"] = [
        {
            "tool_name": "chunk_retrieve",
            "method": "text",
            "chunks": [
                {
                    "chunk_id": "chunk_239",
                    "text": "São José dos Campos, meaning Saint Joseph of the Fields, is a major city in São Paulo, Brazil.",
                }
            ],
        }
    ]

    effective, contract = dms._build_retrieval_query_contract(
        "Saint Joseph of the Fields named after person",
        tool_name="entity_search",
    )

    assert contract["active_atom_id"] == "a1"
    assert "off_atom_query_rewritten_to_active_atom" not in contract["rewrite_reason"]
    assert "Saint Joseph" in effective


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


def test_atom_is_trivial_return_detects_final_echo_atom() -> None:
    """Bridge inference should ignore downstream atoms that only restate the final return."""
    assert dms._atom_is_trivial_return({"sub_question": "Return the birthplace"})
    assert not dms._atom_is_trivial_return({"sub_question": "When was that birthplace abolished?"})


def test_bridge_candidate_names_filters_to_expected_person_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bridge candidates should honor the current atom's expected coarse type when matches exist."""
    dms._current_question = "What is the person after whom São José dos Campos was named?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "atom1",
                    "sub_question": "What is the person after whom São José dos Campos was named?",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                }
            ]
        }
    )

    coarse_types = {
        "brazil": "place",
        "arthur bernardes": "person",
        "rio de janeiro": "place",
    }
    monkeypatch.setattr(
        dms,
        "_lookup_entity_coarse_type",
        lambda candidate, dataset_name="": coarse_types.get(candidate, "unknown"),
    )

    candidates = dms._bridge_candidate_names(
        {
            "canonical_name": "são josé dos campos",
            "resolved_dataset_name": "MuSiQue",
            "connected_entities": ["brazil", "arthur bernardes", "rio de janeiro"],
        },
        current_atom=dms._semantic_plan_atom_by_id("atom1"),
    )

    assert candidates == ["arthur bernardes"]


def test_bridge_candidate_names_preserves_candidates_when_no_type_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bridge filtering should fail open when graph typing cannot confirm any expected match."""
    dms._current_question = "What is the person after whom São José dos Campos was named?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "atom1",
                    "sub_question": "What is the person after whom São José dos Campos was named?",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                }
            ]
        }
    )

    monkeypatch.setattr(dms, "_lookup_entity_coarse_type", lambda candidate, dataset_name="": "unknown")

    candidates = dms._bridge_candidate_names(
        {
            "canonical_name": "são josé dos campos",
            "resolved_dataset_name": "MuSiQue",
            "connected_entities": ["brazil", "arthur bernardes"],
        },
        current_atom=dms._semantic_plan_atom_by_id("atom1"),
    )

    assert candidates == ["brazil", "arthur bernardes"]


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
    def _capture_event(event):
        payload = dict(event)
        captured_events.append(payload)
        dms._atom_lifecycle_events.append(payload)

    monkeypatch.setattr(dms, "_record_atom_lifecycle_event", _capture_event)

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
async def test_entity_search_string_blocks_bridge_autocomplete_for_structural_relation_atoms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural relation atoms like 'season 5 of X' should not collapse to loose graph neighbors."""
    dms._current_question = "How many episodes are in season 5 of the series with The Bag or the Bat?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": "What is the series that contains an episode titled 'The Bag or the Bat'?",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "What is season 5 of the series (from a1)?",
                    "depends_on": ["a1"],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a3",
                    "sub_question": "How many episodes are in that season 5 (from a2)?",
                    "depends_on": ["a2"],
                    "operation": "lookup",
                    "answer_kind": "number",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a1", "content": "Identify the series", "status": "done", "answer": "Ray Donovan"},
            {"id": "a2", "content": "Identify season 5 of that series.", "status": "in_progress"},
            {"id": "a3", "content": "Find how many episodes are in season 5.", "status": "pending"},
        ]
    )

    bridge_calls: list[tuple[str, str]] = []

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        return (
            '{"entity_id":"ray donovan","canonical_name":"Ray Donovan",'
            '"connected_entities":["showtime","ann biderman"],'
            '"evidence_refs":["chunk_200"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        return (
            '{"one_hop_relationships":['
            '{"src_id":"ray donovan","tgt_id":"showtime","description":"aired on Showtime"}'
            ']}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a2",
            "confidence": 0.0,
            "rationale": "No direct season-5 entity is present.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        bridge_calls.append((tool_name, method))
        return {
            "event": "atom_autocomplete",
            "atom_id": "a2",
            "resolved_value": "showtime",
            "confidence": 0.9,
            "evidence_refs": ["chunk_1877"],
            "rationale": "showtime looks connected to the downstream season question.",
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
                    "entity_name": "ray donovan",
                    "canonical_name": "Ray Donovan",
                    "match_score": 100,
                }
            ],
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "dataset_name": "MuSiQue",
        },
        tool_name="entity_search",
        method="string",
    )

    assert bridge_calls == [("entity_info", "profile"), ("relationship_search", "graph")]
    assert update is None
    assert dms._todo_item_by_id("a2")["status"] == "in_progress"
    assert dms._todo_item_by_id("a2").get("answer") in {None, ""}


@pytest.mark.asyncio
async def test_entity_search_string_birthplace_atom_requires_birth_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Birthplace atoms should not autocomplete from unrelated connected places."""
    dms._current_question = "What is the birthplace of the person after whom São José dos Campos was named?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "A1",
                    "sub_question": "Identify the person after whom São José dos Campos was named",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "A2",
                    "sub_question": "Find birthplace of the identified person",
                    "depends_on": ["A1"],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "A1", "content": "Identify the person after whom São José dos Campos was named", "status": "done", "answer": "Saint Joseph"},
            {"id": "A2", "content": "Find birthplace of the identified person", "status": "in_progress"},
        ]
    )

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        return (
            '{"entity_id":"saint joseph","canonical_name":"Saint Joseph",'
            '"connected_entities":["california"],'
            '"description":"The earthly father of Jesus whose workshop is the setting for a painting.",'
            '"evidence_refs":["chunk_3346"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        return (
            '{"one_hop_relationships":['
            '{"src_id":"saint joseph","tgt_id":"california","description":"painting set in california"}'
            '], "evidence_refs":["chunk_3346"]}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_autocomplete",
            "atom_id": "A2",
            "resolved_value": "california",
            "confidence": 0.91,
            "evidence_refs": ["chunk_3346"],
            "rationale": "Connected place candidate.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        return None

    monkeypatch.setattr(dms, "entity_profile", _fake_entity_profile)
    monkeypatch.setattr(dms, "relationship_onehop", _fake_relationship_onehop)
    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "matches": [
                {
                    "entity_name": "Saint Joseph",
                    "canonical_name": "Saint Joseph",
                    "match_score": 100,
                }
            ],
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "dataset_name": "MuSiQue",
        },
        tool_name="entity_search",
        method="string",
    )

    assert update is None
    assert dms._todo_item_by_id("A2")["status"] == "in_progress"


@pytest.mark.asyncio
async def test_chunk_retrieve_birthplace_atom_can_use_contextual_place_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chunk evidence can close a place atom through the contextual place judge."""
    dms._current_question = "What is the birthplace of the person after whom São José dos Campos was named?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "A1",
                    "sub_question": "Identify the person after whom São José dos Campos was named",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "A2",
                    "sub_question": "Find birthplace of the identified person",
                    "depends_on": ["A1"],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "A1", "content": "Identify the person after whom São José dos Campos was named", "status": "done", "answer": "Saint Joseph"},
            {"id": "A2", "content": "Find birthplace of the identified person", "status": "in_progress"},
        ]
    )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "A2",
            "confidence": 0.35,
            "rationale": "No direct birthplace wording.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_contextual_place(atom, todo, payload, *, tool_name: str, method: str):
        assert tool_name == "chunk_retrieve"
        return {
            "event": "atom_autocomplete",
            "atom_id": "A2",
            "resolved_value": "Nazareth",
            "confidence": 0.86,
            "evidence_refs": ["chunk_11367"],
            "rationale": "Nazareth is the only place strongly tied to Saint Joseph in the retrieved biographical context.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "contextual_place_inference",
        }

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_contextual_place_completion_with_llm", _fake_contextual_place)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "chunks": [
                {
                    "chunk_id": "chunk_11367",
                    "text": (
                        'Mary resided in "her own house" in Nazareth in Galilee, and after a number of months, '
                        "when Joseph was told of her conception in a dream by an angel of the Lord, "
                        "he took her as his wife."
                    ),
                }
            ],
            "evidence_refs": ["chunk_11367"],
            "query_contract": {"effective_query": "Saint Joseph birthplace"},
        },
        tool_name="chunk_retrieve",
        method="semantic",
    )

    assert update is not None
    assert update["resolved_value"] == "Nazareth"
    assert update["resolution_mode"] == "contextual_place_inference"
    assert dms._todo_item_by_id("A2")["status"] == "done"
    assert dms._todo_item_by_id("A2")["answer"] == "Nazareth"


@pytest.mark.asyncio
async def test_entity_search_string_namesake_atom_probes_subject_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Namesake atoms should internally probe subject-linked chunks after a clean entity hit."""
    dms._current_question = "What is the birthplace of the person after whom São José dos Campos was named?"
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "A1",
                    "sub_question": "Who is the person after whom São José dos Campos was named?",
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "A2",
                    "sub_question": "What is the birthplace of the person identified in a1?",
                    "depends_on": ["A1"],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "A1", "content": "Who is the person after whom São José dos Campos was named?", "status": "in_progress"},
            {"id": "A2", "content": "What is the birthplace of the person identified in a1?", "status": "pending"},
        ]
    )

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        return (
            '{"entity_id":"s o jos  dos campos","canonical_name":"s o jos  dos campos",'
            '"connected_entities":["são paulo"],'
            '"evidence_refs":["chunk_239"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        return '{"one_hop_relationships": [], "evidence_refs":["chunk_239"]}'

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "A1",
            "confidence": 0.22,
            "rationale": "Need chunk-level naming evidence.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        return None

    async def _fake_chunk_probe(
        atom,
        todo,
        *,
        candidate_entity_id: str,
        candidate_name: str,
        resolved_graph_id: str,
        dataset_name: str,
    ):
        assert candidate_entity_id == "s o jos  dos campos"
        return {
            "event": "atom_autocomplete",
            "atom_id": "A1",
            "resolved_value": "Saint Joseph",
            "confidence": 0.84,
            "evidence_refs": ["chunk_239"],
            "rationale": "The subject-linked chunk states the city means Saint Joseph of the Fields.",
            "tool_name": "chunk_retrieve",
            "method": "by_entities",
            "resolution_mode": "subject_chunk_probe",
        }

    monkeypatch.setattr(dms, "entity_profile", _fake_entity_profile)
    monkeypatch.setattr(dms, "relationship_onehop", _fake_relationship_onehop)
    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)
    monkeypatch.setattr(dms, "_atom_requires_subject_chunk_probe", lambda atom: True)
    monkeypatch.setattr(dms, "_probe_subject_entity_chunks_for_atom", _fake_chunk_probe)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "matches": [
                {
                    "entity_name": "s o jos  dos campos",
                    "canonical_name": "s o jos  dos campos",
                    "match_score": 96,
                }
            ],
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "dataset_name": "MuSiQue",
        },
        tool_name="entity_search",
        method="string",
    )

    assert update is not None
    assert update["resolved_value"] == "Saint Joseph"
    assert update["resolution_mode"] == "subject_chunk_probe"
    assert dms._todo_item_by_id("A1")["status"] == "done"
    assert dms._todo_item_by_id("A2")["status"] == "in_progress"


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
async def test_entity_search_string_prefers_bridge_update_over_direct_profile_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge-qualified winners should beat raw profile autocompletions in subject auto-profiling."""
    _prime_lady_godiva_plan()

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        return (
            '{"entity_id":"godiva","canonical_name":"godiva",'
            '"connected_entities":["england","mercia"],'
            '"evidence_refs":["entity:godiva"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        return (
            '{"one_hop_relationships":['
            '{"src_id":"godiva","tgt_id":"england","description":"countess lived in england"},'
            '{"src_id":"godiva","tgt_id":"mercia","description":"wife of Leofric, Earl of Mercia"}'
            ']}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        if tool_name == "entity_info":
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "England",
                "confidence": 0.98,
                "evidence_refs": ["chunk_82"],
                "rationale": "Profile autocomplete guessed England.",
                "tool_name": tool_name,
                "method": method,
            }
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.25,
            "rationale": "Relationship payload alone is unresolved without bridge disambiguation.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        if tool_name == "entity_info":
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "Mercia",
                "confidence": 0.81,
                "evidence_refs": ["chunk_649"],
                "rationale": "Bridge probe found the downstream abolition clue for Mercia.",
                "tool_name": tool_name,
                "method": method,
                "resolution_mode": "bridge_probe",
            }
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.22,
            "rationale": "No stronger bridge on the relationship payload.",
            "tool_name": tool_name,
            "method": method,
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
                    "match_score": 99,
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
    assert update["resolution_mode"] == "bridge_probe"
    assert dms._todo_item_by_id("a1")["answer"] == "Mercia"


@pytest.mark.asyncio
async def test_entity_search_string_preserves_subject_anchor_over_bridge_neighbor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct completion that matches the resolved subject anchor must beat neighbor bridges."""
    dms._current_question = 'Which series includes the episode "The Bag or the Bat"?'
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": 'Which series includes the episode "The Bag or the Bat"?',
                    "depends_on": [],
                    "operation": "lookup",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "How many episodes does that series have?",
                    "depends_on": ["a1"],
                    "operation": "aggregation",
                    "answer_kind": "number",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a1", "content": 'Which series includes the episode "The Bag or the Bat"?', "status": "in_progress"},
            {"id": "a2", "content": "How many episodes does that series have?", "status": "pending"},
        ]
    )

    async def _fake_entity_profile(*, entity_name: str, graph_reference_id: str, dataset_name: str = ""):
        return (
            '{"entity_id":"ray_donovan","canonical_name":"Ray Donovan",'
            '"connected_entities":["showtime"],'
            '"evidence_refs":["chunk_200"]}'
        )

    async def _fake_relationship_onehop(*, entity_ids, graph_reference_id: str):
        return (
            '{"one_hop_relationships":['
            '{"src_id":"ray_donovan","tgt_id":"showtime","description":"Ray Donovan aired on Showtime."}'
            '], "evidence_refs":["chunk_213"]}'
        )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        if tool_name == "entity_info":
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "Ray Donovan",
                "confidence": 0.93,
                "evidence_refs": ["chunk_200"],
                "rationale": 'The profile directly resolves "The Bag or the Bat" to Ray Donovan.',
                "tool_name": tool_name,
                "method": method,
            }
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.24,
            "rationale": "Relationship payload alone needs interpretation.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "showtime",
            "confidence": 0.89,
            "evidence_refs": ["chunk_213"],
            "rationale": "Showtime appears as the neighboring network entity.",
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
                    "entity_name": "Ray Donovan",
                    "canonical_name": "Ray Donovan",
                    "entity_id": "ray_donovan",
                    "match_score": 100,
                }
            ],
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "dataset_name": "MuSiQue",
        },
        tool_name="entity_search",
        method="string",
    )

    assert update is not None
    assert update["resolved_value"] == "Ray Donovan"
    assert dms._todo_item_by_id("a1")["answer"] == "Ray Donovan"
    assert dms._todo_item_by_id("a2")["status"] == "in_progress"


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
async def test_repeated_unresolved_atom_generates_recovery_reflection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated unresolved attempts should produce a structured recovery hint."""
    _prime_lady_godiva_plan()

    captured_events: list[dict[str, object]] = []

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.28,
            "rationale": "The chunk mentions England broadly but does not directly answer Lady Godiva's birthplace.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_helper_call(model, messages, response_model, **kwargs):
        return (
            response_model(
                diagnosis="The controller is repeating broad birthplace queries instead of probing the supported bridge entity.",
                suggested_query="Lady Godiva Mercia birthplace",
                target_tool_name="chunk_retrieve",
                target_method="semantic",
                next_action="Search source chunks that mention Lady Godiva together with Mercia before trying to submit again.",
                avoid_values=["England"],
                confidence=0.91,
            ),
            SimpleNamespace(),
        )

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_call_helper_structured", _fake_helper_call)
    monkeypatch.setattr(
        dms,
        "_helper_structured_llm_policy",
        lambda num_retries=2: ("openrouter/openai/gpt-5.4-mini", {"num_retries": num_retries}),
    )
    monkeypatch.setattr(
        llm_client,
        "render_prompt",
        lambda *args, **kwargs: [{"role": "user", "content": "reflect"}],
    )

    def _capture_event(event):
        payload = dict(event)
        captured_events.append(payload)
        dms._atom_lifecycle_events.append(payload)

    monkeypatch.setattr(dms, "_record_atom_lifecycle_event", _capture_event)

    payload = {
        "chunks": [
            {
                "chunk_id": "chunk_84",
                "text": "Lady Godiva was associated with England, but this does not directly resolve her birthplace.",
            }
        ],
        "query_contract": {
            "effective_query": "Lady Godiva birthplace",
        },
    }

    first_update = await dms._maybe_complete_active_atom_from_payload(
        payload,
        tool_name="chunk_retrieve",
        method="semantic",
    )
    second_update = await dms._maybe_complete_active_atom_from_payload(
        payload,
        tool_name="chunk_retrieve",
        method="semantic",
    )

    assert first_update is not None
    assert "reflection_hint" not in first_update
    assert second_update is not None
    assert second_update["event"] == "atom_judged_unresolved"
    assert second_update["reflection_hint"]["suggested_query"] == "Lady Godiva Mercia birthplace"
    assert second_update["next_action"].startswith("Search source chunks")
    assert any(event["event"] == "atom_reflection_generated" for event in captured_events)

    effective, contract = dms._build_retrieval_query_contract(
        "When was Lady Godiva's birthplace abolished?",
        tool_name="chunk_text_search",
    )
    assert effective == "Lady Godiva Mercia birthplace"
    assert contract["recovery_hint"]["target_tool_name"] == "chunk_retrieve"


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
async def test_relation_sensitive_bridge_candidate_must_match_focused_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-risk relation atoms should reject bridge candidates when focused evidence supports another value."""
    dms._current_question = (
        "How were the people from whom new coins were a proclamation of independence by the Somali Muslim "
        "Ajuran Empire expelled from the country between Thailand and A Lim's country?"
    )
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": "What is the country between Thailand and A Lim's country?",
                    "depends_on": [],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "How were the people (from a1) expelled?",
                    "depends_on": ["a1"],
                    "operation": "lookup",
                    "answer_kind": "text",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a1", "content": "Resolve the country between Thailand and A Lim's country.", "status": "in_progress"},
            {"id": "a2", "content": "How were the people expelled?", "status": "pending"},
        ]
    )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        effective_query = str((payload.get("query_contract") or {}).get("effective_query") or "")
        if effective_query:
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "Myanmar",
                "confidence": 0.94,
                "evidence_refs": ["chunk_225"],
                "rationale": "The focused chunk explicitly identifies Myanmar as the country bordering Thailand and Laos.",
                "tool_name": tool_name,
                "method": method,
            }
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.18,
            "rationale": "No direct answer yet.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "China",
            "confidence": 0.88,
            "evidence_refs": ["chunk_7829"],
            "rationale": "China looked like the best downstream bridge.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "bridge_probe",
        }

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        lowered = query_text.lower()
        assert "china" in lowered
        assert "country" in lowered
        assert "between" in lowered
        assert "thailand" in lowered
        return (
            '{"chunks":[{"chunk_id":"chunk_225","text":"Myanmar borders China, Thailand and Laos."}]}'
        )

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)
    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "entity_id": "a lim",
            "canonical_name": "A Lim",
            "resolved_dataset_name": "MuSiQue",
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "connected_entities": ["China", "Myanmar"],
        },
        tool_name="entity_info",
        method="profile",
    )

    assert update is not None
    assert update["event"] == "atom_judged_unresolved"
    assert "supports 'Myanmar' rather than bridge candidate 'China'" in update["rationale"]
    assert dms._todo_item_by_id("a1")["status"] == "in_progress"


@pytest.mark.asyncio
async def test_relation_sensitive_bridge_candidate_is_accepted_after_focused_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-risk relation atoms may still autocomplete when focused evidence confirms the bridge value."""
    dms._current_question = (
        "How were the people from whom new coins were a proclamation of independence by the Somali Muslim "
        "Ajuran Empire expelled from the country between Thailand and A Lim's country?"
    )
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a1",
                    "sub_question": "Who were the people from whom new coins were a proclamation of independence by the Somali Muslim Ajuran Empire?",
                    "depends_on": [],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a2",
                    "sub_question": "How were those people expelled?",
                    "depends_on": ["a1"],
                    "operation": "lookup",
                    "answer_kind": "text",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a1", "content": "Resolve the people from whom the Ajuran Empire declared independence.", "status": "in_progress"},
            {"id": "a2", "content": "How were those people expelled?", "status": "pending"},
        ]
    )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        effective_query = str((payload.get("query_contract") or {}).get("effective_query") or "")
        if effective_query:
            return {
                "event": "atom_autocomplete",
                "atom_id": "a1",
                "resolved_value": "the Portuguese",
                "confidence": 0.93,
                "evidence_refs": ["chunk_0"],
                "rationale": "The focused Ottoman Empire evidence directly names the Portuguese.",
                "tool_name": tool_name,
                "method": method,
            }
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a1",
            "confidence": 0.15,
            "rationale": "Profile alone is too indirect.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_autocomplete",
            "atom_id": "a1",
            "resolved_value": "the Portuguese",
            "confidence": 0.84,
            "evidence_refs": ["entity:ajuran empire"],
            "rationale": "The Portuguese are the only candidate that fit the downstream expulsion clue.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "bridge_inference",
        }

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        lowered = query_text.lower()
        assert "portuguese" in lowered
        assert "people" in lowered
        assert "coins" in lowered
        assert "independence" in lowered
        assert "ajuran" in lowered
        return (
            '{"chunks":[{"chunk_id":"chunk_0","text":"The Somali Muslim Ajuran Empire proclaimed economic independence in regard to the Portuguese."}]}'
        )

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)
    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "entity_id": "ajuran empire",
            "canonical_name": "Ajuran Empire",
            "resolved_dataset_name": "MuSiQue",
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "connected_entities": ["Somalia", "the Portuguese"],
        },
        tool_name="entity_info",
        method="profile",
    )

    assert update is not None
    assert update["event"] == "atom_completed"
    assert update["resolved_value"] == "the Portuguese"
    assert update["resolution_mode"] == "bridge_inference_validated"
    assert dms._todo_item_by_id("a1")["status"] == "done"


def test_person_answer_atoms_require_validated_bridge_resolution() -> None:
    """Person-seeking entity atoms should not accept provisional bridge jumps without focused validation."""
    assert dms._atom_requires_validated_bridge_resolution(
        {
            "answer_kind": "entity",
            "sub_question": "What people were a proclamation of independence by the Somali Muslim Ajuran Empire for new coins?",
        }
    )


@pytest.mark.asyncio
async def test_person_bridge_candidate_must_match_focused_validation_without_from_whom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Human-answer bridge guesses should be validated even when the atom lacks an explicit 'from whom' phrase."""
    dms._current_question = (
        "How were the people from whom new coins were a proclamation of independence by the Somali Muslim "
        "Ajuran Empire expelled from the country between Thailand and A Lim's country?"
    )
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a3",
                    "sub_question": "What people were a proclamation of independence by the Somali Muslim Ajuran Empire for new coins?",
                    "depends_on": [],
                    "operation": "relation",
                    "answer_kind": "entity",
                },
                {
                    "atom_id": "a4",
                    "sub_question": "How were those people expelled?",
                    "depends_on": ["a3"],
                    "operation": "lookup",
                    "answer_kind": "text",
                },
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [
            {"id": "a3", "content": "Resolve the people tied to the Ajuran proclamation.", "status": "in_progress"},
            {"id": "a4", "content": "How were those people expelled?", "status": "pending"},
        ]
    )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        effective_query = str((payload.get("query_contract") or {}).get("effective_query") or "")
        if effective_query:
            return {
                "event": "atom_autocomplete",
                "atom_id": "a3",
                "resolved_value": "Portuguese",
                "confidence": 0.93,
                "evidence_refs": ["chunk_217"],
                "rationale": "The focused chunk directly ties the Ajuran independence claim to the Portuguese.",
                "tool_name": tool_name,
                "method": method,
            }
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a3",
            "confidence": 0.18,
            "rationale": "Profile alone is too indirect.",
            "tool_name": tool_name,
            "method": method,
        }

    async def _fake_bridge(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_autocomplete",
            "atom_id": "a3",
            "resolved_value": "Soviet Union",
            "confidence": 0.86,
            "evidence_refs": ["chunk_999"],
            "rationale": "Soviet Union looked like the best downstream bridge candidate.",
            "tool_name": tool_name,
            "method": method,
            "resolution_mode": "bridge_probe",
        }

    async def _fake_chunk_text_search(*, query_text: str, dataset_name: str, top_k: int = 2, entity_names=None):
        lowered = query_text.lower()
        assert "soviet union" in lowered
        assert "people" in lowered
        assert "ajuran" in lowered
        return (
            '{"chunks":[{"chunk_id":"chunk_217","text":"The Ajuran Empire adopted new coinage as a proclamation of economic independence in regard to the Portuguese."}]}'
        )

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_infer_bridge_candidate_with_llm", _fake_bridge)
    monkeypatch.setattr(dms, "chunk_text_search", _fake_chunk_text_search)

    update = await dms._maybe_complete_active_atom_from_payload(
        {
            "entity_id": "ajuran empire",
            "canonical_name": "Ajuran Empire",
            "resolved_dataset_name": "MuSiQue",
            "resolved_graph_reference_id": "MuSiQue_ERGraph",
            "connected_entities": ["Soviet Union", "Portuguese"],
        },
        tool_name="entity_info",
        method="profile",
    )

    assert update is not None
    assert update["event"] == "atom_judged_unresolved"
    assert "supports 'Portuguese' rather than bridge candidate 'Soviet Union'" in update["rationale"]
    assert dms._todo_item_by_id("a3")["status"] == "in_progress"


@pytest.mark.asyncio
async def test_relation_like_entity_reflection_forces_surface_pivot_after_chunk_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated chunk misses on relation-like entity atoms should preserve a graph/entity pivot instead of another chunk loop."""
    dms._current_question = (
        "How were the people from whom new coins were a proclamation of independence by the Somali Muslim "
        "Ajuran Empire expelled from the country between Thailand and A Lim's country?"
    )
    dms._current_semantic_plan.clear()
    dms._current_semantic_plan.update(
        {
            "atoms": [
                {
                    "atom_id": "a3",
                    "sub_question": "Which people were from whom new coins were a proclamation of independence by the Somali Muslim Ajuran Empire?",
                    "depends_on": [],
                    "operation": "relation",
                    "answer_kind": "entity",
                }
            ]
        }
    )
    dms._todos.clear()
    dms._todos.extend(
        [{"id": "a3", "content": "Resolve the people tied to the Ajuran proclamation.", "status": "in_progress"}]
    )

    async def _fake_completion(atom, todo, payload, *, tool_name: str, method: str):
        return {
            "event": "atom_judged_unresolved",
            "atom_id": "a3",
            "confidence": 0.2,
            "rationale": "The current chunks do not directly identify the people from whom the Ajuran Empire declared independence.",
            "tool_name": tool_name,
            "method": method,
            "next_action": (
                "Switch surfaces: resolve the subject entity in the graph with "
                "entity_search(method='string'), then inspect entity_info(profile) "
                "or relationship_search(graph). Do not guess a bridge entity yet."
            ),
        }

    async def _fake_helper_call(model, messages, response_model, **kwargs):
        return (
            response_model(
                diagnosis="Repeated chunk retrieval did not identify the target people.",
                suggested_query="Ajuran Empire new coins proclamation of independence from whom",
                target_tool_name="chunk_retrieve",
                target_method="semantic",
                next_action="Try another semantic chunk retrieval with a narrower independence query.",
                avoid_values=["Soviet Union"],
                confidence=0.89,
            ),
            SimpleNamespace(),
        )

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fake_completion)
    monkeypatch.setattr(dms, "_call_helper_structured", _fake_helper_call)
    monkeypatch.setattr(
        dms,
        "_helper_structured_llm_policy",
        lambda num_retries=2: ("openrouter/openai/gpt-5.4-mini", {"num_retries": num_retries}),
    )
    monkeypatch.setattr(
        llm_client,
        "render_prompt",
        lambda *args, **kwargs: [{"role": "user", "content": "reflect"}],
    )

    payload = {
        "chunks": [
            {
                "chunk_id": "chunk_217",
                "text": "The Ajuran Empire adopted new coinage as a proclamation of independence in regard to the Portuguese.",
            }
        ],
        "query_contract": {
            "effective_query": "Ajuran Empire new coins proclamation independence",
        },
    }

    first_update = await dms._maybe_complete_active_atom_from_payload(
        payload,
        tool_name="chunk_retrieve",
        method="semantic",
    )
    second_update = await dms._maybe_complete_active_atom_from_payload(
        payload,
        tool_name="chunk_retrieve",
        method="semantic",
    )

    assert first_update is not None
    assert second_update is not None
    assert second_update["reflection_hint"]["target_tool_name"] == "entity_search"
    assert second_update["reflection_hint"]["target_method"] in {"", "string", "semantic"}
    assert second_update["next_action"].startswith("Switch surfaces:")


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


@pytest.mark.asyncio
async def test_validate_manual_todo_completion_reuses_identical_done_atom(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rewriting an already-completed atom with the same answer should be idempotent."""
    _prime_lady_godiva_plan()
    dms._todos[0].update(
        {
            "status": "done",
            "answer": "Mercia",
            "evidence_refs": ["chunk_84"],
            "resolution_mode": "bridge_inference_validated",
        }
    )

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("validator should not rerun for identical done atoms")

    monkeypatch.setattr(dms, "_infer_atom_completion_with_llm", _fail_if_called)

    normalized = await dms._validate_manual_todo_completion(
        dms._semantic_plan_atom_by_id("a1"),
        {
            "id": "a1",
            "content": "What was Lady Godiva's birthplace?",
            "status": "done",
            "answer": "Mercia",
            "evidence_refs": ["chunk_84"],
        },
        previous_todo=dms._todo_item_by_id("a1"),
    )

    assert normalized["answer"] == "Mercia"
    assert normalized["status"] == "done"
    assert normalized["evidence_refs"] == ["chunk_84"]
    assert normalized["resolution_mode"] == "bridge_inference_validated"


def test_helper_structured_llm_policy_uses_agentic_fallback_chain() -> None:
    """Helper structured calls should inherit fallback routing instead of hard-pinning one model."""
    original_state = dict(dms._state)
    try:
        dms._state.clear()
        dms._state.update(
            {
                "config": SimpleNamespace(
                    llm=SimpleNamespace(
                        model="gemini/gemini-2.5-flash",
                        fallback_models=[
                            "gemini/gemini-2.5-flash",
                            "openrouter/openai/gpt-5.4-mini",
                            "deepseek/deepseek-chat",
                        ],
                    )
                ),
                "agentic_llm": SimpleNamespace(
                    model="gemini/gemini-2.5-flash",
                    _fallback_models=[
                        "gemini/gemini-2.5-flash",
                        "openrouter/openai/gpt-5.4-mini",
                        "deepseek/deepseek-chat",
                    ],
                ),
            }
        )

        model, helper_kwargs = dms._helper_structured_llm_policy(num_retries=2)

        assert model == "gemini/gemini-2.5-flash"
        assert helper_kwargs["num_retries"] == 2
        assert helper_kwargs["fallback_models"] == [
            "openrouter/openai/gpt-5.4-mini",
            "deepseek/deepseek-chat",
        ]
    finally:
        dms._state.clear()
        dms._state.update(original_state)


@pytest.mark.asyncio
async def test_atom_completion_judge_forwards_helper_fallback_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Atom-completion helper calls should pass fallback models into llm_client."""
    _prime_lady_godiva_plan()
    original_state = dict(dms._state)
    captured: dict[str, object] = {}

    async def _fake_acall_llm_structured(model, messages, response_model, **kwargs):
        captured["model"] = model
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return (
            response_model(
                should_mark_done=True,
                resolved_value="Mercia",
                confidence=0.93,
                evidence_refs=["chunk_84"],
                rationale="The evidence names Mercia directly.",
            ),
            SimpleNamespace(),
        )

    monkeypatch.setattr(llm_client, "acall_llm_structured", _fake_acall_llm_structured)
    monkeypatch.setattr(
        llm_client,
        "render_prompt",
        lambda *args, **kwargs: [{"role": "user", "content": "judge this evidence"}],
    )

    try:
        dms._state.clear()
        dms._state.update(
            {
                "config": SimpleNamespace(
                    llm=SimpleNamespace(
                        model="gemini/gemini-2.5-flash",
                        fallback_models=[
                            "openrouter/openai/gpt-5.4-mini",
                            "deepseek/deepseek-chat",
                        ],
                    )
                ),
                "agentic_llm": SimpleNamespace(
                    model="gemini/gemini-2.5-flash",
                    _fallback_models=[
                        "openrouter/openai/gpt-5.4-mini",
                        "deepseek/deepseek-chat",
                    ],
                ),
            }
        )

        update = await dms._infer_atom_completion_with_llm(
            dms._semantic_plan_atom_by_id("a1"),
            dms._todo_item_by_id("a1"),
            {
                "chunks": [
                    {
                        "chunk_id": "chunk_84",
                        "text": "Lady Godiva was associated with Mercia.",
                    }
                ],
                "query_contract": {
                    "effective_query": "What is Lady Godiva's birthplace?",
                },
            },
            tool_name="chunk_retrieve",
            method="by_entities",
        )

        assert update is not None
        assert update["event"] == "atom_autocomplete"
        assert captured["model"] == "gemini/gemini-2.5-flash"
        assert captured["kwargs"]["num_retries"] == 2
        assert captured["kwargs"]["fallback_models"] == [
            "openrouter/openai/gpt-5.4-mini",
            "deepseek/deepseek-chat",
        ]
    finally:
        dms._state.clear()
        dms._state.update(original_state)


@pytest.mark.asyncio
async def test_helper_structured_call_records_fallback_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Helper structured wrapper should persist routing/fallback provenance."""

    class DemoDecision(BaseModel):
        winner: str

    trace_path = tmp_path / ".helper_decision_trace.jsonl"
    monkeypatch.setattr(dms, "_helper_decision_trace_path", lambda: trace_path)

    async def _fake_acall_llm_structured(model, messages, response_model, **kwargs):
        return (
            response_model(winner="Ray Donovan"),
            SimpleNamespace(
                requested_model=model,
                resolved_model="openrouter/openai/gpt-5.4-mini",
                execution_model="openrouter/openai/gpt-5.4-mini",
                routing_trace={
                    "attempted_models": ["gemini/gemini-2.5-flash", "openrouter/openai/gpt-5.4-mini"],
                    "selected_model": "openrouter/openai/gpt-5.4-mini",
                },
                warnings=["FALLBACK: gemini/gemini-2.5-flash -> openrouter/openai/gpt-5.4-mini"],
                warning_records=[{"code": "LLMC_WARN_FALLBACK", "message": "fallback"}],
                usage={"input_tokens": 12, "output_tokens": 4},
                cost=0.01,
                finish_reason="stop",
            ),
        )

    monkeypatch.setattr(llm_client, "acall_llm_structured", _fake_acall_llm_structured)
    dms._current_question = "How many episodes were in the fifth season of the TV series in which The Bag or the Bat appeared?"

    decision, _meta = await dms._call_helper_structured(
        model="gemini/gemini-2.5-flash",
        messages=[{"role": "user", "content": "judge"}],
        response_model=DemoDecision,
        task="digimon.atom_completion",
        trace_id="digimon.atom_completion.demo",
        input_state={"atom_id": "a2", "effective_query": "Ray Donovan season 5 episodes"},
        fallback_models=["openrouter/openai/gpt-5.4-mini"],
    )

    assert decision.winner == "Ray Donovan"
    assert dms._helper_decision_events
    event = dms._helper_decision_events[-1]
    assert event["status"] == "ok"
    assert event["fallback_used"] is True
    assert event["resolved_model"] == "openrouter/openai/gpt-5.4-mini"
    assert event["input_state"]["atom_id"] == "a2"
    assert event["decision_payload"]["winner"] == "Ray Donovan"
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "digimon.atom_completion.demo" in lines[0]
