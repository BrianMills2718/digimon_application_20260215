# Locked Evaluation Protocol

Use this protocol for any decision-grade benchmark run.

Purpose:
- prevent dev/eval leakage
- ensure all modes run on the same locked IDs
- make the final benchmark reproducible

Current harness note:
- `eval/run_agent_benchmark.py` now supports `--questions-file`, `--write-selected-ids`, and deterministic `--sample-seed`
- locked splits should still be managed as checked-in artifacts, but the harness no longer requires manual comma-joining of IDs

---

## Required Artifacts

- `results/iterative/dev_ids/` for tuned-on question IDs
- `results/locked_eval/locked_eval_ids.txt` for untouched evaluation IDs
- `results/locked_eval/README.md` describing sampling method, date, owner, dataset, and seed or manual rule

## Rules

1. The locked evaluation IDs must be selected before the final run.
2. Locked evaluation IDs must not overlap with tuned-on batch IDs.
3. All comparison modes must run on the exact same locked evaluation IDs.
4. Prompts, tool surfaces, retry policy, timeout policy, and scoring rules must be frozen before the locked run.
5. If any of those change, the locked evaluation must be re-declared.

## Selection Procedure

1. Choose the dataset.
2. Decide the target count and hop mix.
3. Export the final locked IDs to `results/locked_eval/locked_eval_ids.txt`.
4. Record the method in `results/locked_eval/README.md`.
5. Check for overlap against all tuned-on batch ID files.

## Overlap Check

```bash
comm -12 \
  <(sort results/iterative/dev_ids/all_dev_ids.txt) \
  <(sort results/locked_eval/locked_eval_ids.txt)
```

Expected result: no output.

## Running the Locked Eval

```bash
python eval/run_agent_benchmark.py \
  --dataset MuSiQue \
  --questions-file results/locked_eval/locked_eval_ids.txt \
  --mode baseline \
  ...

python eval/run_agent_benchmark.py \
  --dataset MuSiQue \
  --questions-file results/locked_eval/locked_eval_ids.txt \
  --mode fixed_graph \
  ...

python eval/run_agent_benchmark.py \
  --dataset MuSiQue \
  --questions-file results/locked_eval/locked_eval_ids.txt \
  --mode hybrid \
  ...
```

## Pre-Run Checklist

- [ ] Locked IDs file exists
- [ ] Sampling method documented
- [ ] No overlap with tuned-on IDs
- [ ] Same answer model across all modes
- [ ] Same judge model across all modes
- [ ] Same timeout and retry policy across all modes
- [ ] Same scorer across all modes
- [ ] Prompts and tool surfaces frozen

## Post-Run Checklist

- [ ] Results artifacts saved for all modes
- [ ] Comparison table built from the same locked IDs
- [ ] Completion rate recorded
- [ ] Cost and latency recorded
- [ ] Go/no-go gate applied only to this locked run

## If You Cannot Provide an Untouched Locked Split

Do not call the result decision-grade evidence.

Label it explicitly as one of:
- `development score`
- `tuned-on dev result`
- `directional evidence only`
