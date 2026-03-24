# ADR-015: Strategic Risks for Thesis Test — Relocated

**Status**: Superseded
**Date**: 2026-03-23

## Context

Originally recorded strategic risks and open questions as an ADR. Per Pattern 29 (Uncertainty Tracking), concerns and risks belong in plan files as tracked uncertainties, not as ADRs. ADRs are for architectural *decisions*.

## Decision

Relocated all strategic risks and open questions to `docs/plans/17_retest_thesis.md` under the "Open Questions" section, using the Pattern 29 format (status lifecycle, context, resolution/mitigation).

Off-the-shelf alternatives assessment retained here as an architectural reference:

| Area | DIGIMON | Alternative | Assessment |
|------|---------|-------------|------------|
| Graph construction | Custom extraction pipeline | Microsoft GraphRAG, HippoRAG OSS | Composable operator model is the differentiator. Extraction backend swappable but operator routing is custom by design. |
| VDB indexing | FAISS directly | ChromaDB, Qdrant | FAISS fine for current scale. |
| Benchmark eval | Custom EM/F1/LLM-judge | RAGAS, DeepEval | Consider for publishable results. |
| Question decomposition | Single-shot operator | IRCoT, StepChain | Consolidated prompt enables iterative retry. Dedicated loop can be added later. |
| PPR | igraph via BaseGraph | HippoRAG's PPR | Same algorithm. No need to switch. |

## Consequences

Uncertainties are now tracked where they'll be seen during execution (in the plan), not in a separate ADR that agents might miss.
