# ADR-016: Declarative Decision Tracing and Capability-Declared Agent Runtimes

Date: 2026-04-04

## Status

Proposed

## Informed By

1. [Plan #29: Declarative Decision Tracing And Modular Agent Runtime](../plans/29_declarative_decision_tracing_and_modular_agent_runtime.md)
2. [Decision Trace And Modular Agent Runtime Research](../reports/2026-04-04_decision_trace_and_modular_agent_runtime_research.md)
3. [Recursive Reasoning Trace System — Design Document](../RECURSIVE_REASONING_TRACE.md)
4. `/home/brian/projects/llm_client/docs/adr/0010-cross-project-runtime-substrate.md`
5. `/home/brian/projects/llm_client/docs/adr/0007-observability-contract-boundary.md`
6. `/home/brian/projects/onto-canon6/docs/adr/0013-start-stable-identity-with-promoted-entity-identities-alias-membership-and-explicit-external-reference-state.md`
7. `/home/brian/projects/onto-canon6/docs/adr/0014-replace-the-v1-semantic-stack-with-pack-driven-canonicalization-and-explicit-recanonicalization.md`

## Context

DIGIMON's current benchmark and helper-runtime work exposed a shared ecosystem
problem rather than a project-only one.

We need to diagnose agent failures in a way that shows:

1. what state the model saw;
2. what structured decision it returned;
3. what runtime controls changed the outcome;
4. where a good path diverged into a bad one.

At the same time, the ecosystem already has multiple agent/runtime forms:

- plain LLM calls;
- DIGIMON/MCP-style turn agents;
- Codex SDK/CLI and Claude Agent SDK workspace agents.

Those runtimes already partially converge through `llm_client`, but the common
contract is still implicit. Observability is also split between shared runtime
events and project-local debugging conventions.

Recent DIGIMON work also showed that some normalization/canonicalization value
already exists elsewhere in the ecosystem. `onto-canon6` has explicit alias,
identity, and recanonicalization patterns that could improve trace comparison if
used through a bounded adapter rather than by importing a large hot-path
dependency.

Finally, architecture decisions themselves have been too weakly linked to the
research and plan artifacts that informed them.

## Decision

Adopt a three-layer architecture for diagnosable agent runtimes.

### 1. Shared decision-trace substrate

The ecosystem will converge on a shared decision-trace substrate, with
`llm_client` as the intended long-term owner.

That shared layer should own:

1. typed decision-trace records and span linkage;
2. runtime/model/fallback provenance;
3. storage and query helpers;
4. renderers and diff/report helpers;
5. shared runtime declaration models.

### 2. Project-declared observability

Projects such as DIGIMON should not hand-roll fully bespoke tracing stacks, but
they also should not push project-specific state capture into shared
infrastructure.

Instead, each project should declare named decision points and the state it
wants captured through a bounded declaration surface such as:

- `DecisionPointSpec`
- input extractors
- output extractors
- mutation extractors
- validator extractors

### 3. Capability-declared agent runtimes

The common abstraction is not "all agents are the same." The common abstraction
is "all runtimes implement a minimal shared contract and declare their
capabilities honestly."

The runtime model starts with three classes:

1. **minimal agent**
   - one LLM call with typed input/output;
2. **turn agent**
   - repeated turns plus tool/runtime policy;
3. **workspace agent**
   - SDK/CLI runtime with workspace and longer-horizon tool use.

A plain LLM call is therefore treated as the minimal agent runtime, not as a
special case outside the agent model.

### 4. Mandatory `reasoning` fields remain useful but are not sufficient

Structured outputs should continue to carry required explanation/rationale
fields where that helps quality and diagnosis. But those fields do not replace
decision tracing. The primary diagnosis artifact is the combination of:

1. input snapshot;
2. decision payload;
3. runtime provenance;
4. post-decision mutation;
5. derived divergence analysis.

### 5. Bounded canonicalization reuse

`onto-canon6` canonicalization and identity patterns are approved as a source of
bounded reuse for offline trace/report normalization, including alias grouping
and canonical label mapping.

They are not approved as a default DIGIMON benchmark hot-path dependency under
this ADR.

### 6. ADRs must link their informing artifacts

Future architecture ADRs in this repo should include an `Informed By` section
that links the research, plan, and predecessor artifacts that motivated the
decision.

## Consequences

Positive:

1. DIGIMON gets a credible path from manual debugging to rendered causal
   decision traces.
2. The ecosystem gains a realistic shared runtime contract without flattening
   real backend differences.
3. Plain LLM calls, MCP loops, Codex SDK, and Claude Agent SDK can all be
   discussed as runtimes in the same family.
4. `onto-canon6` reuse is made explicit and bounded instead of remaining a
   vague integration idea.
5. Future ADRs become easier to audit because their source reasoning is linked.

Negative:

1. This decision adds one more explicit abstraction layer and therefore some
   design overhead.
2. The first proving slice will still be DIGIMON-specific before the shared
   layer is fully extracted.
3. Capability-declared runtimes are more honest than a fake uniform surface,
   but they are also more complex to design and document.
4. Offline canonicalization adapters may add another step to diagnosis tooling.

## Follow-On

1. Implement the first concrete contract slice under Plan #29.
2. Use DIGIMON as the proving-ground consumer.
3. Open the shared-infra implementation plan in `llm_client` once the DIGIMON
   declaration surface is concrete enough.
