"""auto_compose — LLM-driven method selection for DIGIMON queries.

Given a query, dataset, and available resources, an LLM picks the best
retrieval method from the 10 named methods. This removes the requirement
for the calling agent to understand operator descriptors or method names.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from Core.Composition.OperatorComposer import OperatorComposer

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "auto_compose.yaml"

# Canonical method names (kept in sync with METHOD_PLANS)
_VALID_METHODS = {
    "basic_local", "basic_global", "lightrag", "fastgraphrag",
    "hipporag", "tog", "gr", "dalk", "kgp", "med",
}

_FALLBACK_METHOD = "basic_local"


class CompositionDecision(BaseModel):
    """LLM's method selection decision."""

    method_name: str = Field(description="One of the 10 retrieval method names")
    reasoning: str = Field(description="Why this method fits the query")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the selection")


async def select_method(
    query: str,
    dataset_name: str,
    composer: OperatorComposer,
    model: str,
    resources: str,
    auto_build: bool = True,
    trace_id: str = "",
) -> CompositionDecision:
    """Use an LLM to select the best retrieval method for a query.

    Args:
        query: The user's question
        dataset_name: Name of the target dataset
        composer: OperatorComposer instance (for get_method_profiles())
        model: LLM model identifier (e.g. "gemini/gemini-2.0-flash")
        resources: JSON string from list_available_resources()
        auto_build: Whether auto_build will be available for prerequisites
        trace_id: Trace ID for correlating LLM calls

    Returns:
        CompositionDecision with method_name, reasoning, and confidence.
        Falls back to basic_local on any failure.
    """
    from llm_client import render_prompt, acall_llm_structured

    profiles = composer.get_method_profiles()
    profile_dicts = [asdict(p) for p in profiles]

    try:
        messages = render_prompt(
            str(_PROMPT_PATH),
            methods=profile_dicts,
            dataset_name=dataset_name,
            resources=resources,
            query=query,
            auto_build=auto_build,
        )
    except Exception as e:
        logger.error(f"auto_compose: prompt render failed: {e}")
        return _fallback(f"Prompt render error: {e}")

    try:
        decision, meta = await acall_llm_structured(
            model,
            messages,
            response_model=CompositionDecision,
            task="digimon.auto_compose",
            trace_id=trace_id,
        )
        logger.info(
            f"auto_compose: LLM selected '{decision.method_name}' "
            f"(confidence={decision.confidence:.2f}, cost=${meta.cost:.4f})"
        )
    except Exception as e:
        logger.error(f"auto_compose: LLM call failed: {e}")
        return _fallback(f"LLM call error: {e}")

    # Validate the chosen method
    if decision.method_name not in _VALID_METHODS:
        logger.warning(
            f"auto_compose: LLM returned invalid method '{decision.method_name}', "
            f"falling back to {_FALLBACK_METHOD}"
        )
        return CompositionDecision(
            method_name=_FALLBACK_METHOD,
            reasoning=f"LLM suggested '{decision.method_name}' which is not a valid method. "
            f"Falling back to {_FALLBACK_METHOD}.",
            confidence=0.3,
        )

    return decision


def _fallback(reason: str) -> CompositionDecision:
    """Return a safe fallback decision."""
    return CompositionDecision(
        method_name=_FALLBACK_METHOD,
        reasoning=f"Fallback to {_FALLBACK_METHOD}: {reason}",
        confidence=0.1,
    )
