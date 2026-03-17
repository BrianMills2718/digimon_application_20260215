"""Benchmark scoring — EM, F1, LLM-as-judge for QA evaluation.

Used by eval/run_agent_benchmark.py for scoring agent-composed answers.
"""

from __future__ import annotations

import json
import re
import string
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Optional

from Core.Common.Logger import logger

JUDGE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "llm_judge.yaml"


def _parse_llm_judge_correct(raw_text: str) -> bool:
    """Parse judge output robustly and return the boolean correctness verdict."""
    if not raw_text or not raw_text.strip():
        return False

    text = raw_text.strip()
    candidates: list[str] = [text]

    # Prefer parsing a de-fenced payload when the model wraps JSON in markdown.
    try:
        from llm_client import strip_fences

        stripped = strip_fences(text)
        if stripped and stripped not in candidates:
            candidates.append(stripped)
    except Exception:
        pass

    # Also try extracting the largest JSON-looking object span from each candidate.
    for candidate in list(candidates):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            span = candidate[start : end + 1]
            if span not in candidates:
                candidates.append(span)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "correct" in parsed:
            value = parsed.get("correct")
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                norm = value.strip().lower()
                if norm in {"true", "1", "yes"}:
                    return True
                if norm in {"false", "0", "no"}:
                    return False

    # Conservative text fallback: explicit negative wins.
    lowered = text.lower()
    if re.search(r'"correct"\s*:\s*false', lowered):
        return False
    if re.search(r"\bincorrect\b", lowered) or re.search(r"\bnot\s+correct\b", lowered):
        return False
    if re.search(r'"correct"\s*:\s*true', lowered):
        return True
    if re.search(r"\bcorrect\b", lowered):
        return True
    return False


# --- Scoring (reuses normalize_answer logic from Core/Utils/Evaluation.py) ---

def normalize_answer(s: str) -> str:
    """Lowercase, strip articles, remove punctuation, collapse whitespace."""
    def remove_articles(text: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def remove_punc(text: str) -> str:
        return "".join(ch for ch in text if ch not in string.punctuation)

    return " ".join(remove_articles(remove_punc(s.lower())).split())


def exact_match(predicted: str, gold: str) -> bool:
    return normalize_answer(predicted) == normalize_answer(gold)


def token_f1(predicted: str, gold: str) -> tuple[float, float, float]:
    """Returns (f1, precision, recall)."""
    pred_tokens = normalize_answer(predicted).split()
    gold_tokens = normalize_answer(gold).split()

    if not pred_tokens or not gold_tokens:
        return (0.0, 0.0, 0.0)

    common = Counter(pred_tokens) & Counter(gold_tokens)
    num_same = sum(common.values())

    if num_same == 0:
        return (0.0, 0.0, 0.0)

    precision = num_same / len(pred_tokens)
    recall = num_same / len(gold_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    return (f1, precision, recall)


def score_prediction(predicted: str, gold: str) -> Dict[str, Any]:
    """Compute EM and F1 for a single prediction."""
    em = exact_match(predicted, gold)
    f1, precision, recall = token_f1(predicted, gold)
    return {
        "em": int(em),
        "f1": f1,
        "precision": precision,
        "recall": recall,
    }


async def llm_judge(
    question: str,
    predicted: str,
    gold: str,
    model: str = "deepseek/deepseek-chat",
) -> bool | None:
    """Use an LLM to judge if the predicted answer is correct.

    Returns True if the LLM deems the prediction correct, False if judged incorrect,
    and None when the judge call fails (timeout, API, parse/runtime failure).
    """
    if not predicted or not predicted.strip():
        return False

    from llm_client import acall_llm, render_prompt

    messages = render_prompt(
        JUDGE_PROMPT_PATH,
        question=question,
        gold=gold,
        predicted=predicted,
    )

    q_hash = md5(question.encode()).hexdigest()[:8]
    trace_id = f"digimon.llm_judge.{q_hash}"
    try:
        result = await acall_llm(model, messages, timeout=0, task="digimon.llm_judge", trace_id=trace_id, max_budget=0)
        return _parse_llm_judge_correct(result.content)
    except Exception as e:
        logger.warning(f"llm_judge failed: {e}")
        return None


# --- Data structures ---

@dataclass
class QuestionResult:
    id: str
    question: str
    gold: str
    predicted: str
    em: int
    f1: float
    precision: float
    recall: float
    latency_s: float
    n_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error: Optional[str] = None


@dataclass
class MethodResult:
    method_name: str
    avg_em: float = 0.0
    avg_f1: float = 0.0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_latency_s: float = 0.0
    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_llm_calls_per_q: float = 0.0
    per_question: List[QuestionResult] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    dataset: str
    n_questions: int
    methods: Dict[str, MethodResult] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "dataset": self.dataset,
            "n_questions": self.n_questions,
            "methods": {
                name: {
                    "avg_em": mr.avg_em,
                    "avg_f1": mr.avg_f1,
                    "avg_precision": mr.avg_precision,
                    "avg_recall": mr.avg_recall,
                    "avg_latency_s": mr.avg_latency_s,
                    "total_llm_calls": mr.total_llm_calls,
                    "total_input_tokens": mr.total_input_tokens,
                    "total_output_tokens": mr.total_output_tokens,
                    "avg_llm_calls_per_q": mr.avg_llm_calls_per_q,
                    "per_question": [
                        {
                            "id": qr.id,
                            "question": qr.question,
                            "gold": qr.gold,
                            "predicted": qr.predicted,
                            "em": qr.em,
                            "f1": qr.f1,
                            "latency_s": qr.latency_s,
                            "n_llm_calls": qr.n_llm_calls,
                            "total_input_tokens": qr.total_input_tokens,
                            "total_output_tokens": qr.total_output_tokens,
                            "error": qr.error,
                        }
                        for qr in mr.per_question
                    ],
                }
                for name, mr in self.methods.items()
            },
        }


# --- Runner ---

