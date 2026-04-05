#!/usr/bin/env python3
"""Render normalized benchmark traces for one DIGIMON question.

This script exists because raw benchmark JSON is complete but not easy to review.
It aligns the most useful observability surfaces into one readable artifact:

- semantic-plan helper decisions
- tool calls with arguments and result previews
- atom lifecycle transitions
- terminal submit/failure state

It also supports a light-weight diff mode for comparing the same question across
two result artifacts.

Usage:
    python scripts/diagnose_question.py RESULT_FILE QUESTION_ID
    python scripts/diagnose_question.py RESULT_FILE QUESTION_ID --diff-other OTHER_FILE

    # Or via make:
    make diagnose FILE=results/latest.json QID=2hop__13548_13529
    make trace FILE=results/latest.json QID=2hop__13548_13529
    make trace-diff FILE=results/a.json FILE_B=results/b.json QID=2hop__13548_13529
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any


def _load_result_file(result_file: str) -> dict[str, Any]:
    with open(result_file, encoding="utf-8") as handle:
        return json.load(handle)


def _find_question(data: dict[str, Any], question_id: str) -> dict[str, Any]:
    for question in data.get("results", []):
        if question.get("id") == question_id:
            return question
    available = [q.get("id") for q in data.get("results", [])]
    raise KeyError(f"Question '{question_id}' not found. Available IDs: {available}")


def load_question(result_file: str, question_id: str) -> dict[str, Any]:
    """Load one benchmark question artifact from a consolidated result file."""
    return _find_question(_load_result_file(result_file), question_id)


def _truncate(value: Any, limit: int = 320) -> str:
    text = str(value).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _status(has_result: bool, has_error: bool) -> str:
    if has_error:
        return "ERROR"
    if has_result:
        return "OK"
    return "UNKNOWN"


def _interesting_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    skip = {
        "dataset_name",
        "graph_reference_id",
        "vdb_reference_id",
        "document_collection_id",
        "tool_reasoning",
    }
    return {
        key: value
        for key, value in arguments.items()
        if key not in skip and value not in ("", None, [], {})
    }


def _extract_plan_events(question: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for event in question.get("helper_decision_trace", [])
        if str(event.get("task", "")).startswith("digimon.semantic_plan")
    ]


def _extract_latest_plan(question: dict[str, Any]) -> dict[str, Any] | None:
    plan_events = _extract_plan_events(question)
    for event in reversed(plan_events):
        payload = event.get("decision_payload")
        if isinstance(payload, dict) and payload.get("atoms"):
            return payload
    return None


def _format_atom(atom: dict[str, Any], prefix: str = "-") -> list[str]:
    lines = [
        (
            f"{prefix} {atom.get('atom_id', '?')}: {atom.get('sub_question', '?')} "
            f"[op={atom.get('operation', '?')}, answer_kind={atom.get('answer_kind', '?')}]"
        )
    ]
    output_var = atom.get("output_var")
    depends_on = atom.get("depends_on") or []
    done_criteria = atom.get("done_criteria")
    if output_var:
        lines.append(f"    output_var: {output_var}")
    lines.append(f"    depends_on: {depends_on if depends_on else '[]'}")
    if done_criteria:
        lines.append(f"    done_criteria: {_truncate(done_criteria, 240)}")
    return lines


def _format_plan(plan: dict[str, Any] | None) -> list[str]:
    if not plan:
        return ["No semantic plan payload found."]
    lines = [
        f"final_answer_kind: {plan.get('final_answer_kind', '?')}",
        f"composition_rule: {_truncate(plan.get('composition_rule', ''), 300)}",
    ]
    uncertainty_points = plan.get("uncertainty_points") or []
    if uncertainty_points:
        lines.append("uncertainty_points:")
        lines.extend([f"- {_truncate(point, 240)}" for point in uncertainty_points])
    else:
        lines.append("uncertainty_points: []")
    lines.append("atoms:")
    for atom in plan.get("atoms", []):
        lines.extend(_format_atom(atom))
    return lines


def _format_helper_event(event: dict[str, Any], index: int) -> list[str]:
    lines = []
    event_type = event.get("event_type") or event.get("event") or "helper_event"
    task = event.get("task", "?")
    requested_model = event.get("requested_model", "?")
    resolved_model = event.get("resolved_model") or event.get("execution_model") or "?"
    fallback_used = event.get("fallback_used", False)
    lines.append(
        f"{index}. {task} [{event_type}] "
        f"requested={requested_model} actual={resolved_model} fallback={fallback_used}"
    )
    input_state = event.get("input_state")
    if input_state:
        lines.append(f"   input_state: {_truncate(json.dumps(input_state, ensure_ascii=True), 600)}")
    payload = event.get("decision_payload")
    if isinstance(payload, dict):
        atoms = payload.get("atoms")
        if atoms:
            lines.append(f"   decision: {len(atoms)} atoms, final_answer_kind={payload.get('final_answer_kind', '?')}")
            for atom in atoms:
                lines.extend([f"   {line}" for line in _format_atom(atom)])
        else:
            lines.append(f"   decision: {_truncate(json.dumps(payload, ensure_ascii=True), 700)}")
    warnings = event.get("warnings") or []
    if warnings:
        lines.append(f"   warnings: {[_truncate(w, 180) for w in warnings]}")
    return lines


def _format_tool_call(tool_detail: dict[str, Any], index: int) -> list[str]:
    lines = []
    tool = tool_detail.get("tool", "?")
    status = _status(tool_detail.get("has_result", False), tool_detail.get("has_error", False))
    latency = tool_detail.get("latency_s", "?")
    lines.append(f"{index}. {tool} [{status}] latency={latency}s")
    reasoning = tool_detail.get("tool_reasoning")
    if reasoning:
        lines.append(f"   reasoning: {_truncate(reasoning, 400)}")
    arguments = _interesting_arguments(tool_detail.get("arguments", {}))
    if arguments:
        lines.append(f"   args: {_truncate(json.dumps(arguments, ensure_ascii=True), 900)}")
    if tool_detail.get("has_error"):
        lines.append(f"   error: {_truncate(tool_detail.get('error'), 700)}")
    elif tool_detail.get("result_preview"):
        lines.append(f"   result: {_truncate(tool_detail.get('result_preview'), 1200)}")
    return lines


def _format_atom_event(event: dict[str, Any], index: int) -> list[str]:
    event_name = event.get("event", "?")
    atom_id = event.get("atom_id", "?")
    sub_question = event.get("sub_question", "")
    lines = [f"{index}. {event_name} {atom_id}: {_truncate(sub_question, 180)}"]
    if "resolved_value" in event:
        lines.append(f"   resolved_value: {_truncate(event.get('resolved_value'), 200)}")
    if "proposed_value" in event:
        lines.append(f"   proposed_value: {_truncate(event.get('proposed_value'), 200)}")
    if event.get("confidence") is not None:
        lines.append(f"   confidence: {event.get('confidence')}")
    if event.get("tool_name"):
        tool_name = event.get("tool_name")
        method = event.get("method")
        lines.append(f"   source: {tool_name}{f'({method})' if method else ''}")
    rationale = event.get("rationale")
    if rationale:
        lines.append(f"   rationale: {_truncate(rationale, 900)}")
    evidence_refs = event.get("evidence_refs") or []
    if evidence_refs:
        lines.append(f"   evidence_refs: {evidence_refs}")
    reason = event.get("reason")
    if reason:
        lines.append(f"   reason: {_truncate(reason, 200)}")
    return lines


def _final_summary(question: dict[str, Any]) -> list[str]:
    keys = [
        ("predicted", question.get("predicted")),
        ("gold", question.get("gold")),
        ("llm_em", question.get("llm_em")),
        ("submit_completion_mode", question.get("submit_completion_mode")),
        ("submit_answer_succeeded", question.get("submit_answer_succeeded")),
        ("submit_validator_accepted", question.get("submit_validator_accepted")),
        ("submit_pending_atom_ids", question.get("submit_pending_atom_ids")),
        ("forced_terminal_accept_reason", question.get("forced_terminal_accept_reason")),
        ("primary_failure_class", question.get("primary_failure_class")),
        ("secondary_failure_classes", question.get("secondary_failure_classes")),
        ("failure_event_codes", question.get("failure_event_codes")),
        ("helper_models_used", question.get("helper_models_used")),
        ("helper_fallback_used", question.get("helper_fallback_used")),
        ("tool_calls", question.get("n_tool_calls")),
        ("duration_ms", question.get("duration_ms")),
    ]
    lines = []
    for key, value in keys:
        lines.append(f"{key}: {value}")
    return lines


def render_question_trace(question: dict[str, Any], *, result_file: str | None = None) -> str:
    """Render one question as a normalized text trace."""
    lines = []
    lines.append("=" * 88)
    lines.append(f"TRACE: {question.get('id', '?')}")
    if result_file:
        lines.append(f"artifact: {result_file}")
    lines.append("=" * 88)
    lines.append(f"question: {question.get('question', '?')}")
    lines.append("")
    lines.append("[FINAL OUTCOME]")
    lines.extend(_final_summary(question))
    lines.append("")
    lines.append("[SEMANTIC PLAN]")
    lines.extend(_format_plan(_extract_latest_plan(question)))
    lines.append("")
    lines.append("[HELPER DECISION TRACE]")
    helper_trace = question.get("helper_decision_trace") or []
    if helper_trace:
        for index, event in enumerate(helper_trace, start=1):
            lines.extend(_format_helper_event(event, index))
    else:
        lines.append("No helper decision trace.")
    lines.append("")
    lines.append("[TOOL TRACE]")
    tool_details = question.get("tool_details") or []
    if tool_details:
        for index, tool_detail in enumerate(tool_details, start=1):
            lines.extend(_format_tool_call(tool_detail, index))
    else:
        lines.append("No tool trace.")
    lines.append("")
    lines.append("[ATOM LIFECYCLE TRACE]")
    atom_trace = question.get("atom_lifecycle_trace") or []
    if atom_trace:
        for index, event in enumerate(atom_trace, start=1):
            lines.extend(_format_atom_event(event, index))
    else:
        lines.append("No atom lifecycle trace.")
    lines.append("")
    lines.append("[TERMINAL ANALYSIS]")
    lines.append(
        f"finalization_events: {question.get('finalization_events') or []}"
    )
    lines.append(
        f"required_submit_missing: {question.get('required_submit_missing')}"
    )
    lines.append(
        f"submit_forced_accept_on_budget_exhaustion: {question.get('submit_forced_accept_on_budget_exhaustion')}"
    )
    lines.append(
        f"forced_final_attempts: {question.get('forced_final_attempts')}"
    )
    lines.append(
        f"retrieval_stagnation_triggered: {question.get('retrieval_stagnation_triggered')}"
    )
    lines.append(
        f"retrieval_stagnation_turn: {question.get('retrieval_stagnation_turn')}"
    )
    lines.append(
        f"lane_closure_analysis: {_truncate(json.dumps(question.get('lane_closure_analysis'), ensure_ascii=True), 800)}"
    )
    return "\n".join(lines)


def _plan_atom_subquestions(question: dict[str, Any]) -> list[str]:
    plan = _extract_latest_plan(question)
    if not plan:
        return []
    return [atom.get("sub_question", "?") for atom in plan.get("atoms", [])]


def _completed_atoms(question: dict[str, Any]) -> dict[str, Any]:
    completed: dict[str, Any] = {}
    for event in question.get("atom_lifecycle_trace", []):
        if event.get("event") == "atom_completed":
            completed[event.get("atom_id", "?")] = event.get("resolved_value")
    return completed


def render_trace_diff(
    question_a: dict[str, Any],
    question_b: dict[str, Any],
    *,
    label_a: str,
    label_b: str,
) -> str:
    """Render a question-level diff between two artifacts."""
    lines = []
    lines.append("=" * 88)
    lines.append(f"TRACE DIFF: {question_a.get('id', '?')}")
    lines.append(f"A: {label_a}")
    lines.append(f"B: {label_b}")
    lines.append("=" * 88)
    lines.append(f"question: {question_a.get('question', '?')}")
    lines.append("")
    lines.append("[OUTCOME DELTA]")
    for key in [
        "predicted",
        "llm_em",
        "submit_completion_mode",
        "submit_pending_atom_ids",
        "forced_terminal_accept_reason",
        "primary_failure_class",
        "n_tool_calls",
    ]:
        lines.append(f"{key}:")
        lines.append(f"  A: {question_a.get(key)}")
        lines.append(f"  B: {question_b.get(key)}")
    lines.append("")
    lines.append("[SEMANTIC PLAN DELTA]")
    lines.append(f"A atoms ({len(_plan_atom_subquestions(question_a))}):")
    for sub_question in _plan_atom_subquestions(question_a):
        lines.append(f"- {sub_question}")
    lines.append(f"B atoms ({len(_plan_atom_subquestions(question_b))}):")
    for sub_question in _plan_atom_subquestions(question_b):
        lines.append(f"- {sub_question}")
    lines.append("")
    lines.append("[ATOM COMPLETION DELTA]")
    completed_a = _completed_atoms(question_a)
    completed_b = _completed_atoms(question_b)
    all_atom_ids = sorted(set(completed_a) | set(completed_b))
    for atom_id in all_atom_ids:
        lines.append(
            f"{atom_id}: A={completed_a.get(atom_id)} | B={completed_b.get(atom_id)}"
        )
    lines.append("")
    lines.append("[TRACE COUNTS]")
    for key in [
        "helper_decision_event_count",
        "atom_lifecycle_event_count",
        "submit_answer_call_count",
        "forced_final_attempts",
    ]:
        lines.append(f"{key}: A={question_a.get(key)} | B={question_b.get(key)}")
    return "\n".join(lines)


def diagnose(result_file: str, question_id: str) -> None:
    """Print the normalized trace for one benchmark question."""
    question = load_question(result_file, question_id)
    print(render_question_trace(question, result_file=result_file))


def _latest_result_files() -> list[str]:
    return sorted(glob.glob("results/MuSiQue_gpt-5-4-mini_consolidated_*.json"))


def _print_usage_with_latest() -> None:
    files = _latest_result_files()
    if files:
        latest = files[-1]
        data = _load_result_file(latest)
        print(f"Latest: {latest}")
        print("Questions:")
        for question in data.get("results", []):
            status = "PASS" if question.get("llm_em", 0) == 1 else "FAIL"
            print(f"  {status} {question.get('id')}")
    else:
        print("No result files found")
    print("\nUsage: python scripts/diagnose_question.py RESULT_FILE QUESTION_ID [--diff-other OTHER_FILE]")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_file", nargs="?")
    parser.add_argument("question_id", nargs="?")
    parser.add_argument(
        "--diff-other",
        dest="diff_other",
        help="Optional second artifact to diff against the primary result file.",
    )
    parser.add_argument(
        "--output",
        help="Optional output file. If omitted, print to stdout.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.result_file or not args.question_id:
        _print_usage_with_latest()
        raise SystemExit(0)

    try:
        primary = load_question(args.result_file, args.question_id)
    except KeyError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    if args.diff_other:
        try:
            secondary = load_question(args.diff_other, args.question_id)
        except KeyError as exc:
            print(str(exc))
            raise SystemExit(1) from exc
        rendered = render_trace_diff(
            primary,
            secondary,
            label_a=args.result_file,
            label_b=args.diff_other,
        )
    else:
        rendered = render_question_trace(primary, result_file=args.result_file)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        print(args.output)
        return

    print(rendered)


if __name__ == "__main__":
    main()
