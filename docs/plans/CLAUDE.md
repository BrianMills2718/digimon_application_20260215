# Implementation Plans

Track current implementation work here.

Historical planning artifacts outside `docs/plans/` are not authoritative unless explicitly linked from this index.

## Gap Summary

| # | Name | Priority | Status | Blocks |
|---|------|----------|--------|--------|
| 1 | [Example Plan](01_example.md) | Medium | 📋 Planned | - |
| 2 | [DIGIMON V2 Greenfield Planning Phase](02_digimon_v2_greenfield_planning_phase.md) | High | ✅ Complete | - |
| 3 | [Prove Adaptive Routing](03_prove_adaptive_routing.md) | High | 🚧 In Progress | All future investment |
| 4 | [Graph Build Rearchitecture](04_graph_build_rearchitecture.md) | High | 🚧 In Progress | Clean graph rebuild |
| 5 | [Extraction Quality Repair for Entity-Graph Builds](05_extraction_quality_repair.md) | High | 🚧 In Progress | Full MuSiQue rebuild, fixed-graph sanity rerun |
| 6 | [Two-Pass Extraction Proof for Entity Completeness](06_two_pass_extraction_proof.md) | High | 🚧 In Progress | Next live entity-graph smoke rebuild |
| 7 | [Extraction Iteration Supervisor](07_extraction_iteration_supervisor.md) | High | ✅ Complete | Reliable long-running autonomous extraction iteration |
| 8 | [Supervisor Sentinel Gating](08_supervisor_sentinel_gating.md) | High | ✅ Complete | Trustworthy unattended extraction-family promotion |
| 9 | [Typed Smoke-Build Gate for the Extraction Supervisor](09_supervisor_smoke_build_gate.md) | High | ✅ Complete | Trustworthy unattended promotion beyond prompt-eval-only evidence |
| 10 | [Truthful Open-Schema Type Contract for TKG Extraction](10_open_schema_type_contract.md) | High | ✅ Complete | Further grounded-endpoint supervisor cycles, trustworthy open-TKG prompt iteration |
| 11 | [Strengthen Completeness Promotion Gating](11_completeness_promotion_gate.md) | High | ✅ Complete | Further unattended grounded-endpoint supervisor cycles |

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
