"""Regression tests for the profile-aware prebuild graph CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode
from eval.prebuild_graph import (
    build_prebuild_llm,
    build_er_config_overrides,
    build_requires_fresh_graph,
    ensure_existing_graph_can_be_reused,
    parse_args,
    resolve_build_fallback_models,
    resolve_artifact_dataset_name,
)


def test_parse_args_accepts_profile_schema_and_chunk_limit() -> None:
    """CLI parsing should preserve the requested build contract fields."""

    args = parse_args(
        [
            "MuSiQue",
            "--artifact-dataset-name",
            "MuSiQue_tkg_smoke",
            "--graph-profile",
            "tkg",
            "--schema-mode",
            "schema_guided",
            "--schema-entity-type",
            "person",
            "--schema-relation-type",
            "located_in",
            "--strict-extraction-slot-discipline",
            "--two-pass-extraction",
            "--prefer-grounded-named-entities",
            "--enable-chunk-cooccurrence",
            "--enable-passage-nodes",
            "--lane-policy",
            "pure",
            "--chunk-limit",
            "25",
        ]
    )

    assert args.dataset == "MuSiQue"
    assert args.artifact_dataset_name == "MuSiQue_tkg_smoke"
    assert args.graph_profile == "tkg"
    assert args.schema_mode == GraphSchemaMode.SCHEMA_GUIDED
    assert args.schema_entity_type == ["person"]
    assert args.schema_relation_type == ["located_in"]
    assert args.strict_extraction_slot_discipline is True
    assert args.two_pass_extraction is True
    assert args.prefer_grounded_named_entities is True
    assert args.enable_chunk_cooccurrence is True
    assert args.enable_passage_nodes is True
    assert args.lane_policy == "pure"
    assert args.chunk_limit == 25


def test_build_er_config_overrides_requires_schema_mode_for_schema_lists() -> None:
    """Schema lists without an extraction mode should fail loudly."""

    args = parse_args(["MuSiQue", "--schema-entity-type", "person"])

    with pytest.raises(ValueError, match="Schema types require --schema-mode"):
        build_er_config_overrides(args)


def test_build_er_config_overrides_converts_cli_strings_to_enums() -> None:
    """Override construction should produce typed values for downstream config models."""

    args = parse_args(
        [
            "MuSiQue",
            "--graph-profile",
            "rkg",
            "--schema-mode",
            "schema_constrained",
            "--schema-entity-type",
            "person",
            "--schema-relation-type",
            "works_for",
            "--strict-extraction-slot-discipline",
            "--two-pass-extraction",
            "--prefer-grounded-named-entities",
            "--enable-chunk-cooccurrence",
            "--enable-passage-nodes",
        ]
    )

    overrides = build_er_config_overrides(args)

    assert overrides["graph_profile"] is GraphProfile.RKG
    assert overrides["schema_mode"] is GraphSchemaMode.SCHEMA_CONSTRAINED
    assert overrides["schema_entity_types"] == ["person"]
    assert overrides["schema_relation_types"] == ["works_for"]
    assert overrides["strict_extraction_slot_discipline"] is True
    assert overrides["two_pass_extraction"] is True
    assert overrides["prefer_grounded_named_entities"] is True
    assert overrides["enable_chunk_cooccurrence"] is True
    assert overrides["enable_passage_nodes"] is True


def test_build_er_config_overrides_accepts_legacy_schema_aliases() -> None:
    """Legacy schema aliases should still parse to the new enum names."""

    guided_alias_args = parse_args(
        [
            "MuSiQue",
            "--schema-mode",
            "guided",
            "--schema-entity-type",
            "person",
            "--schema-relation-type",
            "works_for",
        ]
    )
    closed_alias_args = parse_args(["MuSiQue", "--schema-mode", "closed"])

    assert guided_alias_args.schema_mode is GraphSchemaMode.SCHEMA_GUIDED
    assert closed_alias_args.schema_mode is GraphSchemaMode.SCHEMA_CONSTRAINED


def test_build_requires_fresh_graph_for_explicit_contract() -> None:
    """Explicit profile/schema/slice requests should not silently reuse old builds."""

    args = parse_args(["MuSiQue", "--chunk-limit", "10"])

    assert build_requires_fresh_graph(args) is True


def test_build_requires_fresh_graph_for_strict_slot_contract() -> None:
    """Strict extraction-slot discipline should force a fresh graph build."""

    args = parse_args(["MuSiQue", "--strict-extraction-slot-discipline"])

    assert build_requires_fresh_graph(args) is True


def test_build_requires_fresh_graph_for_grounded_entity_preference() -> None:
    """Grounded-entity preference should force a fresh graph build."""

    args = parse_args(["MuSiQue", "--prefer-grounded-named-entities"])

    assert build_requires_fresh_graph(args) is True


def test_build_requires_fresh_graph_for_two_pass_extraction() -> None:
    """Two-pass extraction requests should force a fresh graph build."""

    args = parse_args(["MuSiQue", "--two-pass-extraction"])

    assert build_requires_fresh_graph(args) is True


def test_build_requires_fresh_graph_for_pure_lane_policy() -> None:
    """Pure-lane requests should force a fresh graph artifact."""

    args = parse_args(["MuSiQue", "--lane-policy", "pure"])

    assert build_requires_fresh_graph(args) is True


def test_build_requires_fresh_graph_for_projection_overrides() -> None:
    """Projection toggles should force a fresh graph artifact."""

    chunk_args = parse_args(["MuSiQue", "--enable-chunk-cooccurrence"])
    passage_args = parse_args(["MuSiQue", "--enable-passage-nodes"])

    assert build_requires_fresh_graph(chunk_args) is True
    assert build_requires_fresh_graph(passage_args) is True


def test_resolve_artifact_dataset_name_defaults_to_source_dataset() -> None:
    """Artifact namespace should default to the source dataset name."""

    args = parse_args(["MuSiQue"])

    assert resolve_artifact_dataset_name(args) == "MuSiQue"


def test_resolve_artifact_dataset_name_prefers_explicit_alias() -> None:
    """Artifact namespace should use the explicit alias when provided."""

    args = parse_args(["MuSiQue", "--artifact-dataset-name", "MuSiQue_tkg_smoke"])

    assert resolve_artifact_dataset_name(args) == "MuSiQue_tkg_smoke"


def test_resolve_build_fallback_models_respects_lane_policy() -> None:
    """Pure-lane builds should clear fallbacks while reliability keeps them."""

    class _LLMConfig:
        model = "gemini/gemini-2.5-flash"
        fallback_models = ["openrouter/deepseek/deepseek-chat"]

    class _Config:
        llm = _LLMConfig()

    pure_args = parse_args(["MuSiQue", "--lane-policy", "pure"])
    reliability_args = parse_args(["MuSiQue"])

    assert resolve_build_fallback_models(pure_args, _Config()) == []
    assert resolve_build_fallback_models(reliability_args, _Config()) == [
        "openrouter/deepseek/deepseek-chat"
    ]


def test_build_prebuild_llm_uses_lane_policy_for_fallbacks() -> None:
    """Dedicated prebuild adapters should mirror the requested lane contract."""

    class _LLMConfig:
        model = "gemini/gemini-2.5-flash"
        fallback_models = ["openrouter/deepseek/deepseek-chat"]

    class _Config:
        llm = _LLMConfig()

    llm = build_prebuild_llm(parse_args(["MuSiQue", "--lane-policy", "pure"]), _Config())

    assert getattr(llm, "model") == "gemini/gemini-2.5-flash"
    assert getattr(llm, "_fallback_models") == []


def test_ensure_existing_graph_can_be_reused_rejects_stale_graph(tmp_path: Path) -> None:
    """Existing graphs should not be reused when the caller requested a new contract."""

    args = parse_args(["MuSiQue", "--graph-profile", "tkg"])
    graph_path = tmp_path / "existing.graphml"
    graph_path.write_text("placeholder", encoding="utf-8")

    with pytest.raises(ValueError, match="Re-run with --force-rebuild"):
        ensure_existing_graph_can_be_reused(args, graph_path)


def test_ensure_existing_graph_can_be_reused_allows_default_reuse(tmp_path: Path) -> None:
    """The default legacy path may still reuse an existing graph."""

    args = parse_args(["MuSiQue"])
    graph_path = tmp_path / "existing.graphml"
    graph_path.write_text("placeholder", encoding="utf-8")

    ensure_existing_graph_can_be_reused(args, graph_path)
