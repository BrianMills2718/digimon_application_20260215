# MuSiQue 50q Postmortem

**Date:** 2026-03-19  
**Decision:** One last constrained salvage iteration. Do not run locked eval yet.

## Artifacts Reviewed

- `results/MuSiQue_gemini-2-5-flash_baseline_20260319T033152Z.json`
- `results/MuSiQue_gemini-2-5-flash_fixed_graph_20260319T034919Z.json`
- `results/MuSiQue_gemini-2-5-flash_20260319T040942Z.json`

All three runs are 50-question MuSiQue comparisons with `gemini/gemini-2.5-flash` as the answer model.

## Executive Summary

The current 50q development comparison does **not** support the adaptive-routing thesis.

Results:

| Mode | EM | LLM_EM | F1 | Run Cost | Avg Tools | Avg Latency |
|------|----|--------|----|----------|-----------|-------------|
| baseline | 34.0 | 60.0 | 47.3 | $2.03 | 10.8 | 15.8s |
| fixed_graph | 32.0 | 54.0 | 43.2 | $1.85 | 8.7 | 17.2s |
| hybrid | 32.0 | 44.0 | 43.7 | $5.50 | 11.7 | 48.0s |

Two conclusions are simultaneously true:

1. `fixed_graph` is not currently strong enough to justify graph investment on this sample.
2. `hybrid` is visibly confounded by provider instability in the back half of the run, so this specific run is not a clean decision artifact for adaptive routing.

That combination argues for exactly one narrow salvage pass, not a locked eval and not open-ended tuning.

## Findings

### 1. Baseline wins overall, and most questions are ties

- `baseline` beats both graph modes on 3 questions.
- Graph modes beat `baseline` on 5 questions total.
- 32 of 50 questions are `LLM_EM` ties across all three modes.

Interpretation:
- DIGIMON is not currently getting broad value from graph retrieval on this split.
- The extra graph complexity is paying off only on a handful of questions.

### 2. The current fixed graph pipeline is not a credible `B*`

`fixed_graph` is mixed:

- 2-hop `LLM_EM`: 69.2%
- 3-hop `LLM_EM`: 37.5%
- 4-hop `LLM_EM`: 37.5%

By comparison:

- `baseline` 2-hop: 65.4%
- `baseline` 3-hop: 62.5%
- `baseline` 4-hop: 37.5%

Interpretation:
- The current graph chain can help on some 2-hop entity-resolution questions.
- It is weak on 3-hop questions, which are central to the thesis.
- This looks more like “the fixed chain is too shallow/rigid” than “graph retrieval is proven bad,” but the burden is now on graph to show clear value.

### 3. Hybrid collapses in the second half due to rate-limit fallback

Hybrid split by run segment:

| Segment | LLM_EM | EM | Avg Tools | Avg Latency | Run Cost |
|---------|--------|----|-----------|-------------|----------|
| q1-25 | 60.0 | 44.0 | 13.3 | 55.2s | $1.65 |
| q26-50 | 28.0 | 20.0 | 10.1 | 40.7s | $3.85 |

Back-half confounder signals:

- 24 of the last 25 questions triggered fallback.
- 24 of the last 25 questions show rate-limit warnings.
- The run switched from `gemini/gemini-2.5-flash` to sticky fallback `openrouter/deepseek/deepseek-chat`.

This is the strongest reason **not** to treat the hybrid result as final evidence.

### 4. Even before the confounder, hybrid did not show upside

In q1-25, before the fallback cascade:

- `baseline` `LLM_EM`: 60.0%
- `hybrid` `LLM_EM`: 60.0%

But hybrid was already much more expensive and slower:

- `baseline` q1-25 cost: $0.96
- `hybrid` q1-25 cost: $1.65
- `baseline` q1-25 avg latency: 14.2s
- `hybrid` q1-25 avg latency: 55.2s

Interpretation:
- The pre-confounder evidence does not show adaptive upside.
- At best, hybrid matched baseline while being materially heavier.

### 5. Failure patterns are mostly wrong answers, not loud retrieval failures

Miss pattern summary:

