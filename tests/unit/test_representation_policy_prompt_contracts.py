"""Regression tests for representation-policy guidance in build/retrieval prompts.

These tests lock in the shared prompt contract introduced after ADR-013:
graph construction should avoid promoting every detailed phrase to a node, and
retrieval agents should understand that the graph is a retrieval-optimized view
rather than an exhaustive ontology of the corpus.
"""

from __future__ import annotations

from pathlib import Path

from Core.Prompt import GraphPrompt


def test_grounded_entity_prompt_mentions_retrieval_anchor_policy() -> None:
    """Build prompts should explain when a standalone entity is worth materializing."""

    prompt_text = GraphPrompt.build_entity_inventory_extraction_prompt(
        input_text="{input}",
        entity_types=[],
        tuple_delimiter="<|>",
        record_delimiter="##",
        completion_delimiter="<|COMPLETE|>",
        include_slot_discipline=True,
        include_grounded_entity_preference=True,
        schema_guidance="",
    )

    assert "reusable retrieval anchor, bridge, or relationship endpoint" in prompt_text
    assert "does not need independent graph navigation" in prompt_text


def test_hybrid_benchmark_prompt_mentions_non_exhaustive_graph_representation() -> None:
    """Hybrid retrieval prompt should explain that node absence is not fact absence."""

    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "agent_benchmark_hybrid.yaml"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "retrieval-optimized representation, not an" in prompt_text
    assert "Absence of a standalone node does not imply absence of evidence." in prompt_text


def test_hybrid_benchmark_prompt_requires_canonical_anchor_resolution() -> None:
    """Hybrid prompt should define when an anchor atom is actually resolved."""

    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "agent_benchmark_hybrid.yaml"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "An anchor atom is resolved only after you have one canonical entity ID" in prompt_text
    assert "`entity_select_candidate` or `search_then_expand_onehop`" in prompt_text


def test_fixed_graph_prompt_mentions_chunk_pivot_for_missing_qualifiers() -> None:
    """Fixed-graph retrieval prompt should direct the agent to chunk evidence when needed."""

    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "agent_benchmark_fixed_graph.yaml"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "retrieval-optimized view, not a list of every fact phrase" in prompt_text
    assert "Absence of a standalone node does not imply absence of evidence" in prompt_text


def test_codex_compact_prompt_mentions_relationship_or_chunk_fallback() -> None:
    """Compact benchmark prompt should preserve the same representation-policy awareness."""

    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "agent_benchmark_codex_compact.yaml"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "retrieval-optimized representation, not an exhaustive ontology" in prompt_text
    assert "check relationship descriptions or chunk text" in prompt_text
    assert "An anchor or bridge step is not done until you have one canonical entity ID" in prompt_text
