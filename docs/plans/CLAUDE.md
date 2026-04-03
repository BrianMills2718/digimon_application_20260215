# Implementation Plans

Track current implementation work here.

Historical planning artifacts outside `docs/plans/` are not authoritative unless explicitly linked from this index.

## Strategic Roadmap

See [ROADMAP.md](ROADMAP.md) for phase sequence, gates, budget, and escalation criteria.

**Active workstream** (Plans #17, #21-#23): Benchmark-first continuation on the
maintained core lane. The repo already cleared the earlier "agent drowning"
surface enough to prove graph value. The current frontier is narrower:
canonicalization, namesake/gloss representation, and the boundary between local
DIGIMON projection work and experimental onto-canon6 semantic-build
integration.

**Paused workstream** (Plans #3-#6, #12-#13): Extraction quality and representation audit work. Will resume based on Plan #17 gate results — if graph value is confirmed but extraction is identified as the bottleneck.

## Gap Summary

| # | Name | Priority | Status | Blocks |
|---|------|----------|--------|--------|
| 2 | [DIGIMON V2 Greenfield Planning](02_digimon_v2_greenfield_planning_phase.md) | High | ✅ Complete | - |
| 3 | [Prove Adaptive Routing](03_prove_adaptive_routing.md) | High | ✅ Complete (closeout memo: graph value confirmed, adaptive > fixed still unproven) | - |
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
| 16 | [HippoRAG-Aligned Build Attributes](16_build_attributes_sota_alignment.md) | High | ✅ Complete | #17 |
| 17 | [Re-Test Thesis with Clean Architecture](17_retest_thesis.md) | High | ✅ Complete (50q: 42% LLM-judge, prompt tuning eliminated ANSWER_SYNTHESIS) | - |
| 18 | [PTC Validation (conditional)](18_ptc_validation.md) | Medium | 📋 Planned | - |
| 20 | [Tool Linearization + Restore Planning Tools](20_tool_linearization_and_planning_restore.md) | High | ✅ Complete | - |
| 21 | [Autonomous Failure-Iteration Sprint](21_autonomous_failure_iteration_sprint.md) | High | ✅ Complete | Decision-grade Plan #17 rerun |
| 22 | [Benchmark-First Canonicalization And Projection Hardening](22_benchmark_first_canonicalization_projection_hardening.md) | High | 🚧 In Progress | Next decision-grade MuSiQue rerun |
| 23 | [Semantic Build Boundary And onto-canon6 Experiment](23_semantic_build_boundary_and_onto_canon_experiment.md) | High | 🚧 In Progress | Any default-path convergence decision |
| 24 | [Shared Run-Progress Integration For Graph Builds](24_shared_run_progress_integration_for_graph_builds.md) | High | 📋 Planned | llm_client Plan #22 |
| 25 | [authoritative coordination prerequisite remediation](25_authoritative-coordination-prerequisite-remediation.md) | High | ✅ Complete | - |
| 26 | [DIGIMON isolated governed refresh and ownership-baseline repair](26_digimon-isolated-governed-refresh-and-ownership-baseline-repair.md) | High | ✅ Complete | - |

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
