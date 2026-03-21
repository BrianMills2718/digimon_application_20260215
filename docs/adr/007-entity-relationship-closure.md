# ADR-007: Require Entity-Relationship Closure in Extraction Output

**Status**: Accepted
**Date**: 2026-03-21

## Context

Plan #5 improved structural extraction quality enough to expose a more specific
graph-truth problem:

- named values such as `Silver Ball` could still appear only as relationship
  endpoints
- the parser could therefore build a relationship whose source or target had no
  corresponding entity record in the same extraction output
- downstream graph retrieval cannot honestly expose such a node if the build
  never materialized it as an entity

This ambiguity showed up clearly in the short grounded-entity prompt-eval
smoke fixture and then again in the live 10-chunk MuSiQue smoke slice. Without
an explicit contract, DIGIMON would either:

- accept structurally incomplete relationships and build an untruthful graph, or
- keep debating whether missing endpoint nodes are a prompt quirk or a parser
  concern

## Decision

Treat entity/relationship closure as part of the extraction contract.

This means:

1. Every relationship endpoint must also appear as an entity record in the same
   extraction output.
2. If a relationship references a source or target with no entity record, the
   relationship is invalid and must be rejected before graph persistence.
3. Prompt iteration must score closure explicitly, not just tuple shape.
4. Prompt improvements should still aim to recover useful named endpoints as
   entity records, but parser/runtime behavior must fail closed until that
   happens.

## Consequences

### Positive

- DIGIMON no longer persists relationships that refer to implicit/nonexistent
  graph nodes.
- Prompt-eval and live builds now measure the same closure rule.
- Retrieval operators can trust that persisted edges connect materialized nodes.

### Negative

- Some useful-seeming relationships will now be dropped until prompt quality
  improves.
- Artifact edge counts can fall sharply on real-corpus smoke slices.

### Constraints

- Do not silently synthesize missing endpoint entity records inside the parser.
- Do not weaken closure just to preserve edge counts for benchmark smoke runs.
- Treat residual missing-endpoint behavior as a prompt/completeness problem, not
  as permission to persist incomplete graph structure.
