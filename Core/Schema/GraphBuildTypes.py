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
    GUIDED = "guided"
    CLOSED = "closed"
