# Implementation Plans

Track current implementation work here.

Historical planning artifacts outside `docs/plans/` are not authoritative unless explicitly linked from this index.

## Strategic Roadmap

See [ROADMAP.md](ROADMAP.md) for phase sequence, gates, budget, and escalation criteria.

**Active workstream** (Plans #14-#18): Strategic pivot to fix the agent drowning problem before re-testing the adaptive routing thesis. Literature review confirmed graph value is real but DIGIMON is missing key SOTA innovations and the 50-tool surface overwhelms the routing agent.

**Paused workstream** (Plans #3-#6, #12-#13): Extraction quality and representation audit work. Will resume based on Plan #17 gate results — if graph value is confirmed but extraction is identified as the bottleneck.

## Gap Summary

| # | Name | Priority | Status | Blocks |
|---|------|----------|--------|--------|
| 2 | [DIGIMON V2 Greenfield Planning](02_digimon_v2_greenfield_planning_phase.md) | High | ✅ Complete | - |
| 3 | [Prove Adaptive Routing](03_prove_adaptive_routing.md) | High | ⏸️ Blocked | Superseded by #17 |
| 4 | [Graph Build Rearchitecture](04_graph_build_rearchitecture.md) | High | ⏸️ Blocked | Partially superseded by #16 |
| 5 | [Extraction Quality Repair](05_extraction_quality_repair.md) | High | ⏸️ Blocked | Resumes if #17 identifies extraction bottleneck |
| 6 | [Two-Pass Extraction Proof](06_two_pass_extraction_proof.md) | High | ⏸️ Blocked | Resumes if #17 identifies extraction bottleneck |
| 7 | [Extraction Iteration Supervisor](07_extraction_iteration_supervisor.md) | High | ✅ Complete | - |
| 8 | [Supervisor Sentinel Gating](08_supervisor_sentinel_gating.md) | High | ✅ Complete | - |
| 9 | [Supervisor Smoke-Build Gate](09_supervisor_smoke_build_gate.md) | High | ✅ Complete | - |
| 10 | [Open-Schema Type Contract](10_open_schema_type_contract.md) | High | ✅ Complete | - |
| 11 | [Completeness Promotion Gate](11_completeness_promotion_gate.md) | High | ✅ Complete | - |
| 12 | [MuSiQue Representation Audit](12_musique_representation_audit.md) | High | ⏸️ Blocked | Resumes if #17 identifies routing bottleneck |
| 13 | [Benchmark Anchor Resolution](13_benchmark_anchor_resolution.md) | High | ⏸️ Blocked | Resumes if #17 identifies routing bottleneck |
| 14 | [Fix llm_client / Unblock Benchmark Runner](14_fix_llm_client_benchmark_runner.md) | High | ✅ Complete | #15, #17 |
| 15 | [Operator Consolidation (28→8-10 tools)](15_operator_consolidation.md) | High | ✅ Complete | #17 |
| 16 | [HippoRAG-Aligned Build Attributes](16_build_attributes_sota_alignment.md) | High | 🚧 In Progress | #17 |
| 17 | [Re-Test Thesis with Clean Architecture](17_retest_thesis.md) | High | 📋 Planned | - |
| 18 | [PTC Validation (conditional)](18_ptc_validation.md) | Medium | 📋 Planned | - |

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
