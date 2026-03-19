"""Unit tests for entity-name validation and ranking helpers."""

from Core.Common.entity_name_hygiene import (
    build_search_keys,
    classify_entity_name,
    score_entity_candidate,
)


def test_classify_entity_name_rejects_blank_and_single_letter_junk() -> None:
    """Blank names and one-letter alphabetic nodes should be rejected."""

    assert classify_entity_name("")[0] is False
    assert classify_entity_name("   ")[0] is False
    assert classify_entity_name("s") == (False, "single_alpha_character")
    assert classify_entity_name("J") == (False, "single_alpha_character")
    assert classify_entity_name("UK")[0] is True


def test_build_search_keys_handles_unicode_and_ascii_alias() -> None:
    """Search keys should preserve Unicode and provide an ASCII alias."""

    keys = build_search_keys("São José dos Campos")
    assert "são josé dos campos" in keys
    assert "sao jose dos campos" in keys


def test_score_entity_candidate_prefers_exact_match_over_prefix_noise() -> None:
    """Exact full-title matches should outrank shorter prefix candidates."""

    exact = score_entity_candidate(
        query_text="Sous les pieds des femmes",
        candidate_name="Sous les pieds des femmes",
    )
    prefix = score_entity_candidate(
        query_text="Sous les pieds des femmes",
        candidate_name="Sous",
    )
    assert exact.match_type == "exact"
    assert exact.score > prefix.score
