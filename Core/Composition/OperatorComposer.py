"""OperatorComposer — method profiling, plan building, and execution.

Lightweight helper that:
1. Profiles all 10 method plans (operator chains, requirements, cost tiers)
2. Instantiates method plans with query and parameters
3. Validates and executes plans through PipelineExecutor

No LLM selection logic. The calling agent decides which method to use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Core.Common.Logger import logger
from Core.Schema.OperatorDescriptor import CostTier


@dataclass
class MethodProfile:
    """Machine-readable profile of a retrieval method."""

    name: str
    description: str
    operator_chain: List[str]
    requires_entity_vdb: bool
    requires_relationship_vdb: bool
    requires_community: bool
    requires_sparse_matrices: bool
    cost_tier: str
    has_loop: bool
    uses_llm_operators: bool
    good_for: str


# Cost tier ordering for max() calculation
_COST_ORDER = {
    CostTier.FREE: 0,
    CostTier.CHEAP: 1,
    CostTier.MODERATE: 2,
    CostTier.EXPENSIVE: 3,
}

# Human-readable guidance per method
_METHOD_GUIDANCE = {
    "basic_local": "Simple local retrieval. Best for straightforward factual questions with a well-built entity VDB.",
    "basic_global": "Global community-based retrieval. Best for broad/thematic questions requiring high-level summaries.",
    "lightrag": "Keyword-enriched relationship retrieval. Best when relationships carry rich descriptions and keywords.",
    "fastgraphrag": "PPR-based score propagation. Best for multi-hop questions where graph topology matters.",
    "hipporag": "LLM entity extraction + PPR. Best when query entities aren't in the VDB vocabulary.",
    "tog": "Iterative LLM-guided graph exploration. Best for complex multi-hop reasoning requiring depth.",
    "gr": "PCST subgraph optimization. Best for finding compact, informative subgraphs from dual VDB search.",
    "dalk": "Entity linking + path filtering. Best for questions requiring specific knowledge paths.",
    "kgp": "TF-IDF + iterative neighbor reasoning. Best when entity descriptions are rich text.",
    "med": "Subgraph extraction with Steiner tree. Best for domain-specific (medical) connected subgraph queries.",
}


class OperatorComposer:
    """Profiles method plans and executes them through the operator pipeline."""

    def __init__(self, registry):
        self.registry = registry
        self.profiles: Dict[str, MethodProfile] = self._build_profiles()

    def _build_profiles(self) -> Dict[str, MethodProfile]:
        """Walk each METHOD_PLAN to extract operator chains and requirements."""
        from Core.Methods import METHOD_PLANS
        from Core.AgentSchema.plan import DynamicToolChainConfig, LoopConfig

        profiles = {}
        for name, plan_fn in METHOD_PLANS.items():
            # Build a dummy plan to inspect structure
            plan = plan_fn(query="<profile_query>")

            operator_chain = []
            has_loop = False
            requires_entity_vdb = False
            requires_relationship_vdb = False
            requires_community = False
            requires_sparse_matrices = False
            uses_llm = False
            max_cost = CostTier.FREE

            for step in plan.steps:
                if isinstance(step.action, DynamicToolChainConfig):
                    for tool_call in step.action.tools:
                        op_id = tool_call.tool_id
                        operator_chain.append(op_id)
                        desc = self.registry.get(op_id)
                        if desc:
                            if desc.requires_entity_vdb:
                                requires_entity_vdb = True
                            if desc.requires_relationship_vdb:
                                requires_relationship_vdb = True
                            if desc.requires_community:
                                requires_community = True
                            if desc.requires_sparse_matrices:
                                requires_sparse_matrices = True
                            if desc.requires_llm:
                                uses_llm = True
                            if _COST_ORDER.get(desc.cost_tier, 0) > _COST_ORDER.get(max_cost, 0):
                                max_cost = desc.cost_tier
                elif isinstance(step.action, LoopConfig):
                    has_loop = True
                    # Walk body steps to find operators referenced in loop
                    for body_id in step.action.body_step_ids:
                        body_step = next(
                            (s for s in plan.steps if s.step_id == body_id), None
                        )
                        if body_step and isinstance(body_step.action, DynamicToolChainConfig):
                            for tool_call in body_step.action.tools:
                                op_id = tool_call.tool_id
                                if op_id not in operator_chain:
                                    operator_chain.append(op_id)
                                desc = self.registry.get(op_id)
                                if desc:
                                    if desc.requires_llm:
                                        uses_llm = True
                                    if _COST_ORDER.get(desc.cost_tier, 0) > _COST_ORDER.get(max_cost, 0):
                                        max_cost = desc.cost_tier

            profiles[name] = MethodProfile(
                name=name,
                description=plan.plan_description,
                operator_chain=operator_chain,
                requires_entity_vdb=requires_entity_vdb,
                requires_relationship_vdb=requires_relationship_vdb,
                requires_community=requires_community,
                requires_sparse_matrices=requires_sparse_matrices,
                cost_tier=max_cost.value,
                has_loop=has_loop,
                uses_llm_operators=uses_llm,
                good_for=_METHOD_GUIDANCE.get(name, ""),
            )

        return profiles

    def get_method_profiles(self) -> List[MethodProfile]:
        """All method profiles with rich metadata."""
        return list(self.profiles.values())

    def get_profile(self, method_name: str) -> Optional[MethodProfile]:
        return self.profiles.get(method_name)

    def build_plan(
        self,
        method_name: str,
        query: str,
        return_context_only: bool = False,
        **kwargs: Any,
    ):
        """Instantiate a named method plan.

        If return_context_only=True, strips the final meta.generate_answer step
        so the calling agent can synthesize the answer itself.

        Args:
            method_name: One of the 10 method names
            query: The question to answer
            return_context_only: If True, omit answer generation
            **kwargs: Passed to the method plan factory (e.g. dataset, depth, k_hop)

        Returns:
            ExecutionPlan ready for validation and execution
        """
        from Core.Methods import METHOD_PLANS
        from Core.AgentSchema.plan import DynamicToolChainConfig

        if method_name not in METHOD_PLANS:
            raise ValueError(
                f"Unknown method: {method_name}. "
                f"Available: {sorted(METHOD_PLANS.keys())}"
            )

        plan = METHOD_PLANS[method_name](query=query, **kwargs)

        if return_context_only:
            # Remove the last step if it's meta.generate_answer
            if plan.steps:
                last_step = plan.steps[-1]
                if isinstance(last_step.action, DynamicToolChainConfig):
                    last_tools = last_step.action.tools
                    if last_tools and last_tools[-1].tool_id == "meta.generate_answer":
                        plan.steps = plan.steps[:-1]

        return plan

    def validate_plan(self, plan) -> bool:
        """Validate plan with ChainValidator. Returns True if valid."""
        from Core.Composition.ChainValidator import ChainValidator
        from Core.Schema.SlotTypes import SlotKind

        validator = ChainValidator(self.registry)
        result = validator.validate(plan, plan_input_kinds={SlotKind.QUERY_TEXT})

        if not result.valid:
            for error in result.errors:
                logger.warning(
                    f"Validation error in {error.step_id}/{error.tool_id}: {error.message}"
                )
        for warning in result.warnings:
            logger.debug(f"Validation warning: {warning}")

        return result.valid

    async def execute(self, plan, ctx) -> Dict[str, Any]:
        """Validate plan, run through PipelineExecutor, format output.

        Args:
            plan: ExecutionPlan from build_plan()
            ctx: OperatorContext with graph, VDB, LLM, etc.

        Returns:
            Dict with step outputs. Final step's outputs are the result.
        """
        from Core.Composition.PipelineExecutor import PipelineExecutor

        # Validate first
        is_valid = self.validate_plan(plan)
        if not is_valid:
            logger.warning("Plan has validation errors — executing anyway (best effort)")

        executor = PipelineExecutor(self.registry, ctx)
        step_outputs = await executor.execute(plan)

        # Extract the final step's output as the primary result
        result = {
            "all_step_outputs": {},
            "final_output": {},
        }

        for step_id, outputs in step_outputs.items():
            step_data = {}
            for slot_name, slot_val in outputs.items():
                if hasattr(slot_val, "data"):
                    step_data[slot_name] = slot_val.data
                else:
                    step_data[slot_name] = slot_val
            result["all_step_outputs"][step_id] = step_data

        # The last step's output is the primary result
        if step_outputs:
            last_step_id = list(step_outputs.keys())[-1]
            last_outputs = step_outputs[last_step_id]
            for slot_name, slot_val in last_outputs.items():
                if hasattr(slot_val, "data"):
                    result["final_output"][slot_name] = slot_val.data
                else:
                    result["final_output"][slot_name] = slot_val

        return result
