# DIGIMON Capability Decomposition

This document is the repo-local capability ownership source of record required
by governed rollout. It is intentionally minimal: it records the current
long-term ownership posture DIGIMON depends on today without reopening the full
ecosystem decomposition design during a bounded tooling-refresh lane.

## Authority

- Shared registry authority: `~/projects/project-meta/scripts/capability_ownership_registry.yaml`
- DIGIMON design source: `docs/plans/25_digimon_capability_decomposition_and_ecosystem_alignment.md`
- Boundary lane: `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md`

If this file and the shared registry ever diverge, the shared registry and the
most recent explicit DIGIMON design plan win. Update this file to match them;
do not silently fork the ownership model inside DIGIMON.

## Capability Ledger

| Capability Family | Current Owner | Intended Long-Term Owner | Class | Posture | Not-Before Gate |
|---|---|---|---|---|---|
| Retrieval-oriented graph projection, operator runtime, and benchmark-facing graph materialization | DIGIMON | DIGIMON | durable-core | keep local | None |
| Local graph identity, namesake handling, and canonicalization logic used to move benchmark failures quickly | DIGIMON | onto-canon6 | transitional-local | move upstream after proof | A bounded `onto-canon6` experiment must match or beat the frozen DIGIMON canonicalization tranche without regressing the maintained benchmark lane |
| Thin v1 flat JSONL interchange seam between `onto-canon6` and DIGIMON | DIGIMON + `onto-canon6` | DIGIMON + `onto-canon6` until superseded | transitional-local | preserve until richer contract exists | Replace only when a richer contract preserves current consumer coverage and rollout cost remains acceptable |

## Current Constraints

- DIGIMON remains the durable owner of the retrieval runtime and projection
  layer.
- DIGIMON may carry benchmark-local canonicalization logic temporarily, but
  that does not redefine the long-term semantic-source-of-truth boundary.
- This document is a governed baseline, not a license to start extraction or
  migration work during benchmark execution.

## Open Uncertainties To Monitor

1. The exact richer successor to the v1 flat JSONL seam is still unsettled.
2. The bounded `onto-canon6` experiment has not yet cleared the gate required
   to move benchmark-local canonicalization upstream.
3. DIGIMON worktree-local governed audits may not always infer shared-registry
   matches as cleanly as canonical-root audits; canonical-root audit remains the
   authority when they disagree.
