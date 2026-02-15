"""Meta: LLM answer synthesis operator.

Merges sub-answers from parallel retrieval chains into a single
coherent final answer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from Core.Common.Logger import logger
from Core.Schema.SlotTypes import SlotKind, SlotValue


async def meta_synthesize_answers(
    inputs: Dict[str, SlotValue],
    ctx: Any,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, SlotValue]:
    """Synthesize sub-answers into a final coherent answer.

    Inputs:  {"query": SlotValue(QUERY_TEXT), "chunks": SlotValue(CHUNK_SET)}
    Outputs: {"answer": SlotValue(QUERY_TEXT)}
    Params:  {"synthesis_style": str (default "concise")}
    """
    query = inputs["query"].data
    chunks = inputs.get("chunks")
    chunk_data = chunks.data if chunks else []
    p = params or {}
    style = p.get("synthesis_style", "concise")

    sub_answers = [c.text for c in chunk_data if c.text]

    try:
        sub_answer_block = "\n".join(f"- {a}" for a in sub_answers)
        prompt = (
            "You synthesize sub-answers into a single coherent answer.\n\n"
            f"Original question: {query}\n\n"
            f"Sub-answers:\n{sub_answer_block}\n\n"
            f"Synthesize a {style} final answer that directly addresses the original question."
        )
        response = await ctx.llm.aask(msg=[{"role": "user", "content": prompt}])

        logger.info(f"meta_synthesize_answers: synthesized {len(sub_answers)} sub-answers")
        return {"answer": SlotValue(kind=SlotKind.QUERY_TEXT, data=response, producer="meta.synthesize_answers")}

    except Exception as e:
        logger.exception(f"meta_synthesize_answers failed: {e}")
        return {"answer": SlotValue(kind=SlotKind.QUERY_TEXT, data="Failed to synthesize answer.", producer="meta.synthesize_answers")}
