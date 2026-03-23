# Plan: Validate Progressive Disclosure + PTC, Then Remove Legacy

Status: planned
Date: 2026-03-22

## Purpose

The progressive disclosure and PTC features (commit 0a4c2be) are behind an
env var toggle (`DIGIMON_PROGRESSIVE_DISCLOSURE=1`). This is a transitional
shim. The goal is to prove the new architecture is better across the board,
then make it the default and remove the toggle.

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Benchmark: PTC mode matches or beats sequential on HotpotQA 50q (EM, F1, LLM_EM) | planned |
| 2 | Benchmark: PTC mode matches or beats sequential on MuSiQue 50q | planned |
| 3 | Token usage: PTC uses ≤70% of sequential tokens (37% reduction target from Anthropic research) | planned |
| 4 | Latency: PTC is ≤80% of sequential wall time | planned |
| 5 | Progressive disclosure: agent still discovers and uses all needed tools via search | planned |
| 6 | No regressions: all existing tests pass with progressive disclosure enabled | planned |
| 7 | Legacy removal: env var toggle deleted, progressive disclosure is the only mode | planned |

## Phase 3: Operator Skill Document

Create a skill document that teaches the agent the operator signatures, common
chains, and output-to-input mappings. This is the "800-token trick" — a compact
reference that makes the model 30% more efficient at using operators correctly.

The content already exists in CLAUDE.md's operator composition section. Extract
it into a standalone skill.

**File:** `.claude/skills/digimon-operators/SKILL.md`

**Acceptance:** Agent with skill doc produces correct operator chains on first
attempt more often than agent without it.

## Phase 4: Benchmark Comparison

Run controlled benchmarks comparing three modes:

| Mode | Description | How |
|------|-------------|-----|
| **sequential** | Current default: agent calls tools one at a time | `--backend direct` (existing) |
| **ptc** | Agent writes Python using execute_operator_chain | `--backend direct` with PTC tool available |
| **fixed** | Prescribed chain, no agent composition | existing fixed_graph mode |

### Benchmark protocol

For each mode, run on:
- HotpotQA 50q balanced dev sample
- MuSiQue 50q balanced dev sample

Measure:
- EM, F1, LLM_EM (accuracy)
- Total tokens consumed (efficiency)
- Wall time (latency)
- Cost ($)
- Number of inference passes (for sequential vs PTC)

### What constitutes success

**PTC is the new default if:**
- Accuracy: PTC ≥ sequential on both datasets (within 3% margin)
- Tokens: PTC ≤ 70% of sequential
- No catastrophic failures (no 0% scores on any question type)

**PTC stays optional if:**
- Accuracy: PTC < sequential - 3% on either dataset
- But tokens are still significantly lower

**PTC is reverted if:**
- Accuracy drops >10% on either dataset
- OR agent consistently fails to write valid operator chains

## Phase 5: Legacy Removal

Once Phase 4 criteria are met:

1. Make progressive disclosure the default (no env var needed)
2. Remove the `DIGIMON_PROGRESSIVE_DISCLOSURE` env var check
3. Remove the conditional logic that registers all tools vs deferred
4. The `search_available_tools` tool becomes always-present
5. `execute_operator_chain` becomes the recommended composition method
6. Update CLAUDE.md to remove references to sequential tool calling as primary
7. Update benchmark runner to use PTC as default mode

**If Phase 4 shows PTC is not better:**
- Keep progressive disclosure (token savings are still real)
- Keep execute_operator_chain as optional
- Remove the env var and make disclosure default, PTC opt-in
- Document why sequential is preferred (probably: agent writes bad chains,
  or intermediate reasoning between steps adds value)

## Blocker: Benchmark Runner Cannot Make LLM Calls (2026-03-22)

Phase 4 attempted but blocked. The benchmark runner (`eval/run_agent_benchmark.py`
with `--backend direct`) produces 0 tokens, 0 tool calls, and timeouts on every
question. Tested with both `gemini/gemini-2.5-flash-lite` and `deepseek/deepseek-chat`.

Direct `llm_client.call_llm` works fine — the model responds. The issue is in
the benchmark runner's agent loop, likely related to:
1. The digimon conda env has llm_client v1 installed (from ~/projects/llm_client)
   not v2. The v1 agent loop may have a regression or incompatibility.
2. Previous successful runs (HotpotQA_200, 48/50 completion with deepseek-chat)
   were from 2026-02-17 — something changed since then.

**Next step:** Investigate the benchmark runner's agent loop separately. This is
NOT related to our progressive disclosure or PTC changes (those add tools but
don't change the agent loop). The benchmark was already broken before our changes.

## Timeline

- Phase 3: **DONE** (skill document at .claude/skills/digimon-operators/)
- Phase 4: **BLOCKED** on benchmark runner fix
- Phase 5: Depends on Phase 4
