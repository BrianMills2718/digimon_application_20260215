#!/usr/bin/env python3
"""Summarize repeated benchmark artifacts into a stable iteration report.

This script turns a set of benchmark result JSON artifacts into a compact
distribution summary so iteration decisions come from repeated evidence rather
than a single lucky or unlucky run.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.runtime_paths import benchmark_glob_roots


@dataclass(frozen=True)
class QuestionObservation:
    """One question outcome within a single benchmark artifact."""

    question_id: str
    gold: str
    predicted: str
    llm_em: float
    em: float
    failure_class: str


@dataclass(frozen=True)
class RunArtifact:
    """A parsed benchmark artifact with compact fields for iteration reporting."""

    path: Path
    dataset: str
    model: str
    n_questions: int
    n_completed: int
    llm_em_percent: float
    em_percent: float
    total_cost: float
    results: tuple[QuestionObservation, ...]


def _load_json(path: Path) -> dict[str, Any]:
    """Load a benchmark artifact and fail loudly if the shape is unsupported."""
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def load_run_artifact(path: Path) -> RunArtifact:
    """Parse a benchmark result JSON into a normalized run artifact."""
    payload = _load_json(path)
    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError(f"Artifact {path} is missing a non-empty 'results' list")

    results: list[QuestionObservation] = []
    for item in raw_results:
        if not isinstance(item, dict):
            raise ValueError(f"Artifact {path} contains a non-object result entry")
        results.append(
            QuestionObservation(
                question_id=str(item.get("id", "")),
                gold=str(item.get("gold", "")),
                predicted=str(item.get("predicted", "")),
                llm_em=float(item.get("llm_em", 0) or 0),
                em=float(item.get("em", 0) or 0),
                failure_class=str(item.get("primary_failure_class", "unknown") or "unknown"),
            )
        )

    dataset = str(payload.get("dataset", "")).strip()
    model = str(payload.get("model", "")).strip()
    if not dataset or not model:
        raise ValueError(f"Artifact {path} is missing dataset/model metadata")

    llm_em_percent = round(
        (sum(observation.llm_em for observation in results) / len(results)) * 100,
        2,
    )
    em_percent = round(
        (sum(observation.em for observation in results) / len(results)) * 100,
        2,
    )

    return RunArtifact(
        path=path,
        dataset=dataset,
        model=model,
        n_questions=int(payload.get("n_questions") or len(results)),
        n_completed=int(payload.get("n_completed") or 0),
        llm_em_percent=llm_em_percent,
        em_percent=em_percent,
        total_cost=float(payload.get("total_cost", 0) or 0),
        results=tuple(results),
    )


def _sample_stdev(values: list[float]) -> float:
    """Return sample standard deviation, or 0 for a single observation."""
    if len(values) < 2:
        return 0.0
    return float(statistics.stdev(values))


def _classify_question(pass_rate: float) -> str:
    """Map pass-rate to a compact stability label."""
    if math.isclose(pass_rate, 100.0):
        return "stable_pass"
    if math.isclose(pass_rate, 0.0):
        return "stable_fail"
    return "stochastic"


def _unique_predictions(observations: list[QuestionObservation]) -> list[str]:
    """Return predictions ordered by frequency, then first-seen order."""
    counts = Counter(obs.predicted for obs in observations)
    first_seen: dict[str, int] = {}
    for idx, obs in enumerate(observations):
        first_seen.setdefault(obs.predicted, idx)
    return sorted(
        counts,
        key=lambda prediction: (-counts[prediction], first_seen[prediction], prediction),
    )


def build_iteration_report(runs: list[RunArtifact]) -> dict[str, Any]:
    """Build a compact structured report across repeated benchmark runs."""
    if not runs:
        raise ValueError("At least one run artifact is required")

    llm_ems = [run.llm_em_percent for run in runs]
    ems = [run.em_percent for run in runs]
    question_map: dict[str, list[QuestionObservation]] = defaultdict(list)
    latest_run = runs[-1]

    for run in runs:
        for observation in run.results:
            question_map[observation.question_id].append(observation)

    question_rows: list[dict[str, Any]] = []
    for question_id, observations in sorted(question_map.items()):
        pass_count = sum(1 for obs in observations if obs.llm_em > 0)
        run_count = len(observations)
        pass_rate = round((pass_count / run_count) * 100, 1)
        latest = observations[-1]
        question_rows.append(
            {
                "question_id": question_id,
                "gold": latest.gold,
                "classification": _classify_question(pass_rate),
                "pass_count": pass_count,
                "run_count": run_count,
                "pass_rate": pass_rate,
                "latest_prediction": latest.predicted,
                "distinct_predictions": _unique_predictions(observations),
                "latest_failure_class": latest.failure_class,
            }
        )

    latest_failures: dict[str, list[str]] = defaultdict(list)
    for observation in latest_run.results:
        if observation.llm_em > 0:
            continue
        latest_failures[observation.failure_class].append(observation.question_id)

    failure_rows = [
        {
            "failure_class": failure_class,
            "count": len(question_ids),
            "representative_ids": question_ids[:5],
        }
        for failure_class, question_ids in sorted(
            latest_failures.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]

    stability_counts = Counter(row["classification"] for row in question_rows)

    return {
        "dataset": runs[0].dataset,
        "model": runs[0].model,
        "run_count": len(runs),
        "question_count": runs[0].n_questions,
        "aggregate": {
            "llm_em_mean": round(statistics.mean(llm_ems), 2),
            "llm_em_sample_stdev": round(_sample_stdev(llm_ems), 2),
            "llm_em_min": round(min(llm_ems), 2),
            "llm_em_max": round(max(llm_ems), 2),
            "em_mean": round(statistics.mean(ems), 2),
            "cost_total": round(sum(run.total_cost for run in runs), 4),
        },
        "stability_counts": {
            "stable_pass": stability_counts.get("stable_pass", 0),
            "stochastic": stability_counts.get("stochastic", 0),
            "stable_fail": stability_counts.get("stable_fail", 0),
        },
        "runs": [
            {
                "path": run.path.as_posix(),
                "n_completed": run.n_completed,
                "llm_em_percent": round(run.llm_em_percent, 2),
                "em_percent": round(run.em_percent, 2),
                "total_cost": round(run.total_cost, 4),
            }
            for run in runs
        ],
        "question_stability": question_rows,
        "latest_failure_families": failure_rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the iteration report into a compact markdown artifact."""
    aggregate = report["aggregate"]
    lines = [
        "# Benchmark Iteration Report",
        "",
        f"- Dataset: `{report['dataset']}`",
        f"- Model: `{report['model']}`",
        f"- Runs: `{report['run_count']}`",
        f"- Question count: `{report['question_count']}`",
        f"- Mean LLM_EM: `{aggregate['llm_em_mean']:.2f}%`",
        f"- Sample stdev: `{aggregate['llm_em_sample_stdev']:.2f}` pts",
        f"- Range: `{aggregate['llm_em_min']:.2f}%` to `{aggregate['llm_em_max']:.2f}%`",
        f"- Total cost across runs: `${aggregate['cost_total']:.4f}`",
        "",
        "## Run Distribution",
        "",
        "| Run | LLM_EM | EM | Completed | Cost | Artifact |",
        "|-----|--------|----|-----------|------|----------|",
    ]

    for index, run in enumerate(report["runs"], start=1):
        artifact_name = Path(run["path"]).name
        lines.append(
            f"| {index} | {run['llm_em_percent']:.2f}% | {run['em_percent']:.2f}% | "
            f"{run['n_completed']} | ${run['total_cost']:.4f} | `{artifact_name}` |"
        )

    lines.extend(
        [
            "",
            "## Stability Summary",
            "",
            f"- Stable pass: `{report['stability_counts']['stable_pass']}` questions",
            f"- Stochastic: `{report['stability_counts']['stochastic']}` questions",
            f"- Stable fail: `{report['stability_counts']['stable_fail']}` questions",
            "",
            "## Per-Question Stability",
            "",
            "| Question ID | Pass Rate | Classification | Latest Pred | Gold | Distinct Predictions |",
            "|-------------|-----------|----------------|-------------|------|----------------------|",
        ]
    )

    for row in report["question_stability"]:
        predictions = ", ".join(f"`{value}`" for value in row["distinct_predictions"][:4])
        lines.append(
            f"| {row['question_id']} | {row['pass_rate']:.1f}% ({row['pass_count']}/{row['run_count']}) | "
            f"{row['classification']} | `{row['latest_prediction']}` | `{row['gold']}` | {predictions} |"
        )

    lines.extend(
        [
            "",
            "## Latest-Run Failure Families",
            "",
            "| Failure Class | Count | Representative IDs |",
            "|---------------|-------|--------------------|",
        ]
    )

    if report["latest_failure_families"]:
        for row in report["latest_failure_families"]:
            lines.append(
                f"| {row['failure_class']} | {row['count']} | "
                f"{', '.join(f'`{value}`' for value in row['representative_ids'])} |"
            )
    else:
        lines.append("| none | 0 | — |")

    return "\n".join(lines) + "\n"


