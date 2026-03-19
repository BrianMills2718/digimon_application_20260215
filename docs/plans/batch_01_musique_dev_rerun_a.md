# Batch 01 Rerun A: MuSiQue Dev Iteration

Use this record for the first rerun of `batch_01_musique_dev.md` after targeted changes.

Reference files:
- `docs/plans/batch_01_musique_dev.md`
- `docs/plans/BATCH_ITERATION_TEMPLATE.md`

Important:
- Preserve the original batch record unchanged.
- Use this rerun only for validating a small number of targeted fixes.
- Record exactly what changed between the original batch and this rerun.

---

## Rerun Metadata

- **Rerun ID:** `batch_01_rerun_a`
- **Base Batch:** `batch_01`
- **Date:** `2026-03-18`
- **Owner:** `Brian`
- **Dataset:** `MuSiQue`
- **Question IDs File:** `results/iterative/batch_01/batch_ids.txt`
- **Question Set Changed:** `no`
- **Reason for Rerun:**

## Frozen Run Configuration

- **Answer Model:**
- **Judge Model:**
- **Timeout Policy:**
- **Retry Policy:**
- **Prompt Versions:**
- **Tool Surface Versions:**
- **Scoring Script / Command:**

## Modes Re-Run

- [ ] `baseline`
- [ ] `fixed_graph`
- [ ] `adaptive`

## Changes Since Base Batch

Limit to the specific fixes being validated.

| change_id | file | reason | expected_effect | failure_class_targeted |
|-----------|------|--------|-----------------|------------------------|
| C1 | | | | |
| C2 | | | | |
| C3 | | | | |

## Run Commands

```bash
# baseline
python eval/run_agent_benchmark.py \
  --dataset MuSiQue \
  --questions-file results/iterative/batch_01/batch_ids.txt \
  --mode baseline \
  ...

# fixed_graph
python eval/run_agent_benchmark.py \
  --dataset MuSiQue \
  --questions-file results/iterative/batch_01/batch_ids.txt \
  --mode fixed_graph \
  ...

# adaptive
python eval/run_agent_benchmark.py \
  --dataset MuSiQue \
  --questions-file results/iterative/batch_01/batch_ids.txt \
  --mode hybrid \
  ...
```

---

## Per-Question Results

| question_id | hop_count | mode | correct | completion_status | predicted_answer | gold_answer | tools_used | latency_s | cost_usd | failure_class | notes |
|-------------|-----------|------|---------|-------------------|------------------|-------------|------------|-----------|----------|---------------|-------|
|             |           |      |         |                   |                  |             |            |           |          |               |       |

---

## Comparison vs Base Batch

| mode | metric | base_batch | rerun_a | delta |
|------|--------|------------|---------|-------|
| baseline | EM | | | |
| baseline | LLM_EM | | | |
| fixed_graph | EM | | | |
| fixed_graph | LLM_EM | | | |
| adaptive | EM | | | |
| adaptive | LLM_EM | | | |

## Failure-Class Delta

| failure_class | base_count | rerun_count | delta | comments |
|---------------|------------|-------------|-------|----------|
|               |            |             |       |          |

## Questions Fixed

- 

## Regressions Introduced

- 

## Top Observations

1. 
2. 
3. 

---

## Decision After Rerun

- [ ] Keep the changes
- [ ] Revert the changes
- [ ] Escalate to a new dev batch
- [ ] Freeze and move to locked eval

## Notes

- This rerun is still development evidence, not final benchmark evidence.
- If gains are small or noisy, stop rerunning the same batch and move to a new batch or a frozen evaluation.
