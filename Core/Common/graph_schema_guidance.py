"""Helpers for turning graph config schema settings into prompt guidance.

The current graph builders support both legacy custom ontology files and the
newer explicit schema contract on `GraphConfig`. These helpers normalize both
surfaces into the entity/relation type lists and guidance text that extraction
prompts can consume without importing the heavier graph package.
"""

from __future__ import annotations

from typing import Any

from Core.Common.Constants import DEFAULT_ENTITY_TYPES
from Core.Schema.GraphBuildTypes import GraphSchemaMode


def resolve_entity_type_names(graph_config: Any) -> list[str]:
    """Return the entity types that should guide extraction for this build."""

    schema_entity_types = list(getattr(graph_config, "schema_entity_types", []) or [])
    if schema_entity_types:
        return schema_entity_types

    custom_ontology = getattr(graph_config, "loaded_custom_ontology", None)
    if custom_ontology and custom_ontology.get("entities"):
        names = [
            entity_def.get("name", "").strip()
            for entity_def in custom_ontology["entities"]
            if entity_def.get("name", "").strip()
        ]
        if names:
            return names

    return list(DEFAULT_ENTITY_TYPES)


def resolve_relation_type_names(graph_config: Any) -> list[str]:
    """Return the relation types that should guide extraction for this build."""

    schema_relation_types = list(getattr(graph_config, "schema_relation_types", []) or [])
    if schema_relation_types:
        return schema_relation_types

    custom_ontology = getattr(graph_config, "loaded_custom_ontology", None)
    if custom_ontology and custom_ontology.get("relations"):
        names = [
            relation_def.get("name", "").strip()
            for relation_def in custom_ontology["relations"]
            if relation_def.get("name", "").strip()
        ]
        if names:
            return names

    return []


def build_schema_guidance_text(
    *,
    graph_config: Any,
    entity_types: list[str],
    relation_types: list[str],
) -> str:
    """Return prompt guidance text for the configured schema mode.

    `open` mode keeps extraction unconstrained. `schema_guided` mode encourages
    the listed types without forbidding new ones. `schema_constrained` mode
    requires the prompt to stay within the declared type lists when they are
    provided.
    """

    schema_mode = getattr(graph_config, "schema_mode", GraphSchemaMode.OPEN)
    schema_mode = GraphSchemaMode.parse(schema_mode)

    if schema_mode is GraphSchemaMode.OPEN:
        return ""

    guidance_lines: list[str] = ["-Schema Guidance-"]

    if schema_mode is GraphSchemaMode.SCHEMA_GUIDED:
        guidance_lines.append("Prefer the declared schema when labeling entities and relationships.")
    else:
        guidance_lines.append("Use only the declared schema when labeling entities and relationships.")

    if entity_types:
        joined_entity_types = ", ".join(entity_types)
        if schema_mode is GraphSchemaMode.SCHEMA_CONSTRAINED:
            guidance_lines.append(f"Allowed entity types: {joined_entity_types}")
        else:
            guidance_lines.append(f"Preferred entity types: {joined_entity_types}")

    if relation_types:
        joined_relation_types = ", ".join(relation_types)
        if schema_mode is GraphSchemaMode.SCHEMA_CONSTRAINED:
            guidance_lines.append(f"Allowed relation types: {joined_relation_types}")
        else:
            guidance_lines.append(f"Preferred relation types: {joined_relation_types}")

    return "\n".join(guidance_lines)
