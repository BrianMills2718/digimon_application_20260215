"""Unit tests for the extraction prompt-eval harness."""

from __future__ import annotations

import asyncio
import json
from argparse import Namespace
from pathlib import Path

import pytest
from prompt_eval import EvalResult, VariantSummary

from Config.GraphConfig import GraphConfig
from Core.Common.Constants import (
    DEFAULT_COMPLETION_DELIMITER,
    DEFAULT_RECORD_DELIMITER,
    DEFAULT_TUPLE_DELIMITER,
)
from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode
import eval.extraction_prompt_eval as extraction_prompt_eval
from eval.extraction_prompt_eval import (
    DEFAULT_CASES_PATH,
    build_extraction_output_evaluator,
    build_prompt_variants,
    load_extraction_prompt_eval_cases,
    run_cli,
)


def _tkg_graph_config() -> GraphConfig:
    """Return the TKG graph config used by the extraction prompt-eval harness."""

    return GraphConfig(
        type="er_graph",
        graph_profile=GraphProfile.TKG,
        schema_mode=GraphSchemaMode.OPEN,
    )


def test_load_extraction_prompt_eval_cases_freezes_expected_musique_slice() -> None:
    """The frozen prompt-eval fixture should keep the intended MuSiQue smoke cases."""

    cases = load_extraction_prompt_eval_cases(DEFAULT_CASES_PATH)
    assert [case.source_doc_id for case in cases] == [1, 1, 1, 5, 5, 9, 9]
    assert [case.id for case in cases] == [
        "musique_doc_1_barcelona_2006_07",
        "musique_doc_1_grounded_form_fitness",
        "musique_doc_1_grounded_copa_del_rey",
        "musique_doc_5_vilanova_2012_2013",
        "musique_doc_5_grounded_medical_leave",
        "musique_doc_9_messi_2015_2016",
        "musique_doc_9_grounded_silver_ball",
    ]


def test_build_prompt_variants_adds_grounded_entity_variant() -> None:
    """Prompt iteration should compare the strict contract against a grounded-entity variant."""

    variants = build_prompt_variants(
        graph_config=_tkg_graph_config(),
        subject_model="test-model",
        llm_task="digimon.extraction.prompt_eval",
        max_budget=1.0,
    )
    assert [variant.name for variant in variants] == [
        "slot_disciplined_contract",
        "grounded_entity_contract",
    ]
    assert "-Slot Discipline-" in variants[0].messages[0]["content"]
    assert "-Grounded Entity Preference-" not in variants[0].messages[0]["content"]
    assert "-Grounded Entity Preference-" in variants[1].messages[0]["content"]


def test_extraction_output_evaluator_rewards_structurally_valid_tkg_output() -> None:
    """A clean TKG extraction output should get full structural credit."""

    evaluator = build_extraction_output_evaluator(_tkg_graph_config())
    output = (
        f'("entity"{DEFAULT_TUPLE_DELIMITER}"Barcelona"{DEFAULT_TUPLE_DELIMITER}"organization"'
        f'{DEFAULT_TUPLE_DELIMITER}"Spanish football club"){DEFAULT_RECORD_DELIMITER}'
        f'("entity"{DEFAULT_TUPLE_DELIMITER}"Sevilla"{DEFAULT_TUPLE_DELIMITER}"organization"'
        f'{DEFAULT_TUPLE_DELIMITER}"Spanish football club"){DEFAULT_RECORD_DELIMITER}'
        f'("relationship"{DEFAULT_TUPLE_DELIMITER}"Barcelona"{DEFAULT_TUPLE_DELIMITER}"Sevilla"'
        f'{DEFAULT_TUPLE_DELIMITER}"defeated"{DEFAULT_TUPLE_DELIMITER}"Barcelona beat Sevilla in the UEFA Super Cup"'
        f"{DEFAULT_TUPLE_DELIMITER}8){DEFAULT_COMPLETION_DELIMITER}"
    )

    score = evaluator(
        output,
        {"min_valid_entities": 2, "min_valid_relationships": 1},
    )
    assert score.score == pytest.approx(1.0)
    assert score.dimension_scores == {
        "record_shape": 1.0,
        "entity_validity": 1.0,
        "relationship_validity": 1.0,
        "coverage": 1.0,
    }


