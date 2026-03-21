# ADR-009: Prefer Two-Pass Extraction if One-Pass Completeness Remains Unstable

**Status**: Accepted
**Date**: 2026-03-21

## Context

Plan #5 has now isolated a narrower extraction-quality problem:

- one-pass grounded prompting can suppress broad category labels on focused
  cases
- one-pass prompting still struggles to materialize some named relationship
  endpoints such as `throat cancer` and `Silver Ball` as entity records
- an explicit prompt-only attempt to force endpoint completeness regressed on
  the same six-case fixture, causing a truncated response on a short case and
  malformed tuples on another

ADR-007 already rejects any relationship whose endpoints do not also appear as
entity records. That means DIGIMON now has truthful closure semantics, but it
does not yet have a stable way to achieve entity completeness inside one-pass
extraction.

## Decision

Prefer a two-pass extraction architecture over piling more instructions into the
one-pass prompt.

Proposed two-pass shape:

1. Pass 1 extracts the grounded entity inventory only.
2. Pass 2 extracts relationships using the pass-1 entity inventory as an
   explicit boundary.
3. Relationship extraction fails loudly if it references an entity outside the
   pass-1 inventory.
4. DIGIMON proves the contract on the existing six-case frozen fixture before
   using it in another live smoke rebuild.

## Consequences

### Positive

- Entity completeness becomes an explicit contract instead of a side effect of
  prompt verbosity.
- Closure rules and prompt-eval cases can test each pass separately.
- DIGIMON gets closer to a controlled GraphRAG lab where build strategies are
  configurable and comparable.

### Negative

- Build latency and LLM cost will increase for entity-graph extraction.
- The extraction path becomes more orchestration-heavy than the current single
  response contract.

### Constraints

- Do not silently synthesize entity records from relationship endpoints.
- Do not keep inflating the one-pass prompt indefinitely once the frozen-case
  evidence says it is unstable.
- Prove the two-pass contract on the same frozen cases before using it in live
  smoke rebuilds.
