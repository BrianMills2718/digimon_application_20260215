"""Regression tests for graph entity-name validation paths.

These tests cover the fail-loud storage and merge boundaries plus the
skip-with-logging extraction boundary. They intentionally avoid the larger
graph-building stack so the entity-hygiene contract stays independently
verifiable.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from Core.Schema.EntityRelation import Entity


def _load_module(module_name: str, relative_path: str):
    """Load one project module directly from its file path for isolated tests."""

    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BaseGraph = _load_module("graph_base_graph_test", "Core/Graph/BaseGraph.py").BaseGraph
DelimiterExtractionMixin = _load_module(
    "graph_delimiter_extraction_test",
    "Core/Graph/DelimiterExtraction.py",
).DelimiterExtractionMixin
NetworkXStorage = _load_module(
    "graph_networkx_storage_test",
    "Core/Storage/NetworkXStorage.py",
).NetworkXStorage


class _RecordingGraphStorage:
    """Minimal storage double for testing BaseGraph merge behavior."""

    def __init__(self) -> None:
        self.upserts: list[tuple[str, dict[str, object]]] = []

    async def get_node(self, node_id: str):
        """Return no existing node so merge starts from scratch."""

        return None

    async def upsert_node(self, node_id: str, node_data: dict[str, object]) -> None:
        """Record node upserts for assertion."""

        self.upserts.append((node_id, node_data))


class _ConcreteBaseGraph(BaseGraph):
    """Minimal concrete subclass that exposes BaseGraph helper methods."""

    def _extract_entity_relationship(self, chunk_key_pair):
        """Unused abstract hook required for instantiation."""

        raise NotImplementedError

    def _build_graph(self, chunks):
        """Unused abstract hook required for instantiation."""

        raise NotImplementedError


class _ExtractionHarness(DelimiterExtractionMixin):
    """Minimal host object for delimiter extraction helper tests."""

    def __init__(self) -> None:
        self.config = SimpleNamespace()
        self.graph_config = self.config


def test_networkx_storage_upsert_node_rejects_invalid_ids() -> None:
    """Storage should fail loudly on blank and junk single-letter IDs."""

    storage = NetworkXStorage()

    with pytest.raises(ValueError, match="Invalid node_id"):
        asyncio.run(storage.upsert_node("", {"entity_name": ""}))

    with pytest.raises(ValueError, match="single_alpha_character"):
        asyncio.run(storage.upsert_node("s", {"entity_name": "s"}))


def test_merge_nodes_then_upsert_rejects_invalid_entity_name() -> None:
    """BaseGraph should reject invalid merged entity names before storage."""

    graph = _ConcreteBaseGraph(
        config=SimpleNamespace(enable_entity_description=False, enable_entity_type=False),
        llm=None,
        encoder=None,
    )
    graph._graph = _RecordingGraphStorage()

    with pytest.raises(ValueError, match="Invalid entity name"):
        asyncio.run(
            graph._merge_nodes_then_upsert(
                "j",
                [Entity(entity_name="j", source_id="chunk-1", entity_type="", description="")],
            )
        )

    assert graph._graph.upserts == []


def test_delimiter_extraction_skips_invalid_single_letter_entities() -> None:
    """Delimiter extraction should drop low-signal one-letter entities."""

    extractor = _ExtractionHarness()

    result = asyncio.run(
        extractor._handle_single_entity_extraction(
            ['"entity"', "s", "organization", "noise candidate"],
            chunk_key="chunk-1",
        )
    )

    assert result is None
