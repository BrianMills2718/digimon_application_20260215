# Batch 01: MuSiQue Dev Iteration

Use this record for the first 10-20 question MuSiQue development batch.

Reference template: `docs/plans/BATCH_ITERATION_TEMPLATE.md`

Important:
- This batch is for development and failure analysis, not the final benchmark claim.
- Save exact question IDs before running.
- Freeze prompts, tool surface, and scoring rules for the duration of the batch.
- If you rerun after changes, create a follow-up record such as `batch_01_musique_dev_rerun_a.md`.

---

## Batch Metadata

- **Batch ID:** `batch_01`
- **Date:** `2026-03-18`
- **Owner:** `Brian`
- **Dataset:** `MuSiQue`
- **Question Count:** `10-20`
- **Question IDs File:** `results/iterative/batch_01/batch_ids.txt`
- **Seen Before:** `no | mixed | yes`
- **Purpose:** `bug fix | routing tune | baseline check | regression check`

## Split Record

- **Sampling Method:** `balanced`
- **Seed:**
- **Hop Mix:** `2-hop: _ | 3-hop: _ | 4-hop: _`
- **Question Selection Notes:**

## Frozen Run Configuration

- **Answer Model:**
- **Judge Model:**
- **Timeout Policy:**
- **Retry Policy:**
- **Prompt Versions:**
- **Tool Surface Versions:**
- **Scoring Script / Command:**

## Modes Run

- [ ] `baseline`
- [ ] `fixed_graph`
- [ ] `adaptive`

## Run Commands

```bash
# Save question IDs first

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

Create one row per question and mode.

| question_id | hop_count | mode | correct | completion_status | predicted_answer | gold_answer | tools_used | latency_s | cost_usd | failure_class | notes |
|-------------|-----------|------|---------|-------------------|------------------|-------------|------------|-----------|----------|---------------|-------|
|             |           |      |         |                   |                  |             |            |           |          |               |       |

---

## Batch Summary

| mode | answered | completed | EM | F1 | LLM_EM | avg_latency_s | avg_cost_usd | avg_tools |
|------|----------|-----------|----|----|--------|---------------|--------------|-----------|
| baseline | | | | | | | | |
| fixed_graph | | | | | | | | |
| adaptive | | | | | | | | |

## Failure Taxonomy

Assign one primary failure class per miss.

- `retrieval_miss`
- `entity_linking_miss`
- `graph_traversal_miss`
- `context_overload`
- `tool_selection_error`
- `answer_synthesis_error`
- `format_judge_mismatch`
- `timeout_runtime`
- `unknown`

| failure_class | count | representative_ids | comments |
|---------------|-------|--------------------|----------|
|               |       |                    |          |

## Questions Where Graph Helped

- 

## Questions Where Graph Hurt

- 

## Top Observations

1. 
2. 
3. 

---

## Changes After This Batch

Limit changes to 1-3 items.

| change_id | file | reason | expected_effect | failure_class_targeted |
|-----------|------|--------|-----------------|------------------------|
| C1 | | | | |
| C2 | | | | |
| C3 | | | | |

## Rerun Policy

- [ ] No rerun needed
- [ ] Rerun same batch after changes
- [ ] Escalate to new dev batch
- [ ] Freeze and move to locked eval

## Stop / Continue Decision

- **Continue tuning because:**
- **Freeze because:**
- **Blocked because:**

---

## Required Artifacts

- [ ] `results/iterative/batch_01/batch_ids.txt`
- [ ] `results/iterative/batch_01/results.json`
- [ ] `results/iterative/batch_01/summary.md`
- [ ] `results/iterative/batch_01/changes.md`

## Notes

- Do not use this batch score as the final go/no-go evidence.
- If this batch is rerun after changes, preserve the original record and create a new rerun record.
- Once gains flatten across batches, freeze the system and move to a separate locked evaluation split.
