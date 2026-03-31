"""Utilities for validating and ranking graph entity names.

This module keeps entity-name matching logic isolated from MCP/server code so
it can be tested without importing the full DIGIMON runtime. The current graph
data contains low-signal entities such as empty strings or single letters,
which can dominate naive prefix matching. These helpers enforce a small amount
of hygiene and provide a Unicode-aware search key strategy for name lookup.

Plan #22 extends that contract: graph builders can now preserve a canonical
display name and normalized lookup metadata separately instead of collapsing
both concerns into the same storage field.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz
from unidecode import unidecode

from Core.Common.Constants import GRAPH_FIELD_SEP
from Core.Common.Utils import split_string_by_multi_markers

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


def normalize_display_name(raw_name: str) -> str:
    """Return a canonical display-form candidate without ASCII-stripping it.

    Graph node IDs may stay normalized for legacy compatibility, but canonical
    display names should preserve Unicode letters and case whenever the source
    text contained them. This helper only normalizes Unicode form and
    whitespace; it does not lowercase or strip punctuation beyond trimming.
    """

    return _collapse_whitespace(unicodedata.normalize("NFKC", str(raw_name or "")))


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


def split_identity_values(raw_value: Any) -> tuple[str, ...]:
    """Parse GraphML-safe identity metadata into de-duplicated text values.

    DIGIMON persists multi-valued graph attributes as ``GRAPH_FIELD_SEP``-
    joined strings so GraphML storage stays stable. Retrieval code should not
    have to guess whether an identity field arrived as one string, a list, or
    an already-split tuple.
    """

    if raw_value is None:
        return ()

    values: list[str]
    if isinstance(raw_value, str):
        values = split_string_by_multi_markers(raw_value, [GRAPH_FIELD_SEP])
    elif isinstance(raw_value, (list, tuple, set)):
        values = []
        for item in raw_value:
            values.extend(split_identity_values(item))
    else:
        values = [str(raw_value)]

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = normalize_display_name(value)
        if not candidate:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
    return tuple(cleaned)


def join_identity_values(values: Iterable[str]) -> str:
    """Serialize de-duplicated identity values into GraphML-safe storage."""

    return GRAPH_FIELD_SEP.join(split_identity_values(list(values)))


def select_canonical_display_name(
    values: Sequence[str],
    *,
    fallback: str,
) -> str:
    """Choose the most human-readable display name from observed candidates.

    When the same entity is seen under both raw source text and normalized node
    IDs, prefer the form that preserves more human-facing signal. This remains
    heuristic, but it is deterministic and intentionally favors Unicode,
    mixed-case, and non-lossy spacing over storage-oriented identifiers.
    """

    candidates = list(split_identity_values(values))
    if not candidates:
        fallback_name = normalize_display_name(fallback)
        return fallback_name or str(fallback)

    def _score(name: str) -> tuple[int, int, int, int, int]:
        compact = name.replace(" ", "")
        has_non_ascii = int(any(ord(char) > 127 for char in name))
        has_upper = int(any(char.isupper() for char in name))
        has_punctuation = int(bool(re.search(r"[^\w\s]", name, flags=re.UNICODE)))
        token_count = len(name.split())
        return (
            has_non_ascii,
            has_upper,
            has_punctuation,
            token_count,
            len(compact),
        )

    return max(candidates, key=_score)


def build_identity_payload(
    raw_names: Sequence[str],
    *,
    fallback_entity_name: str,
    extra_aliases: Sequence[str] = (),
    include_aliases: bool = True,
) -> dict[str, str]:
    """Build canonical display and lookup metadata for one graph entity.

    The payload is GraphML-safe: multi-valued fields are stored as
    ``GRAPH_FIELD_SEP``-joined strings. ``fallback_entity_name`` is still
    included in the lookup-key pool so retrieval can bridge from legacy node IDs
    to canonical display names while the graph ID strategy remains unchanged.
    """

    observed_names = split_identity_values(raw_names)
    observed_aliases = split_identity_values(extra_aliases)
    canonical_name = select_canonical_display_name(
        observed_names,
        fallback=fallback_entity_name,
    )

    search_key_values: list[str] = []
    for value in (
        canonical_name,
        fallback_entity_name,
        *observed_names,
        *observed_aliases,
    ):
        search_key_values.extend(build_search_keys(value))

    payload = {
        "canonical_name": canonical_name,
        "search_keys": join_identity_values(search_key_values),
    }

    if include_aliases:
        alias_values = [
            alias
            for alias in (*observed_names, *observed_aliases)
            if alias.casefold() != canonical_name.casefold()
        ]
        alias_string = join_identity_values(alias_values)
        if alias_string:
            payload["aliases"] = alias_string

    return payload


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
