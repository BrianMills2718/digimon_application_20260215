"""Tests for schema guidance resolution under open and declared palettes."""

from __future__ import annotations

from Config.GraphConfig import GraphConfig
from Core.Common.Constants import DEFAULT_ENTITY_TYPES
from Core.Common.graph_schema_guidance import resolve_entity_type_names
from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode


def test_open_schema_without_explicit_palette_returns_no_entity_types() -> None:
    """Open schema without declared types should stay truly open."""

    graph_config = GraphConfig(
        graph_profile=GraphProfile.TKG,
        schema_mode=GraphSchemaMode.OPEN,
    )

    assert resolve_entity_type_names(graph_config) == []


def test_open_schema_preserves_explicit_entity_palette() -> None:
    """Explicit palettes remain authoritative even in open mode."""

    graph_config = GraphConfig(
        graph_profile=GraphProfile.TKG,
        schema_mode=GraphSchemaMode.OPEN,
        schema_entity_types=["person", "diagnosis", "award"],
    )

    assert resolve_entity_type_names(graph_config) == ["person", "diagnosis", "award"]


def test_open_schema_preserves_custom_ontology_entity_palette() -> None:
    """Custom ontology entity names should remain available in open mode."""

    graph_config = GraphConfig(
        graph_profile=GraphProfile.TKG,
        schema_mode=GraphSchemaMode.OPEN,
        loaded_custom_ontology={
            "entities": [
                {"name": "diagnosis"},
                {"name": "award"},
            ]
        },
    )

    assert resolve_entity_type_names(graph_config) == ["diagnosis", "award"]


def test_schema_guided_without_explicit_palette_keeps_default_entity_types() -> None:
    """Non-open modes keep the legacy fallback palette for this slice."""

    graph_config = GraphConfig(
        graph_profile=GraphProfile.TKG,
        schema_mode=GraphSchemaMode.SCHEMA_GUIDED,
    )

    assert resolve_entity_type_names(graph_config) == DEFAULT_ENTITY_TYPES
