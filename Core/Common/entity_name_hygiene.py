"""Utilities for validating and ranking graph entity names.

This module keeps entity-name matching logic isolated from MCP/server code so
it can be tested without importing the full DIGIMON runtime. The current graph
data contains low-signal entities such as empty strings or single letters,
which can dominate naive prefix matching. These helpers enforce a small amount
of hygiene and provide a Unicode-aware search key strategy for name lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import re
import unicodedata

from rapidfuzz import fuzz
from unidecode import unidecode

_NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class EntityMatchScore:
    """Similarity score for one entity candidate.

    Attributes:
        score: Normalized score between 0 and 100. Higher is better.
        match_type: Human-readable label describing why the candidate matched.
    """

    score: float
    match_type: str


def _collapse_whitespace(value: str) -> str:
    """Collapse repeated whitespace and trim outer spaces."""

    return _WHITESPACE_RE.sub(" ", value).strip()


def _normalize_for_matching(raw_name: str, *, ascii_only: bool) -> str:
    """Normalize text into a search key while preserving word boundaries.

    The matching form should be robust to punctuation, casing, and optionally
    diacritics. This intentionally does not serve as a canonical entity ID.
    """

    normalized = unicodedata.normalize("NFKC", raw_name)
    if ascii_only:
        normalized = unidecode(normalized)
    normalized = normalized.casefold()
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return _collapse_whitespace(normalized)


def build_search_keys(raw_name: str) -> tuple[str, ...]:
    """Build Unicode-aware and ASCII search keys for one entity name.

    Returns a de-duplicated tuple of normalized keys. The first item preserves
    Unicode letters when available; later items are ASCII aliases for matching
    user queries against stored names that lost accents or transliterations.
    """

    keys: list[str] = []
    for ascii_only in (False, True):
        key = _normalize_for_matching(raw_name, ascii_only=ascii_only)
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def classify_entity_name(raw_name: str) -> tuple[bool, str]:
    """Return whether an entity name is usable for graph lookup.

    This is intentionally conservative. Names that are empty after
    normalization or collapse into a single alphabetic character are treated as
    low-signal junk and should not be surfaced to retrieval agents.
    """

    if not raw_name or not raw_name.strip():
        return False, "blank"

    normalized_keys = build_search_keys(raw_name)
    if not normalized_keys:
        return False, "blank_after_normalization"

    primary_key = normalized_keys[0]
    compact = primary_key.replace(" ", "")
    if len(compact) == 1 and compact.isalpha():
        return False, "single_alpha_character"

    return True, "ok"


def score_entity_candidate(
    query_text: str,
    candidate_name: str,
    aliases: Sequence[str] = (),
) -> EntityMatchScore:
    """Score one entity candidate against a free-form query.

    The score is designed for entity-name search, not full-text retrieval. It
    strongly rewards exact normalized matches, then uses RapidFuzz for robust
    fuzzy matching across Unicode and ASCII aliases. Short candidates receive a
    modest penalty so near-empty names do not outrank full entities.
    """

    valid_query, _ = classify_entity_name(query_text)
    valid_candidate, _ = classify_entity_name(candidate_name)
    if not valid_query or not valid_candidate:
        return EntityMatchScore(score=0.0, match_type="invalid")

    query_keys = build_search_keys(query_text)
    candidate_keys: list[str] = list(build_search_keys(candidate_name))
    for alias in aliases:
        for key in build_search_keys(alias):
            if key not in candidate_keys:
                candidate_keys.append(key)

    best_score = 0.0
    best_match_type = "none"

    for query_key in query_keys:
        for candidate_key in candidate_keys:
            if query_key == candidate_key:
                if 100.0 > best_score:
                    best_score = 100.0
                    best_match_type = "exact"
                continue

            if (
                len(query_key) >= 3
                and len(candidate_key) >= 3
                and (candidate_key.startswith(query_key) or query_key.startswith(candidate_key))
            ):
                prefix_score = 95.0 if candidate_key.startswith(query_key) else 92.0
                if prefix_score > best_score:
                    best_score = prefix_score
                    best_match_type = "prefix"

            fuzzy_score = max(
                float(fuzz.WRatio(query_key, candidate_key)),
                float(fuzz.token_set_ratio(query_key, candidate_key)),
                float(fuzz.partial_ratio(query_key, candidate_key)) - 5.0,
            )

            overlap = len(set(query_key.split()) & set(candidate_key.split()))
            if overlap:
                fuzzy_score += min(float(overlap) * 2.0, 6.0)

            candidate_compact_len = len(candidate_key.replace(" ", ""))
            if candidate_compact_len < 3:
                fuzzy_score -= 20.0
            elif candidate_compact_len < max(4, len(query_key.replace(" ", "")) // 3):
                fuzzy_score -= 8.0

            if fuzzy_score > best_score:
                best_score = max(fuzzy_score, 0.0)
                best_match_type = "fuzzy"

    capped_score = min(best_score, 100.0)
    if best_match_type != "exact":
        capped_score = min(capped_score, 99.0)
    return EntityMatchScore(score=capped_score, match_type=best_match_type)
