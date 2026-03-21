# ADR-006: Decide Open-TKG Grounded Entity Policy with Frozen Prompt-Eval Cases

**Status**: Accepted
**Date**: 2026-03-21

## Context

Plan #5 has already improved extraction quality in two important ways:

- malformed slot assignments are now rejected more reliably
- anaphoric placeholders such as `his` are filtered before graph persistence

But the latest real-corpus smoke artifacts still expose a different ambiguity:

- low-value abstractions such as `form` can still survive open `TKG` extraction
- named awards and competitions such as `Silver Ball` or `Copa del Rey` must
  remain extractable

This creates a recurring design risk. If DIGIMON reacts with an ad hoc stoplist
of benchmark-specific nouns, the build will become less truthful and less
reusable across GraphRAG methods. If DIGIMON does nothing, open `TKG`
extraction remains too noisy for meaningful graph-quality claims.

The missing decision is not just "write a stricter prompt." It is:

- what counts as a groundable entity in open `TKG` extraction
- how that policy should be proven before it becomes a deterministic validator

## Decision

Treat the open-`TKG` grounded-entity policy as a prompt-and-eval contract
before turning it into a hard validator.

This means:

1. DIGIMON must evaluate abstraction-suppression prompt changes on a frozen case
   set that includes both:
   - low-value abstractions that should probably be dropped
   - legitimate borderline entities such as named awards or competitions that
     must still be kept
2. `prompt_eval` is the required surface for this comparison; manual spot checks
   are not sufficient evidence.
3. DIGIMON must not add a benchmark-specific stoplist as the first solution.
4. Only after a prompt variant shows the intended keep/drop behavior on frozen
   cases should the policy be encoded in deterministic extraction validation.

## Consequences

### Positive

- DIGIMON can improve entity quality without hiding the tradeoff between recall
  and over-pruning.
- The policy becomes reproducible and reviewable instead of living in ad hoc
  prompt edits.
- Named awards, competitions, and similarly groundable entities get explicit
  protection during prompt iteration.

### Negative

- This adds one more prompt-eval slice before the next deterministic validator
  change.
- The 10-chunk smoke rebuild remains blocked on a clean abstraction policy.

### Constraints

- Do not use a benchmark-only noun blacklist as the primary solution.
- Do not confuse this with the Unicode/canonical-identity problem; that remains
  part of Plan #4.
- Keep the first proof focused on the existing MuSiQue extraction slice and its
  frozen prompt-eval cases.
