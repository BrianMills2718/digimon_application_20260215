"""Dataset loading and preparation for benchmarks.

Loads question files and ensures the corresponding corpus/graph are ready.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Core.Common.Logger import logger


def load_questions(
    dataset_path: str,
    n_questions: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load questions from a DIGIMON dataset's Question.json (JSONL format).

    Args:
        dataset_path: Path to dataset directory containing Question.json
        n_questions: Limit to first N questions

    Returns:
        List of dicts with 'id', 'question', 'answer' (and optional 'type', 'level')
    """
    question_file = Path(dataset_path) / "Question.json"
    if not question_file.exists():
        raise FileNotFoundError(f"No Question.json at {question_file}")

    questions = []
    with open(question_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            questions.append(q)

    if n_questions is not None:
        questions = questions[:n_questions]

    logger.info(f"Loaded {len(questions)} questions from {question_file}")
    return questions


def get_dataset_path(dataset_name: str, data_root: str = "./Data") -> str:
    """Resolve dataset name to its directory path.

    Args:
        dataset_name: Name like 'HotpotQA', 'HotpotQAsmallest', etc.
        data_root: Root data directory (default: ./Data)

    Returns:
        Absolute path to dataset directory
    """
    path = Path(data_root) / dataset_name
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset '{dataset_name}' not found at {path}. "
            f"Available: {[p.name for p in Path(data_root).iterdir() if p.is_dir()]}"
        )
    return str(path.resolve())


def check_corpus_ready(dataset_name: str, working_dir: str = "./results") -> bool:
    """Check if corpus has been prepared for a dataset."""
    corpus_path = Path(working_dir) / dataset_name / "corpus" / "Corpus.json"
    return corpus_path.exists()


def check_graph_ready(dataset_name: str, working_dir: str = "./results") -> bool:
    """Check if an ER graph has been built for a dataset."""
    graph_dir = Path(working_dir) / dataset_name / "er_graph"
    return graph_dir.exists() and any(graph_dir.iterdir())
