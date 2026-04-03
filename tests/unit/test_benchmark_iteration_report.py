"""Unit tests for repeated benchmark iteration reporting."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_iteration_report import build_iteration_report, load_run_artifact, render_markdown


def _write_artifact(
    path: Path,
    *,
    dataset: str = "MuSiQue",
    model: str = "openrouter/openai/gpt-5.4-mini",
    results: list[dict],
) -> None:
    """Write a minimal benchmark artifact for report testing."""
    passed = sum(1 for item in results if item["llm_em"] > 0)
    n_questions = len(results)
    path.write_text(
        json.dumps(
            {
                "dataset": dataset,
                "model": model,
                "n_questions": n_questions,
                "n_completed": n_questions,
                "avg_llm_em_judged": (passed / n_questions) * 100,
                "avg_em": (sum(item["em"] for item in results) / n_questions) * 100,
                "total_cost": 0.1,
                "results": results,
            }
        )
    )


def test_build_iteration_report_computes_distribution_and_stability(tmp_path: Path) -> None:
    """Repeated artifacts should yield mean, spread, and per-question stability."""
    run1 = tmp_path / "run1.json"
    run2 = tmp_path / "run2.json"
    run3 = tmp_path / "run3.json"

    _write_artifact(
        run1,
        results=[
            {"id": "q1", "gold": "A", "predicted": "A", "llm_em": 1, "em": 1, "primary_failure_class": "none"},
            {"id": "q2", "gold": "B", "predicted": "X", "llm_em": 0, "em": 0, "primary_failure_class": "IEE"},
        ],
    )
    _write_artifact(
        run2,
        results=[
            {"id": "q1", "gold": "A", "predicted": "A", "llm_em": 1, "em": 1, "primary_failure_class": "none"},
            {"id": "q2", "gold": "B", "predicted": "B", "llm_em": 1, "em": 1, "primary_failure_class": "none"},
        ],
    )
    _write_artifact(
        run3,
        results=[
            {"id": "q1", "gold": "A", "predicted": "A", "llm_em": 1, "em": 1, "primary_failure_class": "none"},
            {"id": "q2", "gold": "B", "predicted": "Y", "llm_em": 0, "em": 0, "primary_failure_class": "IEE"},
        ],
    )

    report = build_iteration_report(
        [load_run_artifact(run1), load_run_artifact(run2), load_run_artifact(run3)]
    )

    assert report["aggregate"]["llm_em_mean"] == 66.67
    assert report["aggregate"]["llm_em_min"] == 50.0
    assert report["aggregate"]["llm_em_max"] == 100.0
    assert report["stability_counts"] == {
        "stable_pass": 1,
        "stochastic": 1,
        "stable_fail": 0,
    }
    q1 = next(row for row in report["question_stability"] if row["question_id"] == "q1")
    q2 = next(row for row in report["question_stability"] if row["question_id"] == "q2")
    assert q1["classification"] == "stable_pass"
    assert q1["pass_rate"] == 100.0
    assert q2["classification"] == "stochastic"
    assert q2["pass_rate"] == 33.3
    assert q2["distinct_predictions"] == ["X", "B", "Y"]
    assert report["latest_failure_families"] == [
        {"failure_class": "IEE", "count": 1, "representative_ids": ["q2"]}
    ]


def test_render_markdown_includes_core_sections(tmp_path: Path) -> None:
    """Markdown rendering should expose run distribution and per-question stability."""
    run_path = tmp_path / "run.json"
    _write_artifact(
        run_path,
        results=[
            {"id": "q1", "gold": "A", "predicted": "A", "llm_em": 1, "em": 1, "primary_failure_class": "none"},
        ],
    )

    report = build_iteration_report([load_run_artifact(run_path)])
    rendered = render_markdown(report)

    assert "# Benchmark Iteration Report" in rendered
    assert "## Run Distribution" in rendered
    assert "## Per-Question Stability" in rendered
    assert "`run.json`" in rendered
    assert "stable_pass" in rendered
