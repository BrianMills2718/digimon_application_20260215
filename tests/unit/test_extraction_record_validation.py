"""Unit tests for typed extraction-record validation helpers."""

from __future__ import annotations

from Core.Common.extraction_validation import (
    looks_like_anaphoric_entity,
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


def test_rejects_anaphoric_placeholder_entity_names() -> None:
    """Pronoun-like placeholders should not become persisted graph entities."""

    is_valid, reason = validate_entity_record(
        "His",
        "person",
        entity_description="A male individual whose name is not specified in the text.",
        require_typed_entities=True,
    )

    assert is_valid is False
    assert reason == "anaphoric_entity_name"


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


def test_rejects_anaphoric_relationship_slots() -> None:
    """Relationship endpoints that are only pronouns should fail loudly."""

    is_valid, reason = validate_relationship_record(
        "His",
        "Athletic Bilbao",
        "played for",
        require_relation_name=True,
    )

    assert is_valid is False
    assert reason == "anaphoric_src_id"


def test_relation_phrase_detector_catches_short_predicates() -> None:
    """Known short predicate phrases should not survive as entity slots."""

    assert looks_like_relation_phrase("located in") is True
    assert looks_like_relation_phrase("part of") is True
    assert looks_like_relation_phrase("real madrid") is False


def test_anaphora_detector_catches_simple_pronouns() -> None:
    """Anaphoric placeholders should be recognized independently of parsing."""

    assert looks_like_anaphoric_entity("his") is True
    assert looks_like_anaphoric_entity("their") is True
    assert looks_like_anaphoric_entity("lionel messi") is False


def test_strip_extraction_field_markup_removes_field_wrappers_only() -> None:
    """Tag wrappers should be removed without deleting bracketed content."""

    assert strip_extraction_field_markup("<entity_name>Barcelona") == "Barcelona"
    assert strip_extraction_field_markup("<entity_type>None") == "None"
    assert (
        strip_extraction_field_markup("<entity_type>person</entity_type>")
        == "person"
    )
    assert strip_extraction_field_markup("<person>") == "<person>"
    assert strip_extraction_field_markup("<organization>") == "<organization>"
    assert strip_extraction_field_markup("<4-0 away win>") == "<4-0 away win>"
