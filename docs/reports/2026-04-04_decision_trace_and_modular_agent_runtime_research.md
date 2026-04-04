# Decision Trace And Modular Agent Runtime Research

**Date:** 2026-04-04
**Status:** Informing research for ADR-016 and Plan #29
**Scope:** DIGIMON as proving ground; `llm_client` as likely long-term shared owner

## Question

How should the ecosystem expose enough observability to diagnose agent failures
without turning raw model self-talk into the primary artifact, and can agent
backends be treated as modular shared infrastructure across projects?

## Why This Matters Now

Recent DIGIMON benchmark work exposed three related gaps:

1. helper-model fallbacks can now happen inside DIGIMON, but nested helper
   fallback provenance is not yet surfaced at the per-question benchmark layer;
2. DIGIMON already runs against multiple backend families (`direct`, Codex SDK,
   Claude Agent SDK, MCP loop), but the project-facing runtime contract is
   still implicit and uneven;
3. debugging failures such as `619265` requires reconstructing what the model
   saw, what it decided, and how runtime control changed the result, not just
   reading the final answer or a free-text rationale field.

This is not a DIGIMON-only concern. It is a shared agentic-ecosystem concern.

## Artifacts Reviewed

### DIGIMON

- `CLAUDE.md`
- `docs/RECURSIVE_REASONING_TRACE.md`
- `docs/plans/28_truthful_overnight_stabilization_and_contract_repair.md`
- `Core/Provider/LLMClientAdapter.py`
- `eval/run_agent_benchmark.py`
- `digimon_mcp_stdio_server.py`
- `CURRENT_STATUS.md`
- `KNOWLEDGE.md`

### Shared Infra

- `/home/brian/projects/llm_client/docs/adr/0010-cross-project-runtime-substrate.md`
- `/home/brian/projects/llm_client/docs/adr/0007-observability-contract-boundary.md`
- `/home/brian/projects/llm_client/docs/guides/codex-integration.md`
- `/home/brian/projects/llm_client/llm_client/agent/mcp_state.py`
- `/home/brian/projects/llm_client/llm_client/io_log.py`

### onto-canon6

- `/home/brian/projects/onto-canon6/docs/CONSUMER_INTEGRATION_NOTES.md`
- `/home/brian/projects/onto-canon6/docs/adr/0013-start-stable-identity-with-promoted-entity-identities-alias-membership-and-explicit-external-reference-state.md`
- `/home/brian/projects/onto-canon6/docs/adr/0014-replace-the-v1-semantic-stack-with-pack-driven-canonicalization-and-explicit-recanonicalization.md`
- `/home/brian/projects/onto-canon6/config/config.yaml`

## Findings

### 1. A mandatory `reasoning` field is useful but insufficient

It should stay, but it does not solve the real diagnosis problem on its own.

It can explain one decision in the model's own words, but it does not capture:

- exact input state shown to the model;
- fallback or retry behavior;
- validator or tool rejection;
- post-decision state mutation;
- cross-turn divergence.

The useful diagnostic unit is therefore not "raw reasoning transcript." It is
**decision provenance**:

- input state;
- model decision payload;
- runtime control effects;
- derived divergence analysis.

### 2. DIGIMON already has the right proving-ground shape

DIGIMON is already close to the needed architecture:

- `eval/run_agent_benchmark.py` supports multiple backend families;
- `LLMClientAdapter` already turns shared `llm_client` calls into DIGIMON's
  legacy `BaseLLM` contract;
- `docs/RECURSIVE_REASONING_TRACE.md` already identifies operator calls,
  evidence, answers, and drivers as first-class trace objects.

What is missing is not the core idea. What is missing is:

- a shared trace envelope;
- project-declared extraction of project context;
- rendered diagnostic views and diffs.

### 3. `llm_client` is the right long-term owner for the shared layer

`llm_client` ADR-0010 already declares it the cross-project runtime and
observability substrate. That makes it the right eventual home for:

- trace/span envelopes;
- parent-child linkage;
- model retry/fallback provenance;
- storage and query helpers;
- rendering and diffing surfaces.

DIGIMON should prove the shape, but should not become the permanent owner of
generic trace plumbing.

### 4. Project-specific observability should be declarative, not hardcoded

The useful DIGIMON-specific data is real, but it should not force DIGIMON-only
logic into shared infrastructure.

The correct pattern is:

- shared infra defines `DecisionTraceRecord`, `DecisionTraceSpan`,
  `AgentRuntimeSpec`, and a registry;
- projects register `DecisionPointSpec`s that say what extra state to snapshot
  at named decision points;
- shared infra persists and renders the records uniformly.

For DIGIMON this would cover points such as:

- `semantic_plan.draft`
- `semantic_plan.revise`
- `atom_completion`
- `bridge_decision`
- `submit_answer`
- `todo_mutation`

### 5. "Treat normal LLM calls as the minimal agent" is realistic and useful

This idea is directionally correct, with one refinement.

The shared abstraction should not be "everything is the same agent." It should
be "everything implements the same minimal runtime contract plus declared
capabilities."

Recommended runtime classes:

