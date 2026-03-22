"""Run prompt_eval experiments for DIGIMON extraction prompt variants.

This module gives Plan #5 a reproducible prompt-iteration surface over a small
frozen MuSiQue slice. It compares prompt variants against real extraction cases
and scores them with deterministic structural validators before any larger
smoke-build or graph rebuild work.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from llm_client import get_model
from prompt_eval import (
    EvalScore,
    Experiment,
    ExperimentInput,
    PromptEvalObservabilityConfig,
    PromptVariant,
    compare_variants,
    run_experiment,
)

from Config.GraphConfig import GraphConfig
from Core.Common.Constants import (
    DEFAULT_COMPLETION_DELIMITER,
    DEFAULT_RECORD_DELIMITER,
    DEFAULT_TUPLE_DELIMITER,
)
from Core.Common.Utils import clean_str, split_string_by_multi_markers
from Core.Common.extraction_validation import (
    strip_extraction_field_markup,
    validate_entity_record,
    validate_relationship_record,
)
from Core.Common.graph_schema_guidance import (
    build_schema_guidance_text,
    resolve_entity_type_names,
    resolve_relation_type_names,
)
from Core.Prompt import GraphPrompt
from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode


DEFAULT_CASES_PATH = Path(__file__).with_name("fixtures") / "musique_tkg_extraction_prompt_eval_cases.json"
DEFAULT_DATASET_NAME = "musique_tkg_extraction_prompt_eval"
DEFAULT_PROJECT_NAME = "Digimon_for_KG_application"
_RECORD_PATTERN = re.compile(r"\((.*)\)")
PROMPT_FAMILY_ONE_PASS = "one_pass"
PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY = "two_pass_entity_inventory"


class ExtractionPromptEvalExpectation(BaseModel):
    """Minimum structural expectations for one frozen extraction case."""

    min_valid_entities: int = Field(
        default=1,
        ge=0,
        description="Minimum number of structurally valid entity records expected from the case.",
    )
    min_valid_relationships: int = Field(
        default=1,
        ge=0,
        description="Minimum number of structurally valid relationship records expected from the case.",
    )
    required_entity_names: list[str] = Field(
        default_factory=list,
        description="Entity names that should remain extractable under the intended policy.",
    )
    forbidden_entity_names: list[str] = Field(
        default_factory=list,
        description="Entity names that should not survive under the intended grounded-entity policy.",
    )


class ExtractionPromptEvalCase(BaseModel):
    """One frozen real-corpus extraction case for prompt comparison."""

    id: str
    source_doc_id: int
    title: str
    focus: str
    content: str
    expected: ExtractionPromptEvalExpectation = Field(
        default_factory=ExtractionPromptEvalExpectation
    )


@dataclass
class _ExtractionScoreState:
    """Accumulate structural extraction-quality counts for one model output."""

    total_records: int = 0
    parseable_records: int = 0
    entity_records: int = 0
    relationship_records: int = 0
    valid_entities: int = 0
    valid_relationships: int = 0
    emitted_entity_names: list[str] = field(default_factory=list)
    valid_entity_names: list[str] = field(default_factory=list)
    candidate_relationship_pairs: list[tuple[str, str]] = field(default_factory=list)
    invalid_reasons: list[str] = field(default_factory=list)


def load_extraction_prompt_eval_cases(path: Path) -> list[ExtractionPromptEvalCase]:
    """Load the frozen prompt-eval cases from a JSON file."""

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError(
            f"Extraction prompt-eval cases must be a JSON list, got {type(loaded).__name__}"
        )
    return [ExtractionPromptEvalCase.model_validate(item) for item in loaded]


def build_prompt_variants(
    *,
    graph_config: GraphConfig,
    subject_model: str,
    llm_task: str,
    max_budget: float,
    prompt_family: str = PROMPT_FAMILY_ONE_PASS,
) -> list[PromptVariant]:
    """Build the prompt variants for the extraction prompt experiment."""

    strict_graph_config = graph_config.model_copy(
        update={"strict_extraction_slot_discipline": True}
    )
    grounded_graph_config = strict_graph_config.model_copy(
        update={"prefer_grounded_named_entities": True}
    )
    strict_prompt = _build_prompt_from_graph_config(
        strict_graph_config,
        prompt_family=prompt_family,
    )
    grounded_prompt = _build_prompt_from_graph_config(
        grounded_graph_config,
        prompt_family=prompt_family,
    )
    shared_kwargs: dict[str, Any] = {"task": llm_task, "max_budget": max_budget}
    return [
        PromptVariant(
            name="slot_disciplined_contract",
            messages=[{"role": "user", "content": strict_prompt}],
            model=subject_model,
            temperature=0.0,
            kwargs=shared_kwargs,
        ),
        PromptVariant(
            name="grounded_entity_contract",
            messages=[{"role": "user", "content": grounded_prompt}],
            model=subject_model,
            temperature=0.0,
            kwargs=shared_kwargs,
        ),
    ]


def build_extraction_prompt_experiment(
    *,
    cases: list[ExtractionPromptEvalCase],
    graph_config: GraphConfig,
    subject_model: str,
    llm_task: str,
    max_budget: float,
    n_runs: int,
    prompt_family: str = PROMPT_FAMILY_ONE_PASS,
) -> Experiment:
    """Build a prompt_eval experiment over the frozen extraction cases."""

    inputs = [
        ExperimentInput(
            id=case.id,
            content=case.content,
            expected=_normalize_expectation_for_prompt_family(
                case.expected,
                prompt_family=prompt_family,
            ).model_dump(),
        )
        for case in cases
    ]
    return Experiment(
        name=DEFAULT_DATASET_NAME,
        variants=build_prompt_variants(
            graph_config=graph_config,
            subject_model=subject_model,
            llm_task=llm_task,
            max_budget=max_budget,
            prompt_family=prompt_family,
        ),
        inputs=inputs,
        n_runs=n_runs,
    )


def build_extraction_output_evaluator(graph_config: GraphConfig) -> Any:
    """Return a deterministic evaluator for extraction structural quality."""

    def evaluate(output: Any, expected: Any = None) -> EvalScore:
        expectation = ExtractionPromptEvalExpectation.model_validate(expected or {})
        state = _score_extraction_output(str(output), graph_config)
        dimension_scores = _dimension_scores(state, expectation)
        overall = _overall_score(dimension_scores)
        invalid_reason_counts = Counter(state.invalid_reasons)
        common_invalid_reasons = ", ".join(
            f"{reason} x{count}"
            for reason, count in invalid_reason_counts.most_common(3)
        )
        reasoning = (
            "records="
            f"{state.parseable_records}/{state.total_records}, "
            f"valid_entities={state.valid_entities}/{state.entity_records}, "
            f"valid_relationships={state.valid_relationships}/{state.relationship_records}"
        )
        if common_invalid_reasons:
            reasoning = f"{reasoning}; invalid={common_invalid_reasons}"
        return EvalScore(
            score=overall,
            dimension_scores=dimension_scores,
            reasoning=reasoning,
        )

    return evaluate


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the extraction prompt-eval harness."""

    parser = argparse.ArgumentParser(
        description="Run prompt_eval over frozen DIGIMON extraction prompt cases."
    )
    parser.add_argument(
        "--cases-file",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="JSON file containing frozen extraction prompt-eval cases.",
    )
    parser.add_argument(
        "--prompt-family",
        choices=[PROMPT_FAMILY_ONE_PASS, PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY],
        default=PROMPT_FAMILY_ONE_PASS,
        help=(
            "Prompt family to evaluate. two_pass_entity_inventory isolates the "
            "first-pass entity inventory prompt and neutralizes relationship expectations."
        ),
    )
    parser.add_argument(
        "--graph-profile",
        choices=[GraphProfile.KG.value.lower(), GraphProfile.TKG.value.lower(), GraphProfile.RKG.value.lower()],
        default=GraphProfile.TKG.value.lower(),
        help="Entity-graph profile to evaluate.",
    )
    parser.add_argument(
        "--schema-mode",
        type=GraphSchemaMode.parse,
        default=GraphSchemaMode.OPEN,
        help="Schema-guidance mode to apply while building prompt variants.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional explicit model override. Defaults to llm_client.get_model('graph_building').",
    )
    parser.add_argument(
        "--llm-task",
        default="digimon.extraction.prompt_eval",
        help="llm_client task label recorded for prompt-eval trials.",
    )
    parser.add_argument(
        "--max-budget",
        type=float,
        default=1.0,
        help="Per-call llm_client max_budget to record in prompt_eval trial metadata.",
    )
    parser.add_argument(
        "--n-runs",
        type=int,
        default=1,
        help="Number of replicates per variant and input.",
    )
    parser.add_argument(
        "--case-limit",
        type=int,
        default=None,
        help="Optional limit for a smaller live smoke run.",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT_NAME,
        help="Observability project name for prompt_eval runs.",
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET_NAME,
        help="Observability dataset name for prompt_eval runs.",
    )
    parser.add_argument(
        "--disable-observability",
        action="store_true",
        help="Disable llm_client observability emission for the prompt_eval run.",
    )
    parser.add_argument(
        "--comparison-method",
        choices=["paired_t", "bootstrap"],
        default="paired_t",
        help="Comparison method for multi-case paired runs. Defaults to paired_t for current SciPy compatibility.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the experiment result and comparison payload as JSON.",
    )
    return parser.parse_args()


