# Digimon Glossary

This glossary defines canonical extraction/rebuild terms used across code, plans, and ADRs.

## Schema Guidance Terms

- **`schema_mode`**: Controls how strongly extraction is constrained by declared entity/relation types.
  - `open`: No schema constraints are enforced in prompts.
  - `schema_guided`: Declared schema is preferred; novel types can still appear.
  - `schema_constrained`: Prompt should stay within the declared schema when lists are provided.
- **`schema_guidance`**: Human-readable shorthand for the same policy in prompt text.

## Compatibility Aliases (Input Surface Only)

- Historical values are accepted at parse points for stability but are non-authoritative:
  - `guided` → `schema_guided`
  - `mixed` → `schema_guided`
  - `closed` → `schema_constrained`
- Canonical values remain authoritative inside manifests, validators, and config models.

## Build and Evaluation Terms

- **`graph_profile`**: Canonical schema profile for entity graph builds (`KG`, `TKG`, `RKG`), independent of `schema_mode`.
- **`entity graph`**: The core KG/TKG/RKG family built by ER-style builders.
- **`profile slice`**: A graph artifact built for a specific `graph_profile` and `schema_mode` combination.
- **`artifact dataset`**: A build namespace (for example `MuSiQue_TKG_open`) that keeps produced artifacts isolated from source dataset artifacts.
- **`build manifest`**: Persisted contract describing exactly what a graph artifact contains and which retrieval tools are safely available.
- **`tool gating`**: Runtime filtering of retrieval operators or benchmarks based on manifest-supported capabilities.
- **`build capability`**: A capability that is part of the persisted artifact truth, such as topology, fields, provenance, or derived artifacts.
- **`runtime resource`**: A capability that depends on what is loaded or reachable in the current process, such as a loaded graph, VDB, chunk store, or sparse matrix set.
- **`operator requirement contract`**: The typed declaration of what a tool requires or prefers from build capabilities and runtime resources.
- **`applicability decision`**: The result of evaluating a tool contract against build capabilities and runtime resources.
- **`hard requirement`**: A requirement whose absence makes a tool unavailable.
- **`soft preference`**: A quality-improving condition whose absence should degrade a tool rather than hide it.
- **`degraded tool`**: A tool whose hard requirements are satisfied but whose soft preferences are not.
- **`unavailable tool`**: A tool whose hard requirements are not satisfied and therefore should not be exposed.

## Lane and Trust Terms

- **`pure lane`**: Build/execution path where fallback model lanes are disabled and single-model behavior is required.
- **`mixed-lane`**: Build/execution path where model fallbacks are allowed; useful for throughput, lower evidentiary strictness.
- **`closed artifact`**: Artifact built under constrained conditions (e.g., fixed prompts/model lanes, strict schema contracts).

## Open-TKG Type Policy Terms

- **`open-TKG`**: A TKG build configured with `schema_mode=open`.
- **`open-TKG type palette`**: The active declared type list for TKG prompts; this may be empty in fully open form or constrained to a specific subset.
- **`grounded entity`**: A candidate entity judged to be stable, nameable, and evidence-backed enough to appear in schema-rich or quality-focused runs.
