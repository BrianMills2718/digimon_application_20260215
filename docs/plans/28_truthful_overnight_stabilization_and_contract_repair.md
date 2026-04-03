# Plan #28: Truthful Overnight Stabilization And Contract Repair

**Status:** In Progress
**Type:** implementation
**Priority:** High
**Blocked By:** None
**Blocks:** Next 19q / 50q decision-grade reruns

---

## Gap

**Current:**

The maintained DIGIMON benchmark lane is no longer blocked by missing product
value. It already demonstrated a meaningful 50q MuSiQue lift over baseline
(20.0% → 42.0% LLM-judge on 2026-03-26). The current blocker is **truthful
execution**: the overnight handoff, `CURRENT_STATUS.md`, and some in-repo
operating assumptions are now out of sync with the actual code and benchmark
artifacts.

Verified examples from the 2026-04-03 artifact set:

1. **Question 619265 is misdiagnosed in the current handoff.**
   The real corpus anchor is `"The Bag or the Bat"` → `Ray Donovan`
   (`results/MuSiQue/corpus/Corpus.json`, doc_id 200 and 213). This is not
   fundamentally a "Batman Beyond aggregate-summary trap" problem. The failing
   path is an **exact-anchor/query-rewrite failure family** where the control
   layer compacts the quoted title into `Bag Bat`, allowing semantic drift.

2. **Question 754156 is also misdescribed in the handoff.**
   The benchmark artifact gold is
   `"The dynasty regrouped and defeated the Portuguese"`, not `Laos`.
   The run artifacts show repeated premature submission of intermediate
   geography (`Laos`, `Myanmar`) despite the final answer being an action/event
   phrase. This is an **answer-kind / premature-submit / chain-completion**
   problem, not an entity-name question.

3. **Current repo truth drift exists in multiple control artifacts.**
   - `prompts/agent_benchmark_consolidated.yaml` still says `version: "3.0"`
     while the handoff and current prompt content describe later behavior.
   - `CURRENT_STATUS.md` says `entity_search top_k=10 default`, but the live
     consolidated tool default is `top_k=5` and `KNOWLEDGE.md` records that
     10 was worse and was reverted.
   - `Makefile` help text still says `bench-musique` uses `STAG_TURNS=4` while
     the live default is `STAG_TURNS ?= 6`.

4. **The tool surface does not fully match how the agent is already trying to
   use it.**
   - The agent repeatedly calls `entity_info(method="resolve", entity_name=...)`,
     but the underlying implementation currently requires `entity_names`.
   - The prompt encourages graph follow-ups generically, but some graph-mode
     calls still fail when the agent has not yet resolved the required entity
     IDs.

**Target:**

1. Restore a truthful execution surface: active plan, `CLAUDE.md`,
   `CURRENT_STATUS.md`, prompt versioning, and Makefile help must match the
   actual maintained lane.
2. Repair the highest-confidence systemic failure family:
   **exact-anchor preservation + tool-contract truthfulness**.
3. Verify the repair on a frozen targeted slice before spending more budget on
   full 19q / 50q reruns.
4. Only continue broad overnight iteration if the maintained lane shows real
   improvement under fixed settings and the controlling docs are truthful.

---

## Why This Matters

Without a truthful control plane, "run continuously" becomes wasteful rather
than autonomous. DIGIMON's current differentiator is not "being a GraphRAG
implementation" in the abstract; it is the hypothesis that a control layer can
choose retrieval surfaces adaptively. That hypothesis cannot be tested cleanly
if:

- the benchmark failure families are mislabeled,
- the prompt/tool contract lies about how tools work,
- or the overnight phase sequence keeps optimizing stale diagnoses.

The first repair is therefore **truthful execution**, not another blind prompt
tweak.

---

## References Reviewed

- `CLAUDE.md`
- `CURRENT_STATUS.md`
- `KNOWLEDGE.md`
- `docs/handoff_2026_04_03.md`
- `docs/plans/27_retrieval_strategy_heuristics.md`
- `prompts/agent_benchmark_consolidated.yaml`
- `Core/MCP/tool_consolidation.py`
- `digimon_mcp_stdio_server.py`
- `tests/unit/test_semantic_plan_query_contract.py`
- `tests/test_tool_consolidation.py`
- `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T003635Z.json`
- `results/MuSiQue_gpt-5-4-mini_consolidated_20260403T045308Z.json`
- `results/MuSiQue/corpus/Corpus.json`

External comparators reviewed from official sources:

- Microsoft GraphRAG
- HippoRAG 2
- LightRAG
- Neo4j GraphRAG for Python

---

## Files Affected

