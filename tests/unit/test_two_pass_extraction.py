"""Regression tests for the config-backed two-pass delimiter extraction flow.

These tests prove the new contract on the smallest deterministic slice:
validated entities from pass one must constrain pass two, invalid first-pass
entities must not leak into the relationship prompt, and empty inventories must
fail closed instead of emitting unconstrained relationships.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from Config.GraphConfig import GraphConfig
from Core.Common.Constants import DEFAULT_COMPLETION_DELIMITER, DEFAULT_RECORD_DELIMITER
from Core.Schema.ChunkSchema import TextChunk
from Core.Schema.GraphBuildTypes import GraphProfile


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
    "graph_delimiter_extraction_two_pass_test",
    "Core/Graph/DelimiterExtraction.py",
).DelimiterExtractionMixin


class _FakeLLM:
    """Minimal async LLM stub that returns a fixed sequence of responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def aask(self, prompt: str) -> str:
        """Record the prompt and return the next configured response."""

        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("Fake LLM received more calls than configured responses.")
        return self._responses.pop(0)


class _TwoPassHarness(DelimiterExtractionMixin):
    """Minimal host object exposing the config and llm contracts the mixin expects."""

    def __init__(self, responses: list[str]) -> None:
        self.config = GraphConfig(
            graph_profile=GraphProfile.TKG,
            enable_edge_name=True,
            enable_edge_keywords=False,
            enable_entity_type=True,
            two_pass_extraction=True,
            strict_extraction_slot_discipline=True,
            loaded_custom_ontology=None,
            max_gleaning=0,
        )
        self.graph_config = self.config
        self.llm = _FakeLLM(responses)


def _chunk() -> TextChunk:
    """Return a small chunk fixture for two-pass extraction tests."""

    return TextChunk(
        tokens=32,
        chunk_id="chunk_medical_leave",
        content=(
            "Diego Maradona took medical leave after he was diagnosed with throat cancer. "
            "Maradona later returned to public life."
        ),
        doc_id="doc_1",
        index=0,
        title="medical leave",
    )


def test_two_pass_extraction_uses_validated_inventory_and_builds_graph() -> None:
    """Validated entity inventory should constrain pass two and still produce a usable graph."""

    first_pass = (
        '("entity"<|>"Diego Maradona"<|>"person"<|>"Argentine football legend")'
        f"{DEFAULT_RECORD_DELIMITER}"
        '("entity"<|>"throat cancer"<|>"diagnosis"<|>"diagnosis that caused the leave")'
        f"{DEFAULT_RECORD_DELIMITER}"
        '("entity"<|>"his"<|>"person"<|>"anaphoric placeholder")'
        f"{DEFAULT_COMPLETION_DELIMITER}"
    )
    second_pass = (
        '("relationship"<|>"diego maradona"<|>"throat cancer"<|>"diagnosed_with"<|>'
        '"Diego Maradona was diagnosed with throat cancer."<|>9)'
        f"{DEFAULT_COMPLETION_DELIMITER}"
    )
    extractor = _TwoPassHarness([first_pass, second_pass])

    records = asyncio.run(extractor._extract_records_from_chunk(_chunk()))
    nodes, edges = asyncio.run(
        extractor._build_graph_from_records(records, chunk_key="chunk_medical_leave")
    )

    assert len(extractor.llm.prompts) == 2
    assert 'diego maradona' in extractor.llm.prompts[1]
    assert 'throat cancer' in extractor.llm.prompts[1]
    assert '"his"' not in extractor.llm.prompts[1]
    assert len(records) == 3
    assert "diego maradona" in nodes
    assert "throat cancer" in nodes
    assert ("diego maradona", "throat cancer") in edges


def test_two_pass_extraction_skips_second_pass_when_no_valid_entities_exist() -> None:
    """The two-pass flow should fail closed when pass one yields no valid entities."""

    first_pass = (
        '("entity"<|>"his"<|>"person"<|>"anaphoric placeholder")'
        f"{DEFAULT_RECORD_DELIMITER}"
        '("entity"<|>"s"<|>"person"<|>"single-letter junk")'
        f"{DEFAULT_COMPLETION_DELIMITER}"
    )
    extractor = _TwoPassHarness([first_pass])

    records = asyncio.run(extractor._extract_records_from_chunk(_chunk()))

    assert records == []
    assert len(extractor.llm.prompts) == 1
