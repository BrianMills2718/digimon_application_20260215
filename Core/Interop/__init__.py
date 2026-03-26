"""Interop helpers for external system data flowing into DIGIMON."""

from .onto_canon_import import (
    OntoCanonImportResult,
    import_onto_canon_jsonl,
    load_entity_records,
    load_relationship_records,
)

__all__ = [
    "OntoCanonImportResult",
    "import_onto_canon_jsonl",
    "load_entity_records",
    "load_relationship_records",
]