- `CLAUDE.md`
- `CURRENT_STATUS.md`
- `docs/plans/CLAUDE.md`
- `docs/plans/28_truthful_overnight_stabilization_and_contract_repair.md`
- `prompts/agent_benchmark_consolidated.yaml`
- `Core/MCP/tool_consolidation.py`
- `digimon_mcp_stdio_server.py`
- `tests/unit/test_semantic_plan_query_contract.py`
- `tests/test_tool_consolidation.py`
- `scripts/validate_status_truth.py`
- `scripts/benchmark_iteration_report.py`
- `tests/unit/test_validate_status_truth.py`
- `tests/unit/test_benchmark_iteration_report.py`
- `docs/HANDOFF_TEMPLATE.md`
- `docs/BENCHMARK_PROMOTION_POLICY.md`
- `docs/reports/musique_19q_iteration_report_2026_04_03.md`
- `docs/handoff_2026_04_03.md`

---

## Implementation Phases (next 24 hours)

### Phase 0 — Truth Restoration

Update the authoritative operating artifacts so the current overnight lane is
based on verified behavior, not stale narrative.

**Tasks**
- Add a truthfulness gate to `CLAUDE.md`: if handoff/status docs conflict with
  code or artifacts, correct the docs first and continue from verified state.
- Create this plan and register it in `docs/plans/CLAUDE.md`.
- Correct stale status facts:
  - prompt version field
  - live `top_k` default
  - live `STAG_TURNS` default/help text
  - 619265 / 754156 failure-family descriptions

**Acceptance**
- Active overnight plan exists and is linked from the plan index.
- `CLAUDE.md` explicitly requires correcting stale diagnostics before continued
  autonomous execution.
- `CURRENT_STATUS.md` no longer contradicts the maintained code path on the
  verified facts above.

### Phase 1 — Exact-Anchor And Tool-Contract Repair

Land the smallest general control-layer changes that directly address the most
evidenced failure family.

**Tasks**
- Preserve quoted anchors / explicit titles in `_compact_search_query()` so
  retrieval does not collapse `"The Bag or the Bat"` into `Bag Bat`.
- Preserve explicit quoted anchors during active-atom query rewriting.
- Allow consolidated `entity_info(method="resolve")` to accept single-name
  calls that the agent is already attempting (`entity_name=...`), translating
  them to the underlying `entity_names=[...]` contract.
- Update prompt guidance to explicitly preserve quoted anchors and favor exact
  text/string search before semantic drift when a question contains a title or
  literal name span.

**Acceptance**
- New or updated unit tests cover quoted-anchor preservation.
- New or updated unit tests cover single-name resolve compatibility.
- Maintained tests for query-contract rewriting and consolidated tools pass.

### Phase 2 — Targeted Verification

Verify the slice on the minimal frozen set that exercises the repaired family.

**Target questions**
- `2hop__619265_45326` — quoted-title anchor preservation
- `2hop__199513_801817` — namesake/alias + exact string/entity resolution
- `3hop1__136129_87694_124169` — downstream chain depends on truthful atom closure
- `4hop3__754156_88460_30152_20999` — answer-kind / premature-submit sanity check

**Tasks**
- Run targeted tests first.
- Run bounded diagnostic reruns only after tests pass.
- Record whether the repair changes retrieval trajectories in the expected way
  (for example, whether exact quoted titles survive into effective queries).

**Acceptance**
- Deterministic tests pass.
- At least one targeted runtime artifact shows the repaired contract behavior.
- Any remaining miss is classified truthfully by failure family.

### Phase 3 — Fixed-Setting 19q Baseline

Only after Phases 0-2 are complete, re-establish the 19q baseline under one
fixed configuration.

**Tasks**
- Run the 19q diagnostic set 3 times at identical settings.
- Compute mean, spread, and per-question stability.
- Update `CURRENT_STATUS.md` with the new baseline distribution.

**Acceptance**
- Three result artifacts exist at one fixed setting.
- Mean and spread are recorded.
- No claim of improvement is made from a single-run outlier.

### Phase 4 — Spend / Continue / Pivot Gate

Use the corrected evidence to decide whether another overnight sprint is
warranted.

**Continue spending time only if all are true**
- the control plane is truthful,
- the repaired slice reduces real failure behavior,
- and the 19q mean is improving or the remaining misses are now cleanly
  concentrated in one or two generalizable families.

**Pivot away from custom DIGIMON control-layer work if any are true**
- the same failure families remain after truthful contract repair,
- the 19q mean does not improve beyond stochastic noise,
- or most new work is rebuilding capabilities already available in maintained
  GraphRAG libraries instead of testing DIGIMON's adaptive-routing thesis.

---

## Failure Modes And Diagnostics

