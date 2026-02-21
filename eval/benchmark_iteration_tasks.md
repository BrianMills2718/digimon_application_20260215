# Overnight Benchmark Iteration Tasks

Date: 2026-02-21
Owner: Codex
Dataset: MuSiQue
Primary metric: `LLM_EM` (with `EM`/`F1` tracked for regression visibility)

## Success Gate

- Gate A (targeted): all current failing IDs pass (`LLM_EM=1`) on failure-only reruns.
- Gate B (full set): `LLM_EM >= 90` on 10-question run with no new validation/control-loop failures.
- Gate C (quality): `n_tool_call_errors = 0` and no parser mis-scoring artifacts.

## Active Task List

1. `DONE` Fix judge parser false-positive (`{"correct": false}` wrapped in fences previously scored as true).
2. `IN_PROGRESS` Re-score latest benchmark artifact with patched parser to establish corrected baseline.
3. `PENDING` Materialize failing-ID set from corrected baseline (`--failure-metric llm_em`).
4. `PENDING` Run failure-only benchmark on gemini-2.5-flash (direct backend).
5. `PENDING` Diagnose top failure modes from traces (reasoning/retrieval/composability/control-loop).
6. `PENDING` Implement one general improvement (no dataset-specific hardcoding).
7. `PENDING` Re-run failure-only set and compare deltas.
8. `PENDING` Commit checkpoint after each meaningful improvement and metric change.
9. `PENDING` Run full 10-question validation every 2 loop cycles or after major architecture change.

## Commit Cadence

- Commit immediately after:
  - parser/infra fixes,
  - each general intelligence improvement,
  - each successful gate advancement.
- Commit message format:
  - `bench: <change> (MuSiQue <metric delta>)`

## Iteration Commands

```bash
# Re-score existing run with patched judge parser
python eval/llm_judge.py results/<run>.json --model openrouter/deepseek/deepseek-chat

# Failure-only rerun (llm_em failures from prior run)
conda run -n digimon python eval/run_agent_benchmark.py \
  --dataset MuSiQue --backend direct --model gemini/gemini-2.5-flash \
  --only-failures-from results/<run>.json \
  --failure-metric llm_em \
  --write-failing-ids results/<next>_failing_ids.txt

# Full 10-question check
conda run -n digimon python eval/run_agent_benchmark.py \
  --dataset MuSiQue --num 10 --backend direct --model gemini/gemini-2.5-flash \
  --post-gate-fail-exit-code
```

## Guardrails

- No benchmark-specific answer hardcoding.
- No prompt state-machine fallback ladders.
- Improvements must be generalizable (reasoning quality, retrieval quality, composability, observability).