| Mode | Misses | Hallucination-like | Abstention-like | Runtime |
|------|--------|--------------------|-----------------|---------|
| baseline | 20 | 18 | 2 | 0 |
| fixed_graph | 23 | 19 | 3 | 1 |
| hybrid | 28 | 28 | 0 | 0 |

Additional fixed-graph signal:

- 13 questions triggered retrieval stagnation.
- 1 question failed with an empty-content provider error: `2hop__51965_165532`.

Interpretation:
- The main problem is not silent no-hit retrieval.
- The system often produces a plausible but wrong answer from insufficient or misdirected evidence.
- Graph modes are not yet converting extra retrieval structure into better answer discipline.

## Representative Differential Questions

### Baseline beat both graph modes

- `3hop1__41865_55331_34700`
  Gold: `Caesar`
  Baseline: `Caesar`
  Fixed: `French`
  Hybrid: `French Marines, French Army of Châlons, Dutch Republic`

- `3hop2__132957_295815_40768`
  Gold: `1981`
  Baseline: `Early 1980s`
  Fixed: wrong abstention-style answer
  Hybrid: `1980s`

- `3hop1__635099_131926_90707`
  Gold: `at the city of Cairo, Illinois`
  Baseline: `Cairo, Illinois`
  Fixed: `Minneapolis...`
  Hybrid: `The Mississippi River`

These are all 3-hop questions.

### Graph clearly helped

Fixed graph best:

- `2hop__709357_136043` → `Natalie Albino`
- `2hop__77832_159673` → `The Hateful Eight`
- `3hop1__145411_443779_52195` → `Francisco Guterres`

Hybrid best:

- `3hop1__103440_443779_52195` → `Francisco Guterres`
- `3hop1__140855_2053_52946` → `February 7, 2018`

Interpretation:
- Graph retrieval can add value on specific entity-linking and date-chain cases.
- That value is too sparse and inconsistent to justify the current cost/complexity.

## Thesis Failure vs Confounders

### Likely thesis weakness

- Baseline wins overall.
- Fixed graph does not beat baseline even without hybrid’s rate-limit collapse.
- Hybrid shows no first-half quality advantage despite much higher latency/cost.
- 4-hop performance is poor across all modes; graph does not create a visible edge there.

### Likely implementation confounders

- Hybrid second-half collapse is strongly correlated with provider rate limits and sticky fallback.
- Current `fixed_graph` chain is probably not the best fixed graph comparator for 3-hop questions.
- Retrieval stagnation and shallow graph traversal suggest the graph pipeline is under-specified, not merely unlucky.

## Recommendation

**Recommendation:** `one last constrained salvage iteration`

Do **not** run locked eval yet.

### Allowed fixes

1. **Remove the hybrid provider confounder**
- Re-run the same 50q split with a stable answer model/provider.
- Do not allow mixed-model sticky fallback during the comparison run.
- If the provider fails, the run is invalid, not silently converted into a different-model run.

2. **Lock one stronger fixed-graph comparator**
- Replace the current shallow fixed chain with one better candidate aimed at 3-hop questions.
- Keep it deterministic and simple.
- One candidate only. No broad graph-pipeline search.

### Success criteria for the salvage run

The salvage iteration only counts as a success if all of the following hold on the same 50q split:

- `hybrid` beats `baseline` on `LLM_EM`
- `hybrid` beats the locked fixed graph comparator by at least `+3 LLM_EM`
- `hybrid` completes without rate-limit/fallback contamination on more than 5% of questions
- `hybrid` does not exceed `1.5x` baseline cost without a clear quality win

If those conditions are not met, stop adaptive-thesis work and do not run locked eval.

## What Not To Do Next

- Do not run the 200q locked eval now.
- Do not start a broad new tuning cycle.
- Do not add new graph types, memory systems, or agent-intelligence layers.
- Do not keep treating the current `fixed_graph` chain as a credible best-fixed baseline.

## Bottom Line

The current evidence is negative, but not yet clean enough to be the final adaptive-routing verdict because the hybrid run is contaminated by provider fallback after q25.

That said, the pre-confounder evidence is also weak. The right move is one narrow salvage pass. If that does not produce a clear win, stop.
