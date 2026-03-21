"""Validation helpers for entity-graph extraction records.

These checks sit between raw LLM extraction tuples and graph persistence. Their
job is not to fully understand semantics; it is to fail loudly on structurally
bad records that we already know contaminate TKG-style builds.
"""

from __future__ import annotations

import re
from typing import Final

from Core.Common.entity_name_hygiene import classify_entity_name

_NULL_ENTITY_TYPE_VALUES: Final[frozenset[str]] = frozenset(
    {"", "null", "none", "unknown", "n/a", "na"}
)
_RELATION_VERB_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "associated",
        "beat",
        "composed",
        "employed",
        "eliminated",
        "hired",
        "hoped",
        "located",
        "lost",
        "part",
        "played",
        "reached",
        "resigned",
        "signed",
        "suffered",
        "took",
        "transferred",
        "won",
    }
)
_RELATION_PREPOSITION_TOKENS: Final[frozenset[str]] = frozenset(
    {"as", "at", "by", "for", "from", "in", "of", "on", "to", "with"}
)
_EXTRACTION_FIELD_TAG_NAMES: Final[frozenset[str]] = frozenset(
    {
        "entity_name",
        "entity_type",
        "entity_description",
        "source_entity",
        "target_entity",
        "relation_name",
        "relationship_description",
        "relationship_keywords",
        "relationship_strength",
    }
)
_FIELD_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"</?(?:"
    + "|".join(sorted(_EXTRACTION_FIELD_TAG_NAMES))
    + r")>"
)
_ANAPHORIC_ENTITY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "he",
        "him",
        "his",
        "it",
        "its",
        "she",
        "them",
        "their",
        "they",
    }
)
_PLACEHOLDER_DESCRIPTION_PATTERNS: Final[tuple[str, ...]] = (
    "name is not specified",
    "name was not specified",
    "subject of the sentence",
    "person whose name is not specified",
)


def _normalize_space(text: str) -> str:
    """Return a single-space-normalized version of a cleaned text value."""

    return " ".join(text.split())


def strip_extraction_field_markup(text: str) -> str:
    """Remove XML-like field tags that some extraction responses leak into tuples.

    This strips wrappers such as ``<entity_name>`` and
    ``</relationship_description>`` while preserving content-like angle-bracket
    text such as ``<4-0 away win>`` or legitimate typed values like ``<person>``.
    """

    return _FIELD_TAG_PATTERN.sub("", text).strip()


def looks_like_relation_phrase(text: str) -> bool:
    """Return whether a would-be entity slot looks like a predicate phrase.

    This intentionally catches only short verb/preposition phrases that are
    implausible entity IDs in the current graph build contract, such as
    ``won by`` or ``located in``.
    """

    normalized = _normalize_space(text.lower())
    if not normalized:
        return True

    tokens = normalized.split()
    if len(tokens) > 3:
        return False
    if len(tokens) == 1:
        return tokens[0] in _RELATION_VERB_TOKENS

    last_token = tokens[-1]
    preceding_tokens = tokens[:-1]
    return last_token in _RELATION_PREPOSITION_TOKENS and any(
        token in _RELATION_VERB_TOKENS for token in preceding_tokens
    )


def looks_like_anaphoric_entity(text: str) -> bool:
    """Return whether an entity slot is just an anaphoric placeholder.

    DIGIMON's entity graphs are intended to store referential entities, not
    unresolved pronouns carried over from local sentence context. A small
    explicit set catches the observed smoke-build failures without trying to
    solve coreference generally.
    """

    normalized = _normalize_space(text.lower())
    return normalized in _ANAPHORIC_ENTITY_NAMES


def validate_entity_record(
    entity_name: str,
    entity_type: str,
    *,
    entity_description: str = "",
    require_typed_entities: bool,
) -> tuple[bool, str | None]:
    """Validate one extracted entity record for graph persistence."""

    is_valid_name, invalid_name_reason = classify_entity_name(entity_name)
    if not is_valid_name:
        return False, f"invalid_entity_name:{invalid_name_reason}"
    if looks_like_anaphoric_entity(entity_name):
        return False, "anaphoric_entity_name"

    normalized_entity_type = _normalize_space(entity_type.lower())
    if require_typed_entities and normalized_entity_type in _NULL_ENTITY_TYPE_VALUES:
        return False, "missing_entity_type_for_typed_profile"
    normalized_description = _normalize_space(entity_description.lower())
    if any(pattern in normalized_description for pattern in _PLACEHOLDER_DESCRIPTION_PATTERNS):
        return False, "placeholder_entity_description"

    return True, None


def validate_relationship_record(
    src_id: str,
    tgt_id: str,
    relation_name: str,
    *,
    require_relation_name: bool,
) -> tuple[bool, str | None]:
    """Validate one extracted relationship record before graph persistence."""

    for label, candidate in (("src_id", src_id), ("tgt_id", tgt_id)):
        is_valid_name, invalid_name_reason = classify_entity_name(candidate)
        if not is_valid_name:
            return False, f"invalid_{label}:{invalid_name_reason}"
        if looks_like_anaphoric_entity(candidate):
            return False, f"anaphoric_{label}"

    if looks_like_relation_phrase(src_id):
        return False, "relationship_subject_looks_like_predicate"
    if looks_like_relation_phrase(tgt_id):
        return False, "relationship_object_looks_like_predicate"

    normalized_relation_name = _normalize_space(relation_name)
    if require_relation_name and not normalized_relation_name:
        return False, "missing_relation_name"

    return True, None