| Failure mode | Observable signal | Diagnosis path | Next action |
|---|---|---|---|
| Stale control artifact | Doc says X, code/artifact says Y | Compare handoff/status file to code defaults and latest result JSON | Correct docs before any new tuning |
| Exact-anchor destruction | Effective query drops stopwords from quoted titles | Inspect `query_contract.effective_query` in tool previews | Preserve quoted spans in compaction/rewrite |
| Tool contract mismatch | `entity_names is required`, `entity_ids is required`, validation errors | Check result JSON counts and question diagnose traces | Accept common aliases or tighten prompt instructions |
| Premature intermediate submit | Final answer equals a mid-chain entity/place | Diagnose trace, compare gold/predicted with atom progression | Repair answer-type / chain-completion guidance, not the graph |
| Benchmark-noise false confidence | One run spikes up or down | Require 3 fixed-setting runs | Report mean/spread, not single best |

---

## Simpler Alternatives / External Learnings

These are not implementation tasks for this plan, but they shape the spend
decision:

1. **If the goal is production QA rather than control-policy research, DIGIMON
   should stop rebuilding commodity GraphRAG infrastructure.**
   Neo4j GraphRAG, LightRAG, and Microsoft GraphRAG already provide maintained
   retrieval/index/query layers. DIGIMON should only own the adaptive control
   layer or a clearly differentiated evaluation harness.

2. **If the goal is better multi-hop retrieval with lower indexing cost, HippoRAG 2
   is the strongest external baseline to compare against before doing more
   custom graph-build work.**

3. **If the goal is faster iteration and observability, LightRAG's current
   tracing / citation / reranker defaults are a practical bar DIGIMON should
   either meet or reuse, not ignore.**

---

## Acceptance Criteria

- [x] Plan and plan index updated
- [x] `CLAUDE.md` truthfulness gate added
- [x] Quoted-anchor preservation implemented and tested
- [x] `entity_info(resolve)` single-name compatibility implemented and tested
- [x] Prompt/version/control artifacts updated to truthful state
- [x] Truth validator + benchmark report tooling landed and verified
- [x] Handoff/status/process docs updated to use generated truth surfaces
- [ ] Targeted verification completed and findings recorded
- [ ] 19q fixed-setting triple-run baseline completed OR explicitly deferred with reason

## Progress (2026-04-02)

- Plan created and linked from `docs/plans/CLAUDE.md`.
- `CLAUDE.md` updated with a truthfulness gate for autonomous execution.
- Implemented deterministic contract repairs:
  - quoted-anchor preservation in `_compact_search_query()`
  - consolidated `entity_info(method="resolve")` compatibility for single-name calls
  - prompt guidance for exact quoted anchors
- Verified with:
  - `python -m compileall Core/MCP/tool_consolidation.py digimon_mcp_stdio_server.py`
  - `/home/brian/projects/Digimon_for_KG_application/.venv/bin/pytest -q tests/unit/test_semantic_plan_query_contract.py tests/test_tool_consolidation.py`
    → `54 passed`
- Worktree runtime verification surfaced an operational prerequisite:
  `eval/run_agent_benchmark.py` in a fresh worktree depends on local-only
  `Option/Config2.yaml` and `results/MuSiQue/...` artifacts. This is now
  recorded in `KNOWLEDGE.md` and must be provisioned explicitly for future
  benchmark runs from claimed worktrees.
- Bounded runtime probe on `2hop__619265_45326` produced live observability
  traces (`trace_id=digimon.benchmark.MuSiQue.2hop__619265_45326.716b5580`).
  The quoted anchor now survives into the live question state, but the run can
  still drift later to a wrong bridge candidate (`showtime`). Conclusion:
  exact-anchor preservation is necessary but not sufficient; the next fix must
  constrain bridge selection once the source chunk already names the series.
- Added process-enforcement tooling:
  - `scripts/validate_status_truth.py` + `make truth-check`
  - `scripts/benchmark_iteration_report.py` + `make benchmark-report`
  - `docs/HANDOFF_TEMPLATE.md`
  - `docs/BENCHMARK_PROMOTION_POLICY.md`
- Generated `docs/reports/musique_19q_iteration_report_2026_04_03.md` from the
  five maintained 19q status artifacts. Historical slice summary:
  `43.16%` mean LLM_EM, `12.00` sample stdev, `31.58%-57.89%` range.
- Rewrote `docs/handoff_2026_04_03.md` and tightened `CURRENT_STATUS.md` until
  `python scripts/validate_status_truth.py --artifact-root <canonical-repo-root>`
  reported a clean truth surface.

---

## Notes

- This plan intentionally does **not** assume the current handoff diagnosis is
  correct. Verified artifacts outrank narrative summaries.
- No question-specific patches are allowed. The repaired rules must generalize
  to any quoted title / exact-anchor retrieval and any single-name resolve call.
- If Phase 2 shows no signal, do **not** escalate into more prompt churn. Move
  to the spend/pivot gate and reassess whether DIGIMON's custom controller is
  still the right place to invest.
