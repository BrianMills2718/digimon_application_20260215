"""Regression tests for ERGraph checkpoint-resume completion semantics."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from Config.GraphConfig import GraphConfig
from Core.Graph.ERGraph import ERGraph


class _DummyNamespace:
    """Minimal namespace stub exposing the saved graph directory."""

    def __init__(self, save_path: Path) -> None:
        self._save_path = save_path

    def get_save_path(self) -> str:
        """Return the artifact directory used by the checkpoint helper."""

        return str(self._save_path)


class _DummyStorage:
    """Minimal storage stub used by checkpoint-only ERGraph tests."""

    def __init__(self, save_path: Path) -> None:
        self.namespace = _DummyNamespace(save_path)


class _DummyLLM:
    """Minimal LLM stub satisfying ERGraph initialization."""

    model = "test-model"


class _DummyEncoder:
    """Minimal encoder stub satisfying BaseGraph initialization."""

    def encode(self, text: str) -> list[int]:
        """Return one token per character for test-only sizing."""

        return list(range(len(text)))

    def decode(self, tokens: list[int]) -> str:
        """Return a deterministic placeholder string."""

        return "".join("x" for _ in tokens)


def test_ergraph_clears_full_checkpoint_when_resume_has_no_remaining_chunks(tmp_path: Path) -> None:
    """A fully processed checkpoint should become a completed build, not a permanent resume state."""

    graph_dir = tmp_path / "er_graph"
    graph_dir.mkdir()
    checkpoint_path = graph_dir / "_checkpoint_processed.json"
    checkpoint_path.write_text(json.dumps([0, 1, 2]), encoding="utf-8")

    graph = ERGraph(
        config=GraphConfig(),
        llm=_DummyLLM(),
        encoder=_DummyEncoder(),
        storage_instance=_DummyStorage(graph_dir),
    )

    result = asyncio.run(graph._build_graph([("chunk_0", object()), ("chunk_1", object()), ("chunk_2", object())]))

    assert result is True
    assert checkpoint_path.exists() is False