def test_extraction_output_evaluator_penalizes_invalid_slots_and_missing_types() -> None:
    """Known-bad Plan #5 failure modes should be penalized deterministically."""

    evaluator = build_extraction_output_evaluator(_tkg_graph_config())
    output = (
        f'("entity"{DEFAULT_TUPLE_DELIMITER}"sextuple"{DEFAULT_TUPLE_DELIMITER}"None"'
        f'{DEFAULT_TUPLE_DELIMITER}"season achievement"){DEFAULT_RECORD_DELIMITER}'
        f'("relationship"{DEFAULT_TUPLE_DELIMITER}"located in"{DEFAULT_TUPLE_DELIMITER}"tear"'
        f'{DEFAULT_TUPLE_DELIMITER}"part of"{DEFAULT_TUPLE_DELIMITER}"malformed slot inversion"'
        f"{DEFAULT_TUPLE_DELIMITER}7){DEFAULT_COMPLETION_DELIMITER}"
    )

    score = evaluator(
        output,
        {"min_valid_entities": 1, "min_valid_relationships": 1},
    )
    assert score.score < 0.25
    assert "missing_entity_type_for_typed_profile" in score.reasoning
    assert "relationship_subject_looks_like_predicate" in score.reasoning


def test_extraction_output_evaluator_scores_grounded_entity_cases_without_relationship_penalty() -> None:
    """Entity-policy cases with no expected relationships should not be penalized for omitting them."""

    evaluator = build_extraction_output_evaluator(_tkg_graph_config())
    output = (
        f'("entity"{DEFAULT_TUPLE_DELIMITER}"Ronaldinho"{DEFAULT_TUPLE_DELIMITER}"person"'
        f'{DEFAULT_TUPLE_DELIMITER}"Brazilian footballer"){DEFAULT_COMPLETION_DELIMITER}'
    )

    score = evaluator(
        output,
        {
            "min_valid_entities": 1,
            "min_valid_relationships": 0,
            "required_entity_names": ["Ronaldinho"],
            "forbidden_entity_names": ["form", "fitness"],
        },
    )

    assert score.score == pytest.approx(1.0)
    assert score.dimension_scores["relationship_validity"] == pytest.approx(1.0)
    assert score.dimension_scores["coverage"] == pytest.approx(1.0)
    assert score.dimension_scores["entity_policy"] == pytest.approx(1.0)


def test_run_cli_allows_single_case_smoke_runs_without_comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A one-case smoke run should skip paired comparison instead of crashing."""

    output_json = tmp_path / "prompt_eval_smoke.json"

    async def fake_run_experiment(*args: object, **kwargs: object) -> EvalResult:
        return EvalResult(
            experiment_name="musique_tkg_extraction_prompt_eval",
            execution_id="exec_single_case",
            variants=["slot_disciplined_contract", "grounded_entity_contract"],
            trials=[],
            summary={
                "slot_disciplined_contract": VariantSummary(
                    variant_name="slot_disciplined_contract",
                    n_trials=1,
                    mean_score=0.7,
                ),
                "grounded_entity_contract": VariantSummary(
                    variant_name="grounded_entity_contract",
                    n_trials=1,
                    mean_score=0.9,
                ),
            },
        )

    # mock-ok: the single-case smoke-path regression is about CLI control flow,
    # not prompt_eval's provider execution, which is tested upstream.
    monkeypatch.setattr(extraction_prompt_eval, "run_experiment", fake_run_experiment)

    args = Namespace(
        cases_file=DEFAULT_CASES_PATH,
        graph_profile="tkg",
        schema_mode="open",
        model="test-model",
        llm_task="digimon.extraction.prompt_eval",
        max_budget=1.0,
        n_runs=1,
        case_limit=1,
        project="Digimon_for_KG_application",
        dataset="musique_tkg_extraction_prompt_eval_smoke",
        disable_observability=True,
        output_json=output_json,
    )

    exit_code = asyncio.run(run_cli(args))
    assert exit_code == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["comparison"] is None
