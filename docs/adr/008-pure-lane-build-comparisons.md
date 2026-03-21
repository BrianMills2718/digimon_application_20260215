# ADR-008: Require Pure-Lane Extraction for Decision-Grade Build Comparisons

**Status**: Accepted
**Date**: 2026-03-21

## Context

Plan #5 introduced closure-aware live smoke builds to compare extraction-policy
variants on the same 10-chunk MuSiQue slice. The first pair of live artifacts
looked useful, but they were methodologically confounded:

- `MuSiQue_TKG_smoke_closure` fell back from Gemini to DeepSeek mid-build
- `MuSiQue_TKG_smoke_closure_grounded` also fell back after a provider policy
  block
- the manifest did not yet preserve a runtime snapshot that could prove which
  model lane actually produced the artifact

That meant DIGIMON could not tell whether the grounded/non-grounded difference
came from prompt policy, model/provider mixing, or both. This is unacceptable
for a system that is supposed to reproduce and compare GraphRAG methods
truthfully.

## Decision

Treat no-fallback extraction as the required path for any decision-grade live
graph-build comparison.

This means:

1. Evaluation-oriented graph builds must support a dedicated pure-lane LLM path
   instead of silently sharing the server's reliability/fallback policy.
2. The graph-build manifest must record the build runtime lane, including the
   primary model and any fallback models.
3. Live artifact comparisons that are meant to justify prompt/build decisions
   must run with `lane_policy=pure`.
4. Mixed-lane builds remain allowed for exploratory debugging, but they must be
   called out explicitly as non-final evidence.

## Consequences

### Positive

- Prompt/build comparisons can now isolate prompt policy changes from
  provider-fallback effects.
- Every artifact can declare whether it is decision-grade or exploratory based
  on manifest truth rather than memory.
- DIGIMON's methodology becomes closer to a controlled GraphRAG lab instead of
  an ad hoc collection of live runs.

### Negative

- Pure-lane builds can fail more often when the chosen provider is unstable or
  rate-limited.
- Some exploratory runs that previously succeeded through fallbacks will now
  fail loudly when used in decision mode.

### Constraints

- Do not silently downgrade a pure-lane build into a fallback-enabled run.
- Do not treat mixed-lane artifacts as decision-grade even if they look better.
- Keep build-lane truth in the persisted manifest, not only in console logs.
