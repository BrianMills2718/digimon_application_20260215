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
) -> list[PromptVariant]:
    """Build the prompt variants for the extraction prompt experiment."""

    current_prompt = _build_prompt_from_graph_config(graph_config)
    strict_graph_config = graph_config.model_copy(
        update={"strict_extraction_slot_discipline": True}
    )
    strict_prompt = _build_prompt_from_graph_config(strict_graph_config)
    shared_kwargs: dict[str, Any] = {"task": llm_task, "max_budget": max_budget}
    return [
        PromptVariant(
            name="current_contract",
            messages=[{"role": "user", "content": current_prompt}],
            model=subject_model,
            temperature=0.0,
            kwargs=shared_kwargs,
        ),
        PromptVariant(
            name="slot_disciplined_contract",
            messages=[{"role": "user", "content": strict_prompt}],
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
) -> Experiment:
    """Build a prompt_eval experiment over the frozen extraction cases."""

    inputs = [
        ExperimentInput(
            id=case.id,
            content=case.content,
            expected=case.expected.model_dump(),
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
        "--graph-profile",
        choices=[GraphProfile.KG.value.lower(), GraphProfile.TKG.value.lower(), GraphProfile.RKG.value.lower()],
        default=GraphProfile.TKG.value.lower(),
        help="Entity-graph profile to evaluate.",
    )
    parser.add_argument(
        "--schema-mode",
        choices=[mode.value for mode in GraphSchemaMode],
        default=GraphSchemaMode.OPEN.value,
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
        schema_mode=GraphSchemaMode(args.schema_mode),
    )
    subject_model = args.model or get_model("graph_building")
    experiment = build_extraction_prompt_experiment(
        cases=cases,
        graph_config=graph_config,
        subject_model=subject_model,
        llm_task=args.llm_task,
        max_budget=args.max_budget,
        n_runs=args.n_runs,
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
            "current_contract",
            "slot_disciplined_contract",
            method=args.comparison_method,
            comparison_mode="paired_by_input",
        )
    _print_summary(result, comparison, subject_model=subject_model)
    if args.output_json is not None:
        payload = {
            "experiment": result.model_dump(mode="json"),
            "comparison": None if comparison is None else comparison.__dict__,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    """CLI entry point for frozen extraction prompt-eval runs."""

    return asyncio.run(run_cli(parse_args()))


def _build_prompt_from_graph_config(graph_config: GraphConfig) -> str:
    """Render the extraction prompt corresponding to one graph-config contract."""

    entity_types = resolve_entity_type_names(graph_config)
    relation_types = resolve_relation_type_names(graph_config)
    schema_guidance = build_schema_guidance_text(
        graph_config=graph_config,
        entity_types=entity_types,
        relation_types=relation_types,
    )
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
        schema_guidance=schema_guidance,
    )


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
            valid, reason = _validate_entity_attributes(record_attributes, graph_config)
            if valid:
                state.valid_entities += 1
            else:
                state.invalid_reasons.append(reason or "invalid_entity_record")
            continue
        if record_type == '"relationship"':
            state.relationship_records += 1
            valid, reason = _validate_relationship_attributes(record_attributes, graph_config)
            if valid:
                state.valid_relationships += 1
            else:
                state.invalid_reasons.append(reason or "invalid_relationship_record")
            continue
        state.invalid_reasons.append(f"unknown_record_type:{record_type}")
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
    entity_validity = (
        state.valid_entities / state.entity_records if state.entity_records else 0.0
    )
    relationship_validity = (
        state.valid_relationships / state.relationship_records
        if state.relationship_records
        else 0.0
    )
    entity_coverage = min(
        1.0,
        state.valid_entities / max(expectation.min_valid_entities, 1),
    )
    relationship_coverage = min(
        1.0,
        state.valid_relationships / max(expectation.min_valid_relationships, 1),
    )
    return {
        "record_shape": record_shape,
        "entity_validity": entity_validity,
        "relationship_validity": relationship_validity,
        "coverage": (entity_coverage + relationship_coverage) / 2,
    }


def _overall_score(dimension_scores: dict[str, float]) -> float:
    """Weight structural validity higher than mere tuple parseability."""

    return (
        (0.1 * dimension_scores["record_shape"])
        + (0.3 * dimension_scores["entity_validity"])
        + (0.3 * dimension_scores["relationship_validity"])
        + (0.3 * dimension_scores["coverage"])
    )


def _print_summary(result: Any, comparison: Any, *, subject_model: str) -> None:
    """Print a compact human-readable prompt_eval summary."""

    print(f"Model: {subject_model}")
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
