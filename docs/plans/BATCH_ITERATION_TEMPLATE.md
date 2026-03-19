# Batch Iteration Template

Use this template for 10-20 question development batches while tuning DIGIMON.

Important:
- A batch run is a development artifact, not a final benchmark claim.
- Save exact question IDs before running.
- Do not change prompts, tools, or scoring rules mid-batch.
- If you rerun after changes, create a new batch record such as `batch_03_rerun_a`.

---

## Batch Metadata

- **Batch ID:** `batch_XX`
- **Date:**
- **Owner:**
- **Dataset:** `MuSiQue | HotpotQA | 2WikiMultiHopQA`
- **Question Count:** `10-20`
- **Question IDs File:** `results/iterative/batch_XX/batch_ids.txt`
- **Seen Before:** `yes | no | mixed`
- **Purpose:** `bug fix | routing tune | baseline check | regression check`

## Split Record

- **Sampling Method:** `manual | random | balanced`
- **Seed:** 
- **Hop Mix:** `2-hop: _ | 3-hop: _ | 4-hop: _`
- **Notes:**

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

# fixed_graph

# adaptive
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

- [ ] `results/iterative/batch_XX/batch_ids.txt`
- [ ] `results/iterative/batch_XX/results.json`
- [ ] `results/iterative/batch_XX/summary.md`
- [ ] `results/iterative/batch_XX/changes.md`

## Directory Convention

```text
results/iterative/
  batch_01/
  batch_02/
  batch_03_rerun_a/
```

## Final Reminder

Do not use tuned-on batch scores as the final go/no-go evidence. Once gains flatten, freeze the system and run a separate locked evaluation split.
