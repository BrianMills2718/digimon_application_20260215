# Core/Composition

This subtree contains execution-plan validation and pipeline execution logic for
DIGIMON operator chains.

## Working Rules

- Preserve fail-loud validation of operator I/O compatibility.
- Composition helpers should make chain semantics more explicit, not more
  magical.
