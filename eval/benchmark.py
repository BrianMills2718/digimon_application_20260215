"""BenchmarkRunner — run operator compositions against QA benchmarks.

Scores EM and F1 using Core/Utils/Evaluation.py normalization logic.
Calls OperatorComposer directly (no MCP overhead) for batch runs.
"""

from __future__ import annotations

import json
import re
import string
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from Core.Common.Logger import logger


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

class BenchmarkRunner:
    """Run operator compositions against QA benchmarks."""

    def __init__(
        self,
        dataset_name: str,
        methods: List[str],
        questions: List[Dict[str, Any]],
        composer: Any,
        op_ctx_builder: Any,
        n_questions: Optional[int] = None,
        llm_stats: Any = None,
    ):
        """
        Args:
            dataset_name: DIGIMON dataset name (e.g. 'HotpotQA')
            methods: Method names to benchmark (e.g. ['basic_local', 'fastgraphrag'])
            questions: List of dicts with 'id', 'question', 'answer' keys
            composer: OperatorComposer instance
            op_ctx_builder: Async callable(dataset_name) -> OperatorContext
            n_questions: Limit to first N questions (None = all)
            llm_stats: Optional LLMStats object from CountingLLMWrapper for tracking calls/tokens
        """
        self.dataset_name = dataset_name
        self.methods = methods
        self.questions = questions[:n_questions] if n_questions else questions
        self.composer = composer
        self.op_ctx_builder = op_ctx_builder
        self.llm_stats = llm_stats

    async def run(self) -> BenchmarkResult:
        """Run all methods against all questions, return scored results."""
        result = BenchmarkResult(
            dataset=self.dataset_name,
            n_questions=len(self.questions),
        )

        for method_name in self.methods:
            logger.info(f"Benchmarking method '{method_name}' on {len(self.questions)} questions")
            method_result = await self._run_method(method_name)
            result.methods[method_name] = method_result
            logger.info(
                f"  {method_name}: EM={method_result.avg_em:.1f}% "
                f"F1={method_result.avg_f1:.1f}% "
                f"latency={method_result.avg_latency_s:.1f}s"
            )

        return result

    async def _run_method(self, method_name: str) -> MethodResult:
        """Run a single method against all questions."""
        mr = MethodResult(method_name=method_name)

        op_ctx = await self.op_ctx_builder(self.dataset_name)

        for i, q in enumerate(self.questions):
            qr = await self._run_single(method_name, q, op_ctx, i)
            mr.per_question.append(qr)

        # Compute averages
        n = len(mr.per_question)
        if n > 0:
            mr.avg_em = 100.0 * sum(qr.em for qr in mr.per_question) / n
            mr.avg_f1 = 100.0 * sum(qr.f1 for qr in mr.per_question) / n
            mr.avg_precision = 100.0 * sum(qr.precision for qr in mr.per_question) / n
            mr.avg_recall = 100.0 * sum(qr.recall for qr in mr.per_question) / n
            mr.avg_latency_s = sum(qr.latency_s for qr in mr.per_question) / n
            mr.total_llm_calls = sum(qr.n_llm_calls for qr in mr.per_question)
            mr.total_input_tokens = sum(qr.total_input_tokens for qr in mr.per_question)
            mr.total_output_tokens = sum(qr.total_output_tokens for qr in mr.per_question)
            mr.avg_llm_calls_per_q = mr.total_llm_calls / n

        return mr

    async def _run_single(
        self, method_name: str, question: Dict[str, Any], op_ctx: Any, idx: int
    ) -> QuestionResult:
        """Run one question through one method, score the result."""
        q_id = question.get("id", f"q{idx}")
        q_text = question["question"]
        gold = question["answer"]

        # Snapshot LLM stats before this question
        calls_before = 0
        input_tok_before = 0
        output_tok_before = 0
        if self.llm_stats:
            snap = self.llm_stats.to_dict()
            calls_before = snap["n_llm_calls"]
            input_tok_before = snap["total_input_tokens"]
            output_tok_before = snap["total_output_tokens"]

        t0 = time.monotonic()
        try:
            plan = self.composer.build_plan(
                method_name=method_name,
                query=q_text,
                dataset=self.dataset_name,
            )
            result = await self.composer.execute(plan, op_ctx)

            # Extract answer from final_output
            predicted = self._extract_answer(result)
            error = None
        except Exception as e:
            predicted = ""
            error = str(e)
            logger.warning(f"  [{q_id}] {method_name} failed: {e}")

        latency = time.monotonic() - t0
        scores = score_prediction(predicted, gold)

        # Compute LLM stats delta for this question
        n_llm_calls = 0
        q_input_tokens = 0
        q_output_tokens = 0
        if self.llm_stats:
            snap = self.llm_stats.to_dict()
            n_llm_calls = snap["n_llm_calls"] - calls_before
            q_input_tokens = snap["total_input_tokens"] - input_tok_before
            q_output_tokens = snap["total_output_tokens"] - output_tok_before

        return QuestionResult(
            id=q_id,
            question=q_text,
            gold=gold,
            predicted=predicted,
            em=scores["em"],
            f1=scores["f1"],
            precision=scores["precision"],
            recall=scores["recall"],
            latency_s=round(latency, 2),
            n_llm_calls=n_llm_calls,
            total_input_tokens=q_input_tokens,
            total_output_tokens=q_output_tokens,
            error=error,
        )

    def _extract_answer(self, result: Dict[str, Any]) -> str:
        """Extract the answer string from composer.execute() output."""
        final = result.get("final_output", {})

        # meta.generate_answer puts answer in "answer" key
        if "answer" in final:
            ans = final["answer"]
            if isinstance(ans, str):
                return ans
            return str(ans)

        # Fallback: try chunks (if return_context_only was used)
        if "chunks" in final:
            chunks = final["chunks"]
            if isinstance(chunks, list):
                texts = []
                for c in chunks:
                    if hasattr(c, "text"):
                        texts.append(c.text)
                    elif isinstance(c, str):
                        texts.append(c)
                return " ".join(texts)

        # Last resort: stringify whatever we got
        return str(final) if final else ""
