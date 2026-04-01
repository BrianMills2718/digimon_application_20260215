# Plan #24: Shared Run-Progress Integration For Graph Builds

**Status:** Planned
**Type:** implementation
**Priority:** High
**Blocked By:** llm_client Plan #22 shared observability contract
**Blocks:** decision-grade observability for Plan #22/graph rebuilds, future long-running DIGIMON build/index tasks

---

## Gap

**Current:** DIGIMON graph builds expose only local evidence:

- repo-local checkpoint files,
- repo-local logs,
- stdout heartbeat text,
- ad hoc process inspection.

That is enough to resume work manually, but not enough to query current state
or detect stalls through shared infrastructure. The current Plan #22 MuSiQue
projection rebuild demonstrates the gap: we can see `_checkpoint_processed.json`
and the process table, but not a durable run-progress record in shared
observability.

**Target:** Once `llm_client` exposes shared run-progress observability, DIGIMON
should use it for graph builds and prebuild orchestration:

1. register graph builds as experiment runs,
2. emit stage changes (`initialize`, `build_er_graph`, `build_entity_vdb`,
   `build_relationship_vdb`, `restore`, etc.),
3. emit per-batch progress snapshots from the checkpointed ER build loop,
4. mark explicit stagnation/failure when a build stops making progress,
5. expose a DIGIMON-friendly status command/view built on the shared query
   surface.

**Why:** Benchmark-first work still needs credible observability. Without a
shared status path, overnight graph builds remain hard to diagnose and too easy
to misread.

---

## References Reviewed

- `eval/prebuild_graph.py` - current build orchestration
- `Core/AgentTools/graph_construction_tools.py` - build tool boundary
- `Core/Graph/BaseGraph.py` - checkpoint-aware build orchestration
- `Core/Graph/ERGraph.py` - batch loop and checkpoint persistence
- `docs/plans/22_benchmark_first_canonicalization_projection_hardening.md` - active benchmark consumer
- `KNOWLEDGE.md` - current projection-build runtime findings

---

## Pre-made Decisions

1. **DIGIMON consumes the shared observability contract; it does not invent a second one.**
2. **Integration starts with graph builds only.**
   Do not broaden to all DIGIMON jobs in the first slice.
3. **Use existing build checkpoints as the canonical numeric progress source.**
   Do not create a second progress counter in DIGIMON.
4. **Emit progress at batch boundaries.**
   Per-chunk events are too noisy for the first slice.
5. **Keep runtime conditions explicit.**
   Build runs should record the artifact dataset, graph profile, passage/cooccurrence flags, and chunk limits in run config or stage metadata.
6. **No DIGIMON-local persistence fork.**
   If shared infra cannot store it, the feature is incomplete.

---

## Files Affected

- `docs/plans/24_shared_run_progress_integration_for_graph_builds.md` (create)
- `docs/plans/CLAUDE.md` (modify)
- `eval/prebuild_graph.py` (modify)
- `Core/Graph/ERGraph.py` (modify)
- `Core/AgentTools/graph_construction_tools.py` (modify if run/stage ownership belongs there)
- `Makefile` (modify if a status target is added)
- `tests/unit/test_prebuild_graph_cli.py` (modify if status/config wiring changes)
- `tests/unit/test_graph_build_progress_observability.py` (create)

---

## Contract

### DIGIMON producer behavior

`eval/prebuild_graph.py` should:

- start a shared run at the start of prebuild,
- emit named stages for each major step,
- attach build metadata:
  - source dataset
  - artifact dataset
  - graph profile
  - chunk limit
  - passage-node/cooccurrence flags
  - whether VDB phases are skipped
- finish or fail the run explicitly.

`ERGraph._build_graph()` should:

- emit progress snapshots after each persisted batch checkpoint,
- include:
  - total chunks
  - completed chunks
  - failed chunks so far
  - checkpoint path
  - current batch number
  - elapsed time

### Consumer/operator surface

The first slice should add a DIGIMON operator-facing status command, likely a
Make target or small script, that uses shared infra to answer:

- which graph builds are active,
- what stage each is in,
- how many chunks are done,
- when progress last moved,
- whether the run is stagnated.

---

## Plan

### Step 1: Wire run registration into prebuild orchestration

Add `start_run` / `finish_run` usage to `eval/prebuild_graph.py`.

**Acceptance:**
- every prebuild invocation gets a durable run record,
- build config/provenance is attached to the run.

### Step 2: Emit stage transitions

Mark clear stages around graph/VDB phases.

**Acceptance:**
- operator can distinguish graph build from VDB build from restore/fail.

### Step 3: Emit per-batch progress from ERGraph

Use the existing checkpoint loop to log shared run progress.

**Acceptance:**
- progress rows reflect the same chunk counts as `_checkpoint_processed.json`,
- batch completion updates last-progress timestamps durably.

### Step 4: Add DIGIMON status surface

Expose a simple status command built on shared helpers.

**Acceptance:**
- operator can inspect active DIGIMON builds without reading raw files/processes.

### Step 5: Prove on a bounded live build

Run a small build and verify shared progress moves as expected.

**Acceptance:**
- live bounded build shows at least one stage transition and one progress update,
- status output matches the checkpoint file.

---

## Required Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/unit/test_graph_build_progress_observability.py` | `test_prebuild_graph_registers_shared_run_and_stage_events` | prebuild starts and finishes a shared run correctly |
| `tests/unit/test_graph_build_progress_observability.py` | `test_ergraph_progress_updates_follow_checkpoint_counts` | ERGraph batch progress emits truthful counts |
| `tests/unit/test_graph_build_progress_observability.py` | `test_failed_build_marks_run_failed_with_last_progress` | failures do not leave runs silently in-progress |

Existing tests that must pass:

- `tests/unit/test_prebuild_graph_cli.py`
- any llm_client observability tests touched by the shared contract

---

## Acceptance Criteria

- [ ] DIGIMON graph builds register shared experiment runs
- [ ] Graph builds emit durable stage transitions
- [ ] ERGraph batch checkpoints emit shared run-progress updates
- [ ] DIGIMON exposes a usable status view built on shared infra
- [ ] A bounded live build proves the integration end to end

---

## Uncertainties

### Q1: Should run ownership live in `prebuild_graph.py` or `build_er_graph()`?
**Status:** Open
**Why it matters:** `prebuild_graph.py` orchestrates multi-stage builds, while
`build_er_graph()` owns the core graph-build tool semantics.
**Plan handling:** Prefer the smallest boundary that keeps one run per prebuild
operation instead of nested competing runs.

### Q2: What counts as stagnation for graph builds?
**Status:** Open
**Why it matters:** A slow batch is not necessarily a stalled run.
**Plan handling:** First slice records last progress timestamp and explicit
checkpoint counts; inferred stagnation can remain conservative.

### Q3: Should VDB phases emit the same progress contract immediately?
**Status:** Open
**Why it matters:** They may not have a natural total/completed unit count yet.
**Plan handling:** Stage events first; numeric progress only where DIGIMON has a
truthful counter already.

---

## Notes

- This plan intentionally depends on shared infra rather than patching DIGIMON
  with more repo-local logs.
- The active Plan #22 projection rebuild is the motivating consumer, but this
  integration must generalize to future DIGIMON long-running builds.
