# Plan #29: Declarative Decision Tracing And Modular Agent Runtime

**Status:** Planned
**Type:** architecture + implementation planning
**Priority:** High
**Blocked By:** None
**Blocks:** trustworthy per-question diagnosis, backend portability, shared agent-runtime convergence

---

## Gap

**Current:**

DIGIMON can already run benchmark agents across multiple backend families and
can already route helper/model work through `llm_client`. But three important
capabilities are still incomplete:

1. **Decision diagnosis is too manual.**
   We can inspect artifacts, logs, and prompts, but there is no standard
   per-decision trace artifact that shows:
   - what input state the model saw;
   - what decision it produced;
   - what runtime control effects changed the result.

2. **Runtime modularity is real but implicit.**
   DIGIMON already supports `direct`, Codex SDK, Claude Agent SDK, and MCP-loop
   style execution, but projects do not yet declare those runtimes through one
   shared contract with capability flags.

3. **Cross-project reuse is under-specified.**
   `llm_client` already owns shared runtime and observability. `onto-canon6`
   already owns bounded identity/canonicalization value. DIGIMON already owns a
   live proving-ground benchmark. The ownership boundary for the next layer is
   not yet explicit.

**Target:**

1. Define a shared decision-trace contract that can become `llm_client`
   infrastructure.
2. Define a project-declared observability seam so DIGIMON can expose its own
   decision state without hardcoding DIGIMON internals into shared infra.
3. Define an agent-runtime declaration model that can represent:
   - plain LLM calls as minimal agents,
   - DIGIMON/MCP tool loops as turn agents,
   - Codex/Claude SDK-style workspace agents as richer runtimes.
4. Define a bounded reuse path for `onto-canon6` canonicalization as an offline
   normalization adapter rather than a hot-path dependency.

---

## Why This Matters

Without a diagnostic trace, "why did this question fail?" keeps collapsing into
hand inspection and narrative guesswork. Without a modular runtime declaration,
projects keep knowing that a backend exists without having a truthful,
capability-based contract for using it. Both are core ecosystem problems, not
just DIGIMON problems.

This plan exists to turn that into a deliberate architecture instead of a pile
of local fixes.

---

## References Reviewed

- `docs/reports/2026-04-04_decision_trace_and_modular_agent_runtime_research.md`
- `docs/RECURSIVE_REASONING_TRACE.md`
- `docs/plans/28_truthful_overnight_stabilization_and_contract_repair.md`
- `CLAUDE.md`
- `CURRENT_STATUS.md`
- `Core/Provider/LLMClientAdapter.py`
- `eval/run_agent_benchmark.py`
- `/home/brian/projects/llm_client/docs/adr/0010-cross-project-runtime-substrate.md`
- `/home/brian/projects/llm_client/docs/adr/0007-observability-contract-boundary.md`
- `/home/brian/projects/onto-canon6/docs/CONSUMER_INTEGRATION_NOTES.md`
- `/home/brian/projects/onto-canon6/docs/adr/0013-start-stable-identity-with-promoted-entity-identities-alias-membership-and-explicit-external-reference-state.md`
- `/home/brian/projects/onto-canon6/docs/adr/0014-replace-the-v1-semantic-stack-with-pack-driven-canonicalization-and-explicit-recanonicalization.md`

---

## Pre-Made Decisions

1. **Shared ownership boundary**
   - `llm_client` is the intended long-term owner of the generic trace engine,
     persistence, query, and runtime-registry pieces.
   - DIGIMON is the first proving ground for the project-declared trace seam.

2. **Diagnostic philosophy**
   - a mandatory `reasoning` field remains useful but is not the sole or
     primary observability artifact;
   - the primary artifact is a typed decision trace with runtime provenance.

3. **Runtime abstraction**
   - plain LLM calls are treated as the minimal agent runtime;
   - richer runtimes extend the same contract via capability flags;
   - the abstraction is "common contract + declared capabilities," not "all
     backends behave identically."

4. **Canonicalization reuse boundary**
   - `onto-canon6` reuse is approved for offline trace/report normalization and
     alias grouping;
   - `onto-canon6` is not pulled into DIGIMON's benchmark hot path by default.

5. **ADR hygiene**
   - architecture ADRs must explicitly link the research and plan artifacts that
     informed them.

---

## Plan

### Steps

1. Establish the architecture package in DIGIMON: research note, ADR, and plan.
2. Define the shared decision-trace and runtime-declaration contracts clearly
   enough to move into `llm_client`.
3. Inventory DIGIMON's first instrumented decision points and their required
   input/output/mutation snapshots.
