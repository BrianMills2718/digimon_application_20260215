# Benchmark Promotion Policy

This policy exists to stop DIGIMON from optimizing stale diagnoses or lucky
single-run results.

---

## Core Rules

1. **Artifacts outrank narrative.**
   A result JSON, trace, or corpus chunk beats memory, handoff prose, and plan
   commentary.

2. **Facts and hypotheses must stay separate.**
   If a claim is not backed by evidence, it is not a fact yet.

3. **Mixed-setting history is diagnostic only.**
   It is useful for orientation, not promotion.

4. **No promotion from a single run.**
   A one-off spike is not a baseline.

5. **Every change must map to a failure family.**
   If a proposed fix does not target a general mechanism, do not spend an
   overnight lane on it.

---

## Promotion Ladder

### 1. Deterministic guardrail

Required before any benchmark spend:
- unit or contract tests
- local compile/import check

Examples:
- query rewrite contract
- tool argument compatibility
- validator/report script tests

### 2. Single-ID rerun

Use for:
- the narrowest question that exercises the repaired mechanism

Required output:
- one artifact or trace
- one truthful classification of what changed

Do not promote past this step if:
- behavior did not change
- or the change only works for one id and does not generalize

### 3. Targeted slice

Use:
- 1-4 questions covering the same family or adjacent failure families

Required output:
- short written note on whether the family actually improved

### 4. Fixed-setting 19q baseline

This is the minimum promotion gate for DIGIMON’s current frontier.

Requirements:
- exact same settings
- exact same question file
- three runs
- one generated report with mean/spread and per-question stability

Required commands:
- `make truth-check`
- `make benchmark-report OUTPUT=docs/reports/<name>.md`

### 5. Decision-grade 50q run

Only allowed after the fixed-setting 19q gate clears.

Requirements:
- stable control plane
- active docs already updated from the 19q artifacts
- explicit statement of what thesis is being tested

---

## What Counts As Improvement

Improvement is one of:
- higher fixed-setting mean beyond the prior run-to-run spread
- same mean with materially tighter spread
- same score but remaining misses collapse into fewer, cleaner families

Improvement is **not**:
- one best run
- one recovered question amid broad noise
- a narrative that the latest result “felt better”

---

## Required Artifacts Per Iteration

Every non-trivial benchmark iteration must leave:
- updated `CURRENT_STATUS.md`
- updated active handoff
- generated benchmark report
- truth-check output clean or documented with a precise reason

If the truth-check is red, fix the docs before starting another tuning cycle.

---

## Spend / Pivot Gate

Continue custom DIGIMON controller work only if:
- the active failure family is still controller-related
- the fixed-setting 19q baseline is moving
- the work is not mostly re-implementing commodity GraphRAG infrastructure

Pivot or pause if:
- the same failure families remain after truthful contract repair
- the fixed-setting baseline does not beat noise
- external maintained systems would provide the same value faster
