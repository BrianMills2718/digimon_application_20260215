"""Unit tests for typed extraction-record validation helpers."""

from __future__ import annotations

from Core.Common.extraction_validation import (
    looks_like_relation_phrase,
    strip_extraction_field_markup,
    validate_entity_record,
    validate_relationship_record,
)


def test_rejects_null_entity_type_for_tkg_profile() -> None:
    """Typed profiles should reject placeholder entity types."""

    is_valid, reason = validate_entity_record(
        "sextuple",
        "null",
        require_typed_entities=True,
    )

    assert is_valid is False
    assert reason == "missing_entity_type_for_typed_profile"


def test_allows_null_entity_type_for_untyped_profile() -> None:
    """Untyped profiles may keep records that lack a concrete entity type."""

    is_valid, reason = validate_entity_record(
        "sextuple",
        "null",
        require_typed_entities=False,
    )

    assert is_valid is True
    assert reason is None


def test_rejects_malformed_relationship_slots() -> None:
    """Relationship records should reject object slots that look like predicates."""

    is_valid, reason = validate_relationship_record(
        "barcelona",
        "won by",
        "extra time",
        require_relation_name=True,
    )

    assert is_valid is False
    assert reason == "relationship_object_looks_like_predicate"


def test_relation_phrase_detector_catches_short_predicates() -> None:
    """Known short predicate phrases should not survive as entity slots."""

    assert looks_like_relation_phrase("located in") is True
    assert looks_like_relation_phrase("part of") is True
    assert looks_like_relation_phrase("real madrid") is False


def test_strip_extraction_field_markup_removes_field_wrappers_only() -> None:
    """Tag wrappers should be removed without deleting bracketed content."""

    assert strip_extraction_field_markup("<entity_name>Barcelona") == "Barcelona"
    assert strip_extraction_field_markup("<entity_type>None") == "None"
    assert strip_extraction_field_markup("<4-0 away win>") == "<4-0 away win>"
