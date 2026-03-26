# GraphRAG Next Steps — Execution Plan

**Created:** 2026-03-26
**Status:** Active — execute in order, skip nothing

## Current State

- Baseline: 21.1% LLM-judge (4/19 MuSiQue)
- Best GraphRAG run: 42.1% LLM-judge (8/19, v3.0 prompt + linearization)
- Gate D: Met (>5% improvement, ≥5 graph wins)
- Blocked: llm_client missing 6 post-eval exports (benchmark crashes on post-eval)

## Immediate Blockers

### Blocker 1: llm_client missing exports
The benchmark runner crashes on post-eval because llm_client deleted 6 functions.
**Fix:** Either restore exports in llm_client OR disable post-eval temporarily:
```bash
# Temporary: skip post-eval (add these flags to make bench-musique)
--post-det-checks none --post-review-rubric none --post-gate-policy none
```

## Phase 1: Iterate on Failing Questions (4-6 hours)

**Methodology:** Run ONLY failing questions. Diagnose. Fix. Re-run failures. Repeat.

### Step 1: Identify current failure set
```bash
# Run the both-fail frozen set (8 questions where baseline AND GraphRAG fail)
make bench FILE=eval/fixtures/musique_both_fail_frozen.json
# These are the questions where GraphRAG SHOULD add value but doesn't yet
```

### Step 2: Diagnose each failure
```bash
# For each failing question:
make diagnose FILE=results/latest.json QID=<question_id>
# Check: Did the agent plan? Complete the plan? Retrieve evidence? Ground in source text?
# Classify: extraction_miss / entity_linking_miss / graph_traversal_miss / retrieval_strategy / answer_synthesis
```

### Step 3: Fix systemic issues (not per-question hacks)
Based on diagnosis, fix the CATEGORY not the individual question:
- If "submitted before plan complete" → enforce plan completion (harness or prompt)
- If "chunk by_ids returned empty" → check linearization for more data-loss patterns
- If "entity not in graph" → extraction issue (separate workstream)
- If "PPR didn't reach target" → graph connectivity issue
- If "right evidence, wrong answer" → answer synthesis prompt issue

### Step 4: Re-run ONLY the failures that the fix should address
```bash
# Create a fixture file with just the relevant failing question IDs
# Run only those
```

### Step 5: When all both-fail questions are either fixed or classified as "extraction_miss" (unfixable without graph rebuild), move to Phase 2

## Phase 2: Scale to 50q (2-3 hours)

### Step 1: Run baseline on 50q MuSiQue
```bash
python eval/run_agent_benchmark.py --dataset MuSiQue --num 50 --mode baseline \
  --model openrouter/openai/gpt-5.4-mini --backend direct \
  --agent-spec none --allow-missing-agent-spec --missing-agent-spec-reason "relocated" \
  --post-det-checks none --post-review-rubric none --post-gate-policy none
```

### Step 2: Run GraphRAG on same 50q
```bash
python eval/run_agent_benchmark.py --dataset MuSiQue --num 50 \
  --model openrouter/openai/gpt-5.4-mini --backend direct \
  --agent-spec none --allow-missing-agent-spec --missing-agent-spec-reason "relocated" \
  --post-det-checks none --post-review-rubric none --post-gate-policy none
```

### Step 3: Cross-reference and document
- Graph wins count, regression count
- Failure family distribution
- Statistical significance (n=50 is still small but better than n=19)

## Phase 3: Implement llm_client Plan #19 — Agent Planning (4-6 hours)

File-based plan state + auto-injected context + harness-level plan enforcement.
See: `~/projects/llm_client/docs/plans/19_agent_planning_and_working_memory.md`

This is the highest-impact infrastructure change — prevents premature submission,
gives the agent persistent working memory, and benefits every llm_client consumer.

## Phase 4: Graph Rebuild (2-4 hours, ~$5-10)

Only after Phase 1-2 confirm that retrieval strategy (not graph quality) is the
primary bottleneck. If Phase 1 shows many "extraction_miss" failures, the rebuild
becomes higher priority.

Build config in `notebooks/plan17_thesis_retest.ipynb` Phase 1.

## Rules for Execution

1. **Observability first, speculation never.** Run `make cost-by-task`, `make diagnose` BEFORE guessing.
2. **Iterate on failures only.** Never re-run passing questions.
3. **Commit at every verified milestone.** Don't batch.
4. **Log uncertainties and continue.** Don't stop to ask — document and proceed.
5. **Fail loud.** No try/except ImportError. No silent fallbacks.
6. **Check linearization health.** Run `make linearization-check` after every code change to linearization.
