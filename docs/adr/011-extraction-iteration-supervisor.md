# ADR-011: Port the Autoloop Supervisor Skeleton into the Active Repo and Reframe It Around Extraction-Family Gates

**Status**: Accepted
**Date**: 2026-03-22

## Context

DIGIMON needs a real external supervisor if it is going to keep iterating for
long stretches without relying on an interactive chat session to "remember" not
to stop.

An earlier repo, `Digimon_for_KG_application__autoloop`, already solved several
operational problems:

- durable loop state
- JSONL event ledger
- signal-based stop handling
- clean-worktree enforcement
- verified commit-or-revert cycle

But that old loop is optimized for a different DIGIMON stage. Its unit of work
is a failing MuSiQue benchmark question, and its gates are targeted benchmark
reruns plus full-batch benchmark reruns.

Current DIGIMON is on a different critical path:

- extraction-quality iteration is pinned to `gemini/gemini-2.5-flash`
- changes must be judged by failure family, not one-off questions
- `prompt_eval` plus protected sentinels are the required first gate
- small smoke rebuilds are the next gate, before benchmark reruns

Reusing the old autoloop unchanged would optimize the wrong surface. Rewriting
all of its durable mechanics from scratch would duplicate already-proven loop
infrastructure.

## Decision

Port the old autoloop **supervisor skeleton** into the active DIGIMON repo, but
rewrite the **control objective and validation gates** around the current
extraction plans.

### Reuse

Keep these patterns from the old autoloop:

- typed YAML config
- durable session state
- event ledger
- signal stop handling
- clean-worktree enforcement
- revert on failed validation
- commit only after verified improvement

### Replace

Do not reuse these behaviors unchanged:

- failing-question selection
- question-scoped benchmark prompts
- targeted question reruns as the first proof
- full-batch benchmark reruns as the only regression gate

Replace them with:

- failure-family selection
- family-scoped prompt-eval validation
- protected sentinels
- optional smoke-build validation after prompt-eval success

## First Slice

The first implementation slice is intentionally narrow:

1. support one failure family at a time
2. run family-filtered `prompt_eval`
3. invoke a coding agent against that family context
4. rerun the same family gate
5. revert on no improvement, commit on verified improvement

Smoke-build and later benchmark gates are deferred to follow-up slices.

## Consequences

### Positive

- DIGIMON gets an actual long-running external supervisor in the active repo.
- The current extraction-quality path becomes automatable without waiting for a
  later benchmark-only phase.
- Previously proven operational mechanics are reused instead of re-invented.

### Negative

- The first supervisor slice will not yet be a complete 24/7 end-state.
- The current extraction harness needs a small extension so the supervisor can
  target one failure family cleanly.

### Constraints

- Keep decision-grade extraction validation on `gemini/gemini-2.5-flash`.
- Do not let the first supervisor slice silently switch production extraction
  lanes.
- Do not promote benchmark-question reruns back to the first gate while Plan #5
  and Plan #6 remain the critical path.
