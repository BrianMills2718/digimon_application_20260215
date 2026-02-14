"""Tests for OperatorComposer — method profiling, plan building, validation."""

import os
import sys

import pytest

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="module")
def composer():
    from Core.Operators.registry import REGISTRY
    from Core.Composition.OperatorComposer import OperatorComposer

    return OperatorComposer(REGISTRY)


class TestProfileBuilding:

    def test_all_10_methods_profiled(self, composer):
        profiles = composer.get_method_profiles()
        assert len(profiles) == 10
        names = {p.name for p in profiles}
        expected = {
            "basic_local", "basic_global", "lightrag", "fastgraphrag",
            "hipporag", "tog", "gr", "dalk", "kgp", "med",
        }
        assert names == expected

    def test_basic_local_profile(self, composer):
        p = composer.get_profile("basic_local")
        assert p is not None
        assert "entity.vdb" in p.operator_chain
        assert "relationship.onehop" in p.operator_chain
        assert "chunk.occurrence" in p.operator_chain
        assert p.requires_entity_vdb is True
        assert p.has_loop is False

    def test_basic_global_profile(self, composer):
        p = composer.get_profile("basic_global")
        assert p is not None
        assert "community.from_level" in p.operator_chain
        assert p.requires_community is True

    def test_lightrag_profile(self, composer):
        p = composer.get_profile("lightrag")
        assert p is not None
        assert "relationship.vdb" in p.operator_chain
        assert p.requires_relationship_vdb is True

    def test_fastgraphrag_profile(self, composer):
        p = composer.get_profile("fastgraphrag")
        assert p is not None
        assert "entity.ppr" in p.operator_chain
        assert "chunk.aggregator" in p.operator_chain
        assert p.requires_sparse_matrices is True

    def test_hipporag_profile(self, composer):
        p = composer.get_profile("hipporag")
        assert p is not None
        assert "meta.extract_entities" in p.operator_chain
        assert p.uses_llm_operators is True

    def test_tog_has_loop(self, composer):
        p = composer.get_profile("tog")
        assert p is not None
        assert p.has_loop is True
        assert p.uses_llm_operators is True

    def test_gr_requires_dual_vdb(self, composer):
        p = composer.get_profile("gr")
        assert p is not None
        assert p.requires_entity_vdb is True
        assert p.requires_relationship_vdb is True
        assert "meta.pcst_optimize" in p.operator_chain

    def test_kgp_has_loop(self, composer):
        p = composer.get_profile("kgp")
        assert p is not None
        assert p.has_loop is True
        assert "entity.tfidf" in p.operator_chain

    def test_med_has_steiner_tree(self, composer):
        p = composer.get_profile("med")
        assert p is not None
        assert "subgraph.steiner_tree" in p.operator_chain

    def test_every_profile_has_guidance(self, composer):
        for p in composer.get_method_profiles():
            assert p.good_for, f"Method {p.name} missing good_for guidance"

    def test_every_profile_has_cost_tier(self, composer):
        valid_tiers = {"free", "cheap", "moderate", "expensive"}
        for p in composer.get_method_profiles():
            assert p.cost_tier in valid_tiers, f"Method {p.name} has invalid cost tier: {p.cost_tier}"


class TestPlanBuilding:

    def test_build_basic_local_plan(self, composer):
        plan = composer.build_plan("basic_local", "What is X?")
        assert plan is not None
        assert plan.plan_inputs["query"] == "What is X?"
        assert len(plan.steps) >= 3

    def test_build_plan_with_dataset_kwarg(self, composer):
        plan = composer.build_plan("basic_local", "test", dataset="my_dataset")
        assert plan.target_dataset_name == "my_dataset"

    def test_unknown_method_raises(self, composer):
        with pytest.raises(ValueError, match="Unknown method"):
            composer.build_plan("nonexistent_method", "test")

    def test_return_context_only_strips_generate_answer(self, composer):
        """Methods ending with meta.generate_answer should have it stripped."""
        # basic_local doesn't end with generate_answer, but dalk does
        plan_full = composer.build_plan("dalk", "What is X?")
        plan_context = composer.build_plan("dalk", "What is X?", return_context_only=True)
        assert len(plan_context.steps) < len(plan_full.steps)

        # Verify the full plan's last step has generate_answer
        from Core.AgentSchema.plan import DynamicToolChainConfig
        last_step_full = plan_full.steps[-1]
        assert isinstance(last_step_full.action, DynamicToolChainConfig)
        assert last_step_full.action.tools[-1].tool_id == "meta.generate_answer"

        # Verify the context plan's last step does NOT have generate_answer
        last_step_ctx = plan_context.steps[-1]
        if isinstance(last_step_ctx.action, DynamicToolChainConfig):
            assert last_step_ctx.action.tools[-1].tool_id != "meta.generate_answer"

    def test_return_context_only_noop_when_no_generate_answer(self, composer):
        """Methods without generate_answer at end should be unchanged."""
        # basic_local doesn't end with generate_answer
        plan_full = composer.build_plan("basic_local", "test")
        plan_ctx = composer.build_plan("basic_local", "test", return_context_only=True)
        assert len(plan_full.steps) == len(plan_ctx.steps)


class TestPlanValidation:

    def test_all_methods_produce_valid_plans(self, composer):
        """Every method plan should pass ChainValidator."""
        from Core.Methods import METHOD_PLANS

        for name in METHOD_PLANS:
            plan = composer.build_plan(name, f"Test query for {name}")
            is_valid = composer.validate_plan(plan)
            assert is_valid, f"Method {name} produced invalid plan"

    def test_validation_with_return_context_only(self, composer):
        """Context-only plans should also validate."""
        from Core.Methods import METHOD_PLANS

        for name in METHOD_PLANS:
            plan = composer.build_plan(name, f"Test query for {name}", return_context_only=True)
            is_valid = composer.validate_plan(plan)
            assert is_valid, f"Method {name} (context_only) produced invalid plan"
