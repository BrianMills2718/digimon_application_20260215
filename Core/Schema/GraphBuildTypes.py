"""Typed enums for graph build profiles, topology families, and schema modes.

These enums define the stable vocabulary for graph-build contracts. They are
shared between config, persisted manifests, and build-time prompt selection so
the system can describe what was built without relying on ad hoc string values.
"""

from __future__ import annotations

from enum import Enum


class GraphTopologyKind(str, Enum):
    """Top-level graph topology families supported by DIGIMON."""

    ENTITY = "entity_graph"
    PASSAGE = "passage_graph"
    TREE = "tree_graph"


class GraphProfile(str, Enum):
    """Named graph attribute profiles used for reproducible builds."""

    KG = "KG"
    TKG = "TKG"
    RKG = "RKG"
    PASSAGE = "PASSAGE"
    TREE = "TREE"


class GraphSchemaMode(str, Enum):
    """How strongly the build prompt should constrain extracted graph structure."""

    OPEN = "open"
    SCHEMA_GUIDED = "schema_guided"
    SCHEMA_CONSTRAINED = "schema_constrained"

    @classmethod
    def _normalise_value(cls, value: object) -> str:
        """Normalize legacy or legacy-styled schema mode values into current values."""

        normalised = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        alias_map = {
            "guided": cls.SCHEMA_GUIDED.value,
            "schema_guided": cls.SCHEMA_GUIDED.value,
            "schemaguided": cls.SCHEMA_GUIDED.value,
            "mixed": cls.SCHEMA_GUIDED.value,
            "open_guided": cls.SCHEMA_GUIDED.value,
            "open_guided_mode": cls.SCHEMA_GUIDED.value,
            "closed": cls.SCHEMA_CONSTRAINED.value,
            "schema_constrained": cls.SCHEMA_CONSTRAINED.value,
            "schemaconstrained": cls.SCHEMA_CONSTRAINED.value,
            "constrained": cls.SCHEMA_CONSTRAINED.value,
            "schema_constrain": cls.SCHEMA_CONSTRAINED.value,
        }
        if normalised in alias_map:
            return alias_map[normalised]
        if normalised in {"open", "schema_open", "open_mode"}:
            return cls.OPEN.value
        if normalised in {"openguide", "openguided"}:
            return cls.SCHEMA_GUIDED.value
        if normalised in {cls.OPEN.value, cls.SCHEMA_GUIDED.value, cls.SCHEMA_CONSTRAINED.value}:
            return normalised
        return normalised

    @classmethod
    def parse(cls, value: object) -> "GraphSchemaMode":
        """Parse a schema mode string or enum using legacy aliases safely."""

        if isinstance(value, cls):
            return value
        return cls(cls._normalise_value(value))

    @classmethod
    def _missing_(cls, value: object) -> "GraphSchemaMode | None":
        """Enable legacy-mode parsing through Enum construction."""

        try:
            return cls(cls._normalise_value(value))
        except ValueError:
            return None