1. **Minimal agent**
   - one LLM call, typed input/output, no tool loop required
   - examples: extraction call, judge call, planner call
2. **Turn agent**
   - repeated LLM turns plus tool loop over a bounded runtime policy
   - examples: DIGIMON benchmark agent, MCP loop
3. **Workspace agent**
   - external SDK/CLI agent with filesystem, shell, and long-horizon tool use
   - examples: Codex SDK/CLI, Claude Code SDK

All three can share:

- runtime declaration;
- capability flags;
- observability contract;
- result envelope;
- budget and provenance policy.

They should **not** be forced into identical behavior when capabilities differ.

### 6. A common runtime contract is realistic; a fully uniform backend surface is not

Seamless project declaration through `llm_client` is realistic if the contract
is thin:

- `AgentRuntimeSpec`
- `AgentCapabilitySet`
- `AgentExecutionRequest`
- `AgentExecutionResult`

It is not realistic if the contract assumes every backend has:

- the same tool-calling grammar;
- the same approval semantics;
- the same workspace access;
- the same streaming and interruption behavior.

So the correct shared design is:

- common submission contract;
- backend-specific capability declaration;
- project policy chooses acceptable capabilities.

### 7. onto-canon6 has reusable pieces, but only as bounded adapters

The most reusable `onto-canon6` value here is not its whole runtime. It is its
bounded canonicalization discipline:

- explicit stable identity records;
- explicit alias membership;
- auditable canonicalization and recanonicalization events;
- configurable exact/fuzzy/LLM resolution strategies.

That is useful for **trace normalization and cross-run diagnosis**, for example:

- normalizing agent/backend names across runs;
- canonicalizing decision-point labels and evidence entity mentions;
- grouping equivalent aliases in diagnostic reports.

It is **not** a reason to import the full `onto-canon6` canonical graph runtime
into DIGIMON's hot retrieval path.

Recommended reuse boundary:

- offline trace/report canonicalization first;
- optional evidence/entity alias normalization second;
- no mandatory hot-path dependency unless a later benchmark proves value.

### 8. ADRs should explicitly link to the research and plan artifacts that informed them

This should become policy.

The current ecosystem often has the right analysis but the linkage is too
implicit. For architecture work, each ADR should include an `Informed By`
section pointing at:

- the research note or investigation;
- the execution plan;
- relevant predecessor ADRs;
- key benchmark or runtime artifacts when applicable.

This keeps decision history reviewable and reduces "narrative drift."

## Proposed Shared Contracts

### Decision trace substrate

```text
DecisionTraceRecord
  trace_id
  span_id
  parent_span_id
  project
  run_id
  question_id
  decision_point
  actor_kind
  requested_runtime
  actual_runtime
  requested_model
  actual_model
  fallback_used
  input_snapshot_ref
  output_snapshot_ref
  mutation_snapshot_ref
  validator_result
  started_at
  finished_at
  latency_ms
  tags
```

### Project declaration surface

```text
DecisionPointSpec
  name
  description
  input_extractors[]
  output_extractors[]
  mutation_extractors[]
  validator_extractors[]
  canonicalization_policy
  render_hints
```

### Agent runtime declaration surface

```text
AgentRuntimeSpec
  runtime_id
  runtime_kind            # minimal | turn | workspace
  backend_family          # litellm | codex | claude-sdk | mcp | custom
  capability_flags[]
  default_model
  fallback_models[]
  tool_transport
  approval_mode
  observability_policy
```

## Recommended Make Surfaces

Project-local wrappers over shared CLI:

- `make trace QUESTION=<id> RUN=<artifact>`
- `make trace-diff QUESTION=<id> RUN_A=<artifact> RUN_B=<artifact>`
- `make diagnose QUESTION=<id>`
- `make runtime-report RUN=<artifact>`

These should produce:

- JSON trace artifact;
- Markdown diagnostic summary;
- notebook/HTML render when requested.

## Alternatives Considered

### 1. Just require a mandatory reasoning field everywhere

Rejected as the whole solution. Keep it, but it is not enough.

### 2. Let every project invent its own tracing format

Rejected. This repeats infrastructure and blocks cross-project diagnostics.

### 3. Move DIGIMON-specific observability into `llm_client` directly

Rejected. Shared infra should own the engine, not project-specific state
extractors.

### 4. Import `onto-canon6` wholesale into DIGIMON now

Rejected. Too much hot-path complexity for a still-unproven benchmark value
case.

## Recommendation

Adopt a three-layer architecture:

1. **shared substrate in `llm_client`**
2. **project-declared decision points in DIGIMON**
3. **optional offline canonicalization adapters informed by `onto-canon6`**

Treat DIGIMON as the proving ground for the first real slice, but keep the
ownership boundary honest: once the contract is validated, generic pieces move
to shared infrastructure.

## Open Questions

1. Should decision trace storage live only in existing observability tables, or
   should it add a new typed trace table?
2. How much of the trace artifact should be stored inline versus as referenced
   JSON blobs?
3. Should capability declarations live beside model policies, or in a new
   agent-runtime registry?
4. At what point does offline alias normalization justify a bounded
   `onto-canon6` adapter package?