4. Define the `make` surfaces for trace generation, diffing, and diagnosis.
5. Use one real DIGIMON failure family as the proving slice before expanding to
   broader shared-infra implementation.
6. Keep `onto-canon6` reuse bounded to offline normalization unless later
   evidence justifies a hot-path dependency.

---

## Implementation Phases

### Phase 0 — Architecture Artifacts

Create the architecture package that makes the boundary explicit.

**Tasks**
- Write the informing research note.
- Write ADR-016.
- Register this plan and the ADR in the local indexes.
- Update ADR guidance so future ADRs include `Informed By`.

**Acceptance**
- Research note exists and is linked from ADR-016.
- ADR-016 exists and is linked from the ADR index.
- This plan exists and is linked from the plan index.
- ADR guidance now requires explicit linkage to informing artifacts.

### Phase 1 — Shared Contract Design

Define the concrete contracts that could move into shared infrastructure.

**Tasks**
- Specify `DecisionTraceRecord`.
- Specify `DecisionPointSpec`.
- Specify `AgentRuntimeSpec` and `AgentCapabilitySet`.
- Specify minimal required provenance fields for nested helper calls.

**Acceptance**
- The plan documents the contract fields and their ownership boundary.
- The contract is narrow enough to support direct LLM, MCP-turn, and SDK
  workspace runtimes without pretending they are identical.

### Phase 2 — DIGIMON Decision-Point Inventory

Map DIGIMON's actual runtime decisions onto the shared contract.

**Tasks**
- Enumerate the first DIGIMON decision points to instrument:
  - `semantic_plan.draft`
  - `semantic_plan.revise`
  - `atom_completion`
  - `bridge_decision`
  - `submit_answer`
  - `todo_mutation`
- Define the minimum input/output/mutation snapshots for each.
- Define which of those fields are safe to log directly versus by artifact
  reference.

**Acceptance**
- Each named decision point has:
  - purpose,
  - required input fields,
  - required output fields,
  - required mutation fields,
  - failure families it helps diagnose.

### Phase 3 — Shared Tooling Surface

Define how humans and agents will consume the trace artifact.

**Tasks**
- Define `make trace`, `make trace-diff`, `make diagnose`, and
  `make runtime-report`.
- Define machine-readable JSON output and human-readable Markdown output.
- Define notebook/HTML rendering as an optional presentation layer.

**Acceptance**
- Every planned command has:
  - input contract,
  - output contract,
  - expected consumer,
  - failure behavior.

### Phase 4 — First Proving Slice

Use one real DIGIMON failure family to validate the architecture.

**Tasks**
- Choose one anchor-preservation question and one helper-fallback question.
- Require the trace artifact to answer:
  - what the model saw,
  - what it decided,
  - whether fallback happened,
  - what mutation caused the divergence.
- Require a good-run/bad-run diff.

**Acceptance**
- One question-level trace diff can identify the first bad turn without reading
  raw logs end to end.
- Nested helper fallback events are visible in the diagnostic artifact.

### Phase 5 — Bounded Canonicalization Adapter Spike

Explore whether `onto-canon6` can improve cross-run trace comparability without
becoming a runtime dependency.

**Tasks**
- Define one offline normalization surface for:
  - agent/runtime aliases,
  - decision-point label aliases,
  - evidence entity aliases.
- Decide whether DIGIMON should consume this directly or wait for a shared
  adapter package.

**Acceptance**
- The decision is explicit:
  - use now as offline adapter,
  - defer,
  - or move to shared infra first.

---

## Failure Modes To Guard Against

1. Building a raw chain-of-thought dump instead of a causal decision trace.
2. Forcing Codex, Claude Code, MCP loops, and direct LLM calls into an
   unrealistically identical runtime contract.
3. Pulling `onto-canon6` canonicalization into DIGIMON's benchmark hot path
   before proving value.
4. Logging too much inline payload and making traces unreadable or too costly.
5. Treating fallback visibility as optional when diagnosing benchmark
   regressions.

---

## Verification

This plan is complete only when all of the following are true:

1. the architecture docs define the shared boundary truthfully;
2. DIGIMON decision points are enumerated concretely enough to implement;
3. the planned make surfaces are specific enough for an agent to execute;
4. reuse and non-reuse boundaries for `llm_client` and `onto-canon6` are
   explicit;
5. the architecture can explain how a plain LLM call fits as a minimal agent.

---

## Next 24 Hours

1. Complete the documentation package in this repo.
2. Use the package to scope the first shared-infra implementation slice in
   `llm_client`.
3. Use DIGIMON as the first proving-ground consumer rather than building the
   shared layer in the abstract.
