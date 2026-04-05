"""Tests for the normalized benchmark trace renderer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "diagnose_question.py"
    )
    spec = importlib.util.spec_from_file_location("diagnose_question", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _question(predicted: str = "by force", atom_3_value: str = "Somali Muslim Ajuran Empire") -> dict:
    return {
        "id": "4hop3__754156_88460_30152_20999",
        "question": "How were the people from whom new coins were a proclamation of independence by the Somali Muslim Ajuran Empire expelled from the country between Thailand and A Lim's country?",
        "gold": "The dynasty regrouped and defeated the Portuguese",
        "predicted": predicted,
        "llm_em": 0,
        "submit_completion_mode": "missing_required_submit",
        "submit_answer_succeeded": False,
        "submit_validator_accepted": False,
        "submit_pending_atom_ids": ["atom_4"],
        "forced_terminal_accept_reason": "budget_exhaustion",
        "primary_failure_class": "control_churn",
        "secondary_failure_classes": ["answer_type_mismatch"],
        "failure_event_codes": ["SUBMIT_FORCED_ACCEPT_BUDGET_EXHAUSTION"],
        "helper_models_used": ["gemini/gemini-2.5-flash"],
        "helper_fallback_used": False,
        "n_tool_calls": 12,
        "duration_ms": 12345,
        "finalization_events": ["FINALIZATION_PRIMARY_SUCCEEDED"],
        "required_submit_missing": True,
        "submit_forced_accept_on_budget_exhaustion": True,
        "forced_final_attempts": 1,
        "retrieval_stagnation_triggered": False,
        "retrieval_stagnation_turn": None,
        "lane_closure_analysis": {"lane_closed": True},
        "helper_decision_event_count": 2,
        "atom_lifecycle_event_count": 4,
        "submit_answer_call_count": 3,
        "helper_decision_trace": [
            {
                "event_type": "helper_structured_call",
                "task": "digimon.semantic_plan.revise",
                "requested_model": "gemini/gemini-2.5-flash",
                "resolved_model": "gemini/gemini-2.5-flash",
                "fallback_used": False,
                "input_state": {"phase": "revise"},
                "decision_payload": {
                    "final_answer_kind": "text",
                    "composition_rule": "atom_4 depends on atom_2 and atom_3.",
                    "uncertainty_points": ["A Lim is ambiguous."],
                    "atoms": [
                        {
                            "atom_id": "atom_1",
                            "sub_question": "What is the country of A Lim?",
                            "operation": "Lookup->Location",
                            "answer_kind": "entity",
                            "output_var": "country_of_A_Lim",
                            "depends_on": [],
                            "done_criteria": "Evidence identifying A Lim's country.",
                        },
                        {
                            "atom_id": "atom_3",
                            "sub_question": "Which people were involved in a proclamation of independence by the Somali Muslim Ajuran Empire with new coins?",
                            "operation": "Relation",
                            "answer_kind": "entity",
                            "output_var": "people_with_new_coins",
                            "depends_on": [],
                            "done_criteria": "Evidence identifying the people.",
                        },
                    ],
                },
            }
        ],
        "tool_details": [
            {
                "tool": "semantic_plan",
                "arguments": {"question": "How were the people ..."},
                "tool_reasoning": "Decompose the question.",
                "has_result": True,
                "has_error": False,
                "error": None,
                "result_preview": "{\"final_answer_kind\": \"text\"}",
                "latency_s": 10.5,
            },
            {
                "tool": "chunk_retrieve",
                "arguments": {
                    "method": "text",
                    "query_text": "Ajuran Empire new coins proclamation independence people expelled",
                    "dataset_name": "MuSiQue",
                },
                "tool_reasoning": "Ground the Ajuran clue.",
                "has_result": True,
                "has_error": False,
                "error": None,
                "result_preview": "Atom atom_3 completed: Somali Muslim Ajuran Empire.",
                "latency_s": 0.8,
            },
        ],
        "atom_lifecycle_trace": [
            {
                "event": "atom_completed",
                "atom_id": "atom_1",
                "sub_question": "What is the country of A Lim?",
                "resolved_value": "Laos",
                "confidence": 1.0,
                "tool_name": "entity_search",
                "method": "string",
                "rationale": "A Lim is in Laos.",
                "evidence_refs": ["chunk_220"],
            },
            {
                "event": "atom_completed",
                "atom_id": "atom_3",
                "sub_question": "Which people were involved in a proclamation of independence by the Somali Muslim Ajuran Empire with new coins?",
                "resolved_value": atom_3_value,
                "confidence": 1.0,
                "tool_name": "chunk_retrieve",
                "method": "text",
                "rationale": "The evidence directly states that the 'Somali Muslim Ajuran Empire' employed new coinage as a proclamation of economic independence.",
                "evidence_refs": ["chunk_217"],
            },
            {
                "event": "atom_judged_unresolved",
                "atom_id": "atom_4",
                "sub_question": "How were those people expelled from that country?",
                "confidence": 0.0,
                "tool_name": "chunk_retrieve",
                "method": "text",
                "rationale": "No relevant expulsion evidence found.",
            },
        ],
    }


def test_render_question_trace_includes_normalized_sections(tmp_path: Path) -> None:
    module = _load_module()
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps({"results": [_question()]}), encoding="utf-8")

    question = module.load_question(str(result_file), "4hop3__754156_88460_30152_20999")
    rendered = module.render_question_trace(question, result_file=str(result_file))

    assert "TRACE: 4hop3__754156_88460_30152_20999" in rendered
    assert "[SEMANTIC PLAN]" in rendered
    assert "atom_3: Which people were involved in a proclamation of independence by the Somali Muslim Ajuran Empire with new coins?" in rendered
    assert "[HELPER DECISION TRACE]" in rendered
    assert "digimon.semantic_plan.revise" in rendered
    assert "[TOOL TRACE]" in rendered
    assert "chunk_retrieve [OK]" in rendered
    assert "[ATOM LIFECYCLE TRACE]" in rendered
    assert "resolved_value: Somali Muslim Ajuran Empire" in rendered
    assert "[TERMINAL ANALYSIS]" in rendered


def test_render_trace_diff_highlights_changed_completion() -> None:
    module = _load_module()
    question_a = _question(predicted="by force", atom_3_value="Somali Muslim Ajuran Empire")
    question_b = _question(
        predicted="The dynasty regrouped and defeated the Portuguese",
        atom_3_value="Portuguese",
    )

    rendered = module.render_trace_diff(
        question_a,
        question_b,
        label_a="run_a.json",
        label_b="run_b.json",
    )

    assert "TRACE DIFF: 4hop3__754156_88460_30152_20999" in rendered
    assert "predicted:" in rendered
    assert "A=Somali Muslim Ajuran Empire | B=Portuguese" in rendered
    assert "[SEMANTIC PLAN DELTA]" in rendered
