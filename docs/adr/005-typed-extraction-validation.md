# ADR-005: Add Typed Validation to Entity-Graph Extraction Records

**Status**: Accepted
**Date**: 2026-03-21

## Context

The graph-build rearchitecture already established that DIGIMON should treat
the entity-graph family as an explicit, reproducible build contract rather than
as a loose collection of ad hoc graph artifacts.

The first real-corpus proof of that architecture succeeded operationally:

- `MuSiQue_TKG_smoke` rebuilt into an isolated artifact namespace
- manifest provenance stayed truthful
- the artifact stayed free of empty and one-character junk node IDs

But the same run also showed that the current extraction layer is still too
loose for TKG-quality claims:

- some records have malformed relationship slot assignments
- some extracted entities still carry null or weak types
- the current delimiter tuple is effectively the only record contract, which
  makes malformed records too easy to accept

This is a recurring design ambiguity: is the build contract the persisted graph
only, or does it also include the extracted record semantics that feed it?

## Decision

Treat typed extraction-record validation as part of the canonical entity-graph
build contract.

This means:

1. Entity and relationship records must have explicit typed semantics before
   graph persistence.
2. `TKG` and `RKG` profiles must be able to reject null/placeholder typing when
   typed entities are part of the contract.
3. Malformed relationship slot assignments must fail loudly instead of being
   silently accepted as graph edges.
4. Profile/schema guidance must influence extraction validation, not just prompt
   text.

The current delimiter text format may remain as a transport/parsing format for a
short transition, but it is no longer the canonical contract by itself.

## Consequences

### Positive

- DIGIMON’s graph builds become more truthful to JayLZhou-style `TKG`/`RKG`
  profile claims.
- Real-corpus smoke builds become better indicators of graph quality.
- Known-bad extraction failures can be locked into deterministic tests.

### Negative

- Some previously accepted extracted records will now be rejected, which may
  reduce graph size until prompt/schema quality improves.
- The extraction path will need more explicit validation and observability.
- This increases short-term implementation work before benchmark reruns.

### Constraints

- Do not expand this slice into retrieval changes or benchmark prompt changes.
- Do not add new few-shot prompt examples without user approval.
- Keep the first proof focused on the existing 10-chunk `MuSiQue_TKG_smoke`
  slice.
