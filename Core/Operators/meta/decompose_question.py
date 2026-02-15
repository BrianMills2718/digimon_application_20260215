"""Meta: LLM question decomposition operator (AoT-style).

Decomposes a complex multi-hop question into independent sub-questions
that can each be answered via separate retrieval chains.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from Core.Common.Logger import logger
from Core.Schema.SlotTypes import EntityRecord, SlotKind, SlotValue


async def meta_decompose_question(
    inputs: Dict[str, SlotValue],
    ctx: Any,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, SlotValue]:
    """Decompose a complex question into independent sub-questions.

    Inputs:  {"query": SlotValue(QUERY_TEXT)}
    Outputs: {"sub_questions": SlotValue(ENTITY_SET)}
    Params:  {"max_questions": int (default 5)}
    """
    query = inputs["query"].data
    p = params or {}
    max_questions = p.get("max_questions", 5)

    try:
        prompt = (
            "You decompose complex questions into independent sub-questions.\n\n"
            f"Question: {query}\n\n"
            f"Break this into up to {max_questions} focused, independent sub-questions "
            "that together answer the original question. "
            "Return a JSON array of strings.\n\n"
            "Sub-questions (JSON array):"
        )
        result = await ctx.llm.aask(msg=[{"role": "user", "content": prompt}])

        # Parse JSON array from response
        match = re.search(r"\[.*?\]", result, re.DOTALL)
        if match:
            sub_qs = json.loads(match.group())
        else:
            sub_qs = [q.strip().strip('"').strip("'") for q in result.split("\n") if q.strip()]

        # Reuse EntityRecord: entity_name holds the sub-question text
        records = [
            EntityRecord(entity_name=q, entity_type="sub_question", score=1.0)
            for q in sub_qs[:max_questions]
            if q.strip()
        ]

        logger.info(f"meta_decompose_question: {len(records)} sub-questions from query")
        return {"sub_questions": SlotValue(kind=SlotKind.ENTITY_SET, data=records, producer="meta.decompose_question")}

    except Exception as e:
        logger.exception(f"meta_decompose_question failed: {e}")
        return {"sub_questions": SlotValue(kind=SlotKind.ENTITY_SET, data=[], producer="meta.decompose_question")}
