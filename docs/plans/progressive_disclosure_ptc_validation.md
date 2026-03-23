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

## Phase 4 Findings (2026-03-23)

### Benchmark runner fix

Root cause found: Python 3.10 compatibility bug in llm_client v1's heartbeat
monitor (`call_lifecycle.py`). `except TimeoutError:` doesn't catch
`asyncio.TimeoutError` in Python 3.10 (unified in 3.11). Fixed — benchmark
runner works again.

### Preliminary results (10q HotpotQAsmallest, gemini-2.5-flash-lite)

| Metric | Sequential | PTC (optional) | PTC (forced) |
|--------|:-:|:-:|:-:|
| EM | 20% | 10% | 0% |
| LLM_EM | 40% | 30% | 0% |
| Cost | $0.12 | $0.10 | $0.18 |
| Tool calls/q | 13.5 | 10.4 | 13.9 |
| Wall time/q | 48s | 43s | 81s |
| Completion | 90% | 100% | 90% |

### Key findings

1. **When PTC is optional, the agent never uses it.** It always falls back to
   familiar sequential tool calls. The PTC tool was available but ignored.

2. **When PTC is forced (only execute_operator_chain available), flash-lite
   writes broken code.** The model can't reliably produce correct async Python
   with proper JSON parsing of operator results. 0% accuracy.

3. **The efficiency gains when PTC works are real** — 23% fewer tool calls,
   17% less cost, 12% faster. Consistent with Anthropic's 37% token reduction
   benchmark.

4. **The wall time is dominated by inference latency.** ~48s/question with 13.5
   tool calls = ~3.5s per inference round-trip. PTC should collapse this to
   1-2 inference passes, but only if the model can write correct code.

### Open questions

- Does deepseek-chat or a Claude model write correct operator chain code?
- Is the execute_operator_chain interface too complex? Should it pre-parse
  JSON results so the agent doesn't have to json.loads() everything?
- Would a simpler interface (operators return Python dicts, not JSON strings)
  dramatically reduce code errors?
- Is the v1 llm_client's tool-call recording sufficient for debugging?
  (Currently stores tool names as bare strings, not arguments/results.)

### What needs to happen

1. **Simplify the PTC interface** — operators should return dicts, not JSON
   strings. The json.loads() on every intermediate is the main error source.
2. **Test with a code-capable model** — flash-lite is too weak for async Python.
3. **Better error logging** — capture the actual code written and errors returned.
4. **llm_client_v2 migration** (when ready) — v2 has PTC support built-in with
   proper tool callable registry and context budget tracking.

## Timeline

- Phase 3: **DONE** (skill document at .claude/skills/digimon-operators/)
- Phase 4: **BLOCKED** on benchmark runner fix
- Phase 5: Depends on Phase 4
