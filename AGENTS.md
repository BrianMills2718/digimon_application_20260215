# CLAUDE.md — DIGIMON

<!-- GENERATED FILE: DO NOT EDIT DIRECTLY -->
<!-- generated_by: scripts/meta/render_agents_md.py -->
<!-- canonical_claude: CLAUDE.md -->
<!-- canonical_relationships: scripts/relationships.yaml -->
<!-- canonical_relationships_sha256: c597a2e79109 -->
<!-- sync_check: python scripts/meta/check_agents_sync.py --check -->

This file is a generated Codex-oriented projection of repo governance.
Edit the canonical sources instead of editing this file directly.

Canonical governance sources:
- `CLAUDE.md` — human-readable project rules, workflow, and references
- `scripts/relationships.yaml` — machine-readable ADR, coupling, and required-reading graph

## Purpose

CLAUDE.md — DIGIMON uses `CLAUDE.md` as canonical repo governance and workflow policy.

## Commands

```bash
# Repo interface
make help                    # List supported targets
make status                  # git status --short --branch
make build                   # Build the configured graph artifact
make bench                   # Run the benchmark entrypoint
make build-status            # Show active graph-build progress

# Targeted benchmark/debug paths
python eval/prebuild_graph.py --help
python eval/run_agent_benchmark.py --help
python scripts/graph_build_status.py

# Plan workflow
python scripts/meta/create_plan.py --title "short title"
python scripts/meta/validate_plan.py --plan-file docs/plans/NN_name.md
python scripts/meta/complete_plan.py --plan N

# Coordination
python scripts/meta/check_coordination_claims.py --check --project Digimon_for_KG_application --json
python scripts/meta/worktree-coordination/create_worktree.py --help
```

## Operating Rules

This projection keeps the highest-signal rules in always-on Codex context.
For full project structure, detailed terminology, and any rule omitted here,
read `CLAUDE.md` directly.

### Principles

1. **Benchmark-first, general fixes only** — improve failure families, not one benchmark row.
2. **Composable build, adaptive retrieval** — graph enrichments are reusable layers and retrieval should only use graph structure when the question benefits from it.
3. **Observability before diagnosis** — inspect graph-build progress, benchmark artifacts, and trace data before guessing.
4. **Representation is product logic** — answer-critical facts must be retrievable as nodes, edges, attributes, or chunk evidence; do not hide them only in prose.
5. **DIGIMON is the retrieval/runtime lane, not the permanent semantic source of truth** — benchmark-lane local build logic is allowed when needed, but long-term ownership boundaries must stay explicit.

### Workflow

### Active execution lane
- Use `docs/plans/CLAUDE.md` as the current plan index.
- The active benchmark lane is Plans #17 and #21-#24, with Plan #22 as the current execution surface for canonicalization/projection hardening.
- Keep repo-local remediation or rollout work in its own numbered plan rather than folding it into benchmark plans.

### Benchmark iteration loop
- Freeze a bounded failing tranche before making representation or routing changes.
- Implement the smallest general fix that addresses the failure family.
- Rebuild on the smallest real slice first, then rerun the frozen tranche before broadening scope.
- Record the before/after artifact path in the active plan and append durable findings to `KNOWLEDGE.md`.

### Coordination and governance
- Work from claimed worktrees for implementation slices; do not edit the dirty canonical checkout for DIGIMON remediation.
- Keep `AGENTS.md` generated from this file and rerender it after governance-structure changes.
- If a shared or upstream migration question appears, record it in the active plan instead of silently redefining DIGIMON ownership.

## Machine-Readable Governance

`scripts/relationships.yaml` is the source of truth for machine-readable governance in this repo: ADR coupling, required-reading edges, and doc-code linkage. This generated file does not inline that graph; it records the canonical path and sync marker, then points operators and validators back to the source graph. Prefer deterministic validators over prompt-only memory when those scripts are available.

## References

| Doc | Purpose |
|-----|---------|
| `docs/plans/CLAUDE.md` | Active plan index |
| `docs/plans/17_retest_thesis.md` | Thesis gate and benchmark decision frame |
| `docs/plans/22_benchmark_first_canonicalization_projection_hardening.md` | Current benchmark execution lane |
| `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md` | DIGIMON vs onto-canon6 boundary plan |
| `docs/plans/24_shared_run_progress_integration_for_graph_builds.md` | Shared graph-build observability contract |
| `docs/GRAPH_ATTRIBUTE_MODEL.md` | Long-term graph representation and projection model |
| `docs/ACTIVE_DOCS.md` | Current documentation authority map |
| `KNOWLEDGE.md` | Cross-agent runtime findings |