def _select_input_paths(args: argparse.Namespace) -> list[Path]:
    """Resolve the CLI input selection into sorted artifact paths."""
    if args.glob:
        paths: list[Path] = []
        seen: set[Path] = set()
        for root in benchmark_glob_roots(
            Path(args.repo_root),
            explicit_root=Path(args.glob_root) if args.glob_root else None,
        ):
            for path in sorted(root.expanduser().glob(args.glob)):
                resolved = path.resolve()
                if resolved in seen or not path.name.endswith("Z.json"):
                    continue
                seen.add(resolved)
                paths.append(resolved)
    else:
        paths = [Path(value) for value in args.input]

    if args.latest is not None and args.latest > 0:
        paths = paths[-args.latest :]
    return paths


def _filter_runs(
    runs: list[RunArtifact],
    *,
    dataset: str | None,
    model: str | None,
    question_count: int | None,
) -> list[RunArtifact]:
    """Filter artifacts down to the requested benchmark lane."""
    filtered: list[RunArtifact] = []
    for run in runs:
        if dataset and run.dataset != dataset:
            continue
        if model and run.model != model:
            continue
        if question_count is not None and run.n_questions != question_count:
            continue
        filtered.append(run)
    return filtered


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--glob", help="Glob pattern for benchmark result JSON artifacts")
    source.add_argument("--input", nargs="+", help="Explicit benchmark artifact paths")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root used to auto-detect worktree + canonical artifact locations",
    )
    parser.add_argument(
        "--glob-root",
        help="Optional explicit root used when resolving --glob patterns",
    )
    parser.add_argument("--dataset", help="Optional dataset filter")
    parser.add_argument("--model", help="Optional model filter")
    parser.add_argument("--question-count", type=int, help="Optional question-count filter")
    parser.add_argument("--latest", type=int, help="Keep only the latest N matching artifacts")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--output", help="Optional output file path")
    args = parser.parse_args()

    input_paths = _select_input_paths(args)
    if not input_paths:
        raise SystemExit("No benchmark artifacts matched the requested input")

    runs = [load_run_artifact(path) for path in input_paths]
    runs = _filter_runs(
        runs,
        dataset=args.dataset,
        model=args.model,
        question_count=args.question_count,
    )
    if not runs:
        raise SystemExit("No benchmark artifacts remained after filtering")

    report = build_iteration_report(runs)
    rendered = (
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else render_markdown(report)
    )

    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
