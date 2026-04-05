# DIGIMON Handoff Template

Use this when handing DIGIMON work to a fresh agent. The goal is to separate
verified facts from hypotheses so the next loop does not optimize a stale story.

---

## Header

- **Date:**
- **Status:** `draft | truth-audited | superseded`
- **Working branch:** verify with `git status --short --branch`
- **Repo root:**
- **Artifact root:** if different from repo root
- **Active plan(s):**

---

## What DIGIMON Is

- One paragraph on the product thesis
- One paragraph on the active benchmark lane and metric
- Link the exact code/prompt/status files that matter now

---

## Verified Facts

Only include claims backed by code, result JSON, corpus evidence, or traces.

| Claim | Evidence | Confidence | Last verified | Reproduce |
|-------|----------|------------|---------------|-----------|
| | | high/medium/low | YYYY-MM-DD | command |

Rules:
- If you cannot cite evidence, move the statement to `Working Hypotheses`
- If a claim depends on a specific artifact, name the artifact exactly
- If a claim could drift, include the reproduce command

---

## Working Hypotheses

These are explanations, not facts yet.

| Hypothesis | Why it seems plausible | What would confirm it | What would falsify it |
|------------|------------------------|-----------------------|-----------------------|
| | | | |

---

## Current Benchmark State

- Link the exact report file
- State whether it is `fixed-setting` or `mixed-setting`
- Record mean/spread, not just the best run

Required fields:
- run count
- mean metric
- spread metric
- stable pass count
- stochastic count
- stable fail count

---

## Failure Families

Group by general mechanism, not by memorable question name.

| Family | Representative IDs | Evidence | Next smallest test |
|--------|--------------------|----------|--------------------|
| | | | |

Allowed examples:
- `exact_anchor_drift`
- `bridge_displacement`
- `intermediate_entity_error`
- `answer_kind_mismatch`
- `year_disambiguation`

---

## Active Plans

| # | Plan | Status | Why it still matters |
|---|------|--------|----------------------|
| | | | |

---

## Next 24 Hours

Write these as executable phases.

| Phase | Goal | Exact command(s) | Acceptance | Stop condition |
|-------|------|------------------|------------|----------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

Rules:
- Every phase needs an acceptance condition
- Every phase needs an explicit command or script path
- If a decision is deferred, say what evidence is missing

---

## Environment / Portability Concerns

Record anything that can make the next agent misread the repo state:
- missing artifacts in fresh worktrees
- required local config
- broken CLI/conda assumptions
- external service prerequisites

---

## Open Uncertainties

- Flat list only
- If something is uncertain but non-blocking, say the safer default the next
  agent should take