async def run_cli(args: argparse.Namespace) -> int:
    """Execute the configured prompt_eval run and print a compact summary."""

    cases = load_extraction_prompt_eval_cases(args.cases_file)
    if args.case_limit is not None:
        cases = cases[: args.case_limit]
    if not cases:
        raise ValueError("Prompt-eval requires at least one frozen extraction case.")

    graph_config = GraphConfig(
        type="er_graph",
        graph_profile=GraphProfile(args.graph_profile.upper()),
        schema_mode=args.schema_mode,
    )
    subject_model = args.model or get_model("graph_building")
    experiment = build_extraction_prompt_experiment(
        cases=cases,
        graph_config=graph_config,
        subject_model=subject_model,
        llm_task=args.llm_task,
        max_budget=args.max_budget,
        n_runs=args.n_runs,
        prompt_family=args.prompt_family,
    )
    observability: bool | PromptEvalObservabilityConfig
    if args.disable_observability:
        observability = False
    else:
        observability = PromptEvalObservabilityConfig(
            project=args.project,
            dataset=args.dataset,
        )
    result = await run_experiment(
        experiment,
        evaluator=build_extraction_output_evaluator(graph_config),
        observability=observability,
    )
    comparison = None
    if len(cases) >= 2:
        comparison = compare_variants(
            result,
            "slot_disciplined_contract",
            "grounded_entity_contract",
            method=args.comparison_method,
            comparison_mode="paired_by_input",
        )
    _print_summary(
        result,
        comparison,
        subject_model=subject_model,
        prompt_family=args.prompt_family,
    )
    if args.output_json is not None:
        payload = {
            "prompt_family": args.prompt_family,
            "experiment": result.model_dump(mode="json"),
            "comparison": None if comparison is None else comparison.__dict__,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    """CLI entry point for frozen extraction prompt-eval runs."""

    return asyncio.run(run_cli(parse_args()))


def _build_prompt_from_graph_config(graph_config: GraphConfig, *, prompt_family: str) -> str:
    """Render the extraction prompt corresponding to one graph-config contract."""

    entity_types = resolve_entity_type_names(graph_config)
    relation_types = resolve_relation_type_names(graph_config)
    schema_guidance = build_schema_guidance_text(
        graph_config=graph_config,
        entity_types=entity_types,
        relation_types=relation_types,
    )
    if prompt_family == PROMPT_FAMILY_ONE_PASS:
        return GraphPrompt.build_entity_extraction_prompt(
            input_text="{input}",
            entity_types=entity_types,
            relation_types=relation_types,
            tuple_delimiter=DEFAULT_TUPLE_DELIMITER,
            record_delimiter=DEFAULT_RECORD_DELIMITER,
            completion_delimiter=DEFAULT_COMPLETION_DELIMITER,
            include_relation_name=graph_config.enable_edge_name,
            include_relation_keywords=graph_config.enable_edge_keywords,
            include_slot_discipline=graph_config.strict_extraction_slot_discipline,
            include_grounded_entity_preference=graph_config.prefer_grounded_named_entities,
            schema_guidance=schema_guidance,
        )
    if prompt_family == PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY:
        return GraphPrompt.build_entity_inventory_extraction_prompt(
            input_text="{input}",
            entity_types=entity_types,
            tuple_delimiter=DEFAULT_TUPLE_DELIMITER,
            record_delimiter=DEFAULT_RECORD_DELIMITER,
            completion_delimiter=DEFAULT_COMPLETION_DELIMITER,
            include_slot_discipline=graph_config.strict_extraction_slot_discipline,
            include_grounded_entity_preference=graph_config.prefer_grounded_named_entities,
            schema_guidance=schema_guidance,
        )
    raise ValueError(f"Unsupported prompt family: {prompt_family}")


def _normalize_expectation_for_prompt_family(
    expectation: ExtractionPromptEvalExpectation,
    *,
    prompt_family: str,
) -> ExtractionPromptEvalExpectation:
    """Adapt frozen-case expectations to the prompt family under evaluation.

    The two-pass entity-inventory slice only evaluates pass-1 entity extraction,
    so relationship minimums must be treated as neutral rather than as missing
    evidence. Entity keep/drop requirements remain part of the contract.
    """

    normalized = expectation.model_copy(deep=True)
    if prompt_family == PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY:
        normalized.min_valid_relationships = 0
    return normalized


def _score_extraction_output(output: str, graph_config: GraphConfig) -> _ExtractionScoreState:
    """Score one raw extraction output for structural validity."""

    state = _ExtractionScoreState()
    for record in _split_records(output):
        state.total_records += 1
        record_attributes = _parse_record_attributes(record)
        if record_attributes is None:
            state.invalid_reasons.append("unparseable_record")
            continue
        state.parseable_records += 1
        record_type = record_attributes[0]
        if record_type == '"entity"':
            state.entity_records += 1
            cleaned_entity_name = clean_str(record_attributes[1])
            state.emitted_entity_names.append(cleaned_entity_name)
            valid, reason = _validate_entity_attributes(record_attributes, graph_config)
            if valid:
                state.valid_entities += 1
                state.valid_entity_names.append(cleaned_entity_name)
            else:
                state.invalid_reasons.append(reason or "invalid_entity_record")
            continue
        if record_type == '"relationship"':
            state.relationship_records += 1
            valid, reason = _validate_relationship_attributes(record_attributes, graph_config)
            if valid:
                state.candidate_relationship_pairs.append(
                    (
                        clean_str(record_attributes[1]),
                        clean_str(record_attributes[2]),
                    )
                )
            else:
                state.invalid_reasons.append(reason or "invalid_relationship_record")
            continue
        state.invalid_reasons.append(f"unknown_record_type:{record_type}")
    _apply_entity_relationship_closure(state)
    return state


def _split_records(output: str) -> list[str]:
    """Split one raw extraction output into delimiter-separated records."""

    return [
        record.strip()
        for record in split_string_by_multi_markers(
            output,
            [DEFAULT_RECORD_DELIMITER, DEFAULT_COMPLETION_DELIMITER],
        )
        if record.strip()
    ]


def _parse_record_attributes(record: str) -> list[str] | None:
    """Parse the tuple-delimited attributes from one raw record string."""

    match = _RECORD_PATTERN.search(record)
    if match is None:
        return None
    return [
        strip_extraction_field_markup(attribute)
        for attribute in split_string_by_multi_markers(
            match.group(1),
            [DEFAULT_TUPLE_DELIMITER],
        )
    ]


def _validate_entity_attributes(
    record_attributes: list[str],
    graph_config: GraphConfig,
) -> tuple[bool, str | None]:
    """Validate one parsed entity record under the configured graph profile."""

    if len(record_attributes) < 4:
        return False, "entity_record_too_short"
    entity_name = clean_str(record_attributes[1])
    entity_type = clean_str(record_attributes[2])
    return validate_entity_record(
        entity_name,
        entity_type,
        entity_description=record_attributes[3],
        require_typed_entities=graph_config.enable_entity_type,
    )


def _validate_relationship_attributes(
    record_attributes: list[str],
    graph_config: GraphConfig,
) -> tuple[bool, str | None]:
    """Validate one parsed relationship record under the configured graph profile."""

    minimum_length = 6 if graph_config.enable_edge_name else 5
    if len(record_attributes) < minimum_length:
        return False, "relationship_record_too_short"
    relation_name = ""
    if graph_config.enable_edge_name:
        relation_name = clean_str(record_attributes[3])
    src_id = clean_str(record_attributes[1])
    tgt_id = clean_str(record_attributes[2])
    return validate_relationship_record(
        src_id,
        tgt_id,
        relation_name,
        require_relation_name=graph_config.enable_edge_name,
    )


def _dimension_scores(
    state: _ExtractionScoreState,
    expectation: ExtractionPromptEvalExpectation,
) -> dict[str, float]:
    """Compute stable score dimensions from one extraction output state."""

    record_shape = (
        state.parseable_records / state.total_records if state.total_records else 0.0
    )
    entity_validity = _validity_ratio(
        valid_count=state.valid_entities,
        total_count=state.entity_records,
        expected_minimum=expectation.min_valid_entities,
    )
    relationship_validity = _validity_ratio(
        valid_count=state.valid_relationships,
        total_count=state.relationship_records,
        expected_minimum=expectation.min_valid_relationships,
    )
    entity_coverage = _coverage_ratio(
        observed_count=state.valid_entities,
        expected_minimum=expectation.min_valid_entities,
    )
    relationship_coverage = _coverage_ratio(
        observed_count=state.valid_relationships,
        expected_minimum=expectation.min_valid_relationships,
    )
    dimension_scores: dict[str, float] = {
        "record_shape": record_shape,
        "entity_validity": entity_validity,
        "relationship_validity": relationship_validity,
        "coverage": (entity_coverage + relationship_coverage) / 2,
    }
    entity_policy = _entity_policy_score(state, expectation)
    if entity_policy is not None:
        dimension_scores["entity_policy"] = entity_policy
    return dimension_scores


def _overall_score(dimension_scores: dict[str, float]) -> float:
    """Weight only the score dimensions that are active for the current case."""

    weights = {
        "record_shape": 0.1,
        "entity_validity": 0.25,
        "relationship_validity": 0.25,
        "coverage": 0.2,
        "entity_policy": 0.2,
    }
    active_weight = sum(weights[name] for name in dimension_scores)
    if active_weight <= 0:
        return 0.0
    weighted_score = sum(
        weights[name] * score for name, score in dimension_scores.items()
    )
    return weighted_score / active_weight


def _entity_policy_score(
    state: _ExtractionScoreState,
    expectation: ExtractionPromptEvalExpectation,
) -> float | None:
    """Score whether required entities are kept and forbidden ones are suppressed."""

    emitted_entities = {
        clean_str(name) for name in state.emitted_entity_names if clean_str(name)
    }
    valid_entities = {
        clean_str(name) for name in state.valid_entity_names if clean_str(name)
    }
    required = {clean_str(name) for name in expectation.required_entity_names if clean_str(name)}
    forbidden = {clean_str(name) for name in expectation.forbidden_entity_names if clean_str(name)}

    if not required and not forbidden:
        return None

    required_recall = 1.0
    if required:
        required_recall = sum(name in valid_entities for name in required) / len(required)

    forbidden_precision = 1.0
    if forbidden:
        forbidden_hits = sum(name in emitted_entities for name in forbidden)
        forbidden_precision = 1.0 - (forbidden_hits / len(forbidden))

    return (required_recall + forbidden_precision) / 2


def _validity_ratio(*, valid_count: int, total_count: int, expected_minimum: int) -> float:
    """Return a validity ratio that stays neutral when a case expects no records of that kind."""

    if total_count:
        return valid_count / total_count
    return 1.0 if expected_minimum == 0 else 0.0


def _coverage_ratio(*, observed_count: int, expected_minimum: int) -> float:
    """Return coverage against the frozen expectation, treating zero-required cases as satisfied."""

    if expected_minimum == 0:
        return 1.0
    return min(1.0, observed_count / expected_minimum)


def _apply_entity_relationship_closure(state: _ExtractionScoreState) -> None:
    """Count only relationships whose endpoints are backed by emitted entity records."""

    valid_entity_names = {name for name in state.valid_entity_names if name}
    valid_relationships = 0
    for src_id, tgt_id in state.candidate_relationship_pairs:
        if src_id in valid_entity_names and tgt_id in valid_entity_names:
            valid_relationships += 1
            continue
        state.invalid_reasons.append("relationship_endpoint_missing_entity_record")
    state.valid_relationships = valid_relationships


def _print_summary(
    result: Any,
    comparison: Any,
    *,
    subject_model: str,
    prompt_family: str,
) -> None:
    """Print a compact human-readable prompt_eval summary."""

    print(f"Model: {subject_model}")
    print(f"Prompt family: {prompt_family}")
    print(f"Execution ID: {result.execution_id}")
    for variant_name in result.variants:
        summary = result.summary[variant_name]
        print(
            f"{variant_name}: mean_score={summary.mean_score:.3f} "
            f"n_trials={summary.n_trials} n_errors={summary.n_errors} "
            f"mean_cost={summary.mean_cost:.4f} mean_latency_ms={summary.mean_latency_ms:.1f}"
        )
    if comparison is None:
        print("comparison: skipped (paired-by-input comparison requires at least 2 frozen cases)")
        return
    print(
        "comparison: "
        f"{comparison.variant_a} - {comparison.variant_b} = {comparison.difference:.4f} "
        f"CI=[{comparison.ci_lower:.4f}, {comparison.ci_upper:.4f}] "
        f"significant={comparison.significant} units={comparison.n_units}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
