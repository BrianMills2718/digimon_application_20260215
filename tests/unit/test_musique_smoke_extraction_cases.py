"""Regression tests for the exact bad MuSiQue smoke extraction cases."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_module(module_name: str, relative_path: str):
    """Load one project module directly from its file path for isolated tests."""

    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DelimiterExtractionMixin = _load_module(
    "graph_delimiter_extraction_musique_smoke_test",
    "Core/Graph/DelimiterExtraction.py",
).DelimiterExtractionMixin


class _ExtractionHarness(DelimiterExtractionMixin):
    """Minimal host object for delimiter extraction helper tests."""

    def __init__(self) -> None:
        self.config = SimpleNamespace(
            enable_edge_name=True,
            enable_edge_keywords=False,
            enable_entity_type=True,
            schema_entity_types=[],
            schema_relation_types=[],
            schema_mode="open",
            loaded_custom_ontology=None,
            max_gleaning=1,
        )
        self.graph_config = self.config


def test_known_bad_musique_relationship_case_is_rejected() -> None:
    """The `won by` MuSiQue smoke regression should not become a graph edge."""

    extractor = _ExtractionHarness()

    result = asyncio.run(
        extractor._handle_single_relationship_extraction(
            [
                '"relationship"',
                "Barcelona",
                "won by",
                "extra time",
                "Barcelona won the match after extra time.",
                "0.8",
            ],
            chunk_key="chunk_9",
        )
    )

    assert result is None


def test_known_bad_musique_null_type_case_is_rejected() -> None:
    """The `sextuple` null-type MuSiQue smoke regression should be dropped in TKG mode."""

    extractor = _ExtractionHarness()

    result = asyncio.run(
        extractor._handle_single_entity_extraction(
            [
                '"entity"',
                "sextuple",
                "null",
                "Winning six major trophies in a single season.",
            ],
            chunk_key="chunk_9",
        )
    )

    assert result is None


def test_tagged_null_type_case_is_rejected_after_markup_stripping() -> None:
    """Field-tag wrappers should not let null types bypass typed-profile validation."""

    extractor = _ExtractionHarness()

    result = asyncio.run(
        extractor._handle_single_entity_extraction(
            [
                '"entity"',
                "<entity_name>trophies",
                "<entity_type>None",
                "<entity_description>Awards that Barcelona failed to win.</entity_description>",
            ],
            chunk_key="chunk_1",
        )
    )

    assert result is None
