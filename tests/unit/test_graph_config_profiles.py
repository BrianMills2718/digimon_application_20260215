"""Unit tests for graph profile and schema-mode behavior in GraphConfig."""

from __future__ import annotations

import pytest

from Config.GraphConfig import GraphConfig
from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode


def test_kg_profile_locks_minimal_two_step_entity_graph_contract() -> None:
    """KG profile should normalize the config to the current minimal KG build path."""

    config = GraphConfig(graph_profile=GraphProfile.KG)

    assert config.extract_two_step is True
    assert config.enable_entity_type is False
    assert config.enable_entity_description is False
    assert config.enable_edge_name is True
    assert config.enable_edge_description is False
    assert config.enable_edge_keywords is False


def test_rkg_profile_locks_rich_delimiter_entity_graph_contract() -> None:
    """RKG profile should normalize the config to the richest current delimiter path."""

    config = GraphConfig(
        graph_profile=GraphProfile.RKG,
        schema_mode=GraphSchemaMode.SCHEMA_GUIDED,
        schema_entity_types=["person"],
        schema_relation_types=["located_in"],
    )

    assert config.extract_two_step is False
    assert config.enable_entity_type is True
    assert config.enable_entity_description is True
    assert config.enable_edge_name is True
    assert config.enable_edge_description is True
    assert config.enable_edge_keywords is True
    assert config.schema_mode is GraphSchemaMode.SCHEMA_GUIDED


def test_profile_assignment_revalidates_existing_config() -> None:
    """Validated assignment should apply profile defaults during tool-style overrides."""

    config = GraphConfig()
    config.graph_profile = GraphProfile.TKG

    assert config.extract_two_step is False
    assert config.enable_entity_type is True
    assert config.enable_entity_description is True
    assert config.enable_edge_name is True
    assert config.enable_edge_description is True


def test_strict_extraction_slot_discipline_is_assignable_contract_flag() -> None:
    """The stricter extraction prompt contract should be a first-class typed flag."""

    config = GraphConfig(graph_profile=GraphProfile.TKG)
    config.strict_extraction_slot_discipline = True

    assert config.strict_extraction_slot_discipline is True


def test_grounded_entity_preference_is_assignable_contract_flag() -> None:
    """The grounded-entity prompt preference should be a first-class typed flag."""

    config = GraphConfig(graph_profile=GraphProfile.TKG)
    config.prefer_grounded_named_entities = True

    assert config.prefer_grounded_named_entities is True


def test_entity_graph_rejects_tree_profile() -> None:
    """Entity graph configs should fail loudly on topology/profile mismatches."""

    with pytest.raises(ValueError, match="Entity-graph builds must not use"):
        GraphConfig(type="er_graph", graph_profile=GraphProfile.TREE)


def test_graph_schema_mode_parse_keeps_legacy_mode_terms() -> None:
    """Backward-compatible schema-mode aliases should resolve to canonical terms."""

    assert GraphSchemaMode.parse("guided") is GraphSchemaMode.SCHEMA_GUIDED
    assert GraphSchemaMode.parse("closed") is GraphSchemaMode.SCHEMA_CONSTRAINED
    assert GraphSchemaMode.parse("schema_guided") is GraphSchemaMode.SCHEMA_GUIDED
    assert GraphSchemaMode.parse("schema_constrained") is GraphSchemaMode.SCHEMA_CONSTRAINED
