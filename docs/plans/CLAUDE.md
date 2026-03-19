# Implementation Plans

Track current implementation work here.

Historical planning artifacts outside `docs/plans/` are not authoritative unless explicitly linked from this index.

## Gap Summary

| # | Name | Priority | Status | Blocks |
|---|------|----------|--------|--------|
| 1 | [Example Plan](01_example.md) | Medium | 📋 Planned | - |
| 2 | [DIGIMON V2 Greenfield Planning Phase](02_digimon_v2_greenfield_planning_phase.md) | High | ✅ Complete | - |
| 3 | [Prove Adaptive Routing](03_prove_adaptive_routing.md) | High | 🚧 In Progress | All future investment |

## Status Key

| Status | Meaning |
|--------|---------|
| Planned | Ready to implement |
| In Progress | Being worked on |
| Blocked | Waiting on dependency |
| Complete | Implemented and verified |

## Creating a New Plan

1. Copy `TEMPLATE.md` to `NN_name.md`
2. Fill in gap, steps, required tests
3. Add to this index
4. Commit with `[Plan #N]` prefix

## Supporting Templates

- `BATCH_ITERATION_TEMPLATE.md` - for 10-20 question development batches during iterative tuning
- `LOCKED_EVAL_PROTOCOL.md` - for decision-grade benchmark runs on untouched question IDs

## Batch Records

- `batch_01_musique_dev.md` - first MuSiQue development batch record
- `batch_01_musique_dev_rerun_a.md` - first rerun record for batch 01

## Trivial Changes

Not everything needs a plan. Use `[Trivial]` for:
- Less than 20 lines changed
- No changes to `src/` (production code)
- No new files created

```bash
git commit -m "[Trivial] Fix typo in README"
```

## Completing Plans

```bash
python scripts/meta/complete_plan.py --plan N
```

This verifies tests pass and records completion evidence.
