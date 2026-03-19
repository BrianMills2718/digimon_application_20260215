# DIGIMON V2 Greenfield Architecture

## Product Goals

1. **Generalized GraphRAG System**
   Build a graph-native research system that extends the JayLZhou-style idea set: composable graph builds, composable retrieval operators, reference methods expressed as operator plans, and evaluation on real corpora.

2. **Ecosystem Interoperability**
   Let DIGIMON fit cleanly into the wider project ecosystem without surrendering its graph-native center. Interop happens through explicit projections and artifacts, not by forcing DIGIMON to become an ontology store.

3. **Fail-Loud Operability**
   Every phase must prefer explicit validation, typed contracts, and observable state changes over hidden fallbacks.

## Non-Goals

- Preserve legacy DIGIMON execution paths.
- Make assertion IR the internal source of truth for DIGIMON v2.
- Ship a UI before the graph build and operator runtime are stable.
- Support every historical experiment in the first executable release.
- Add silent compatibility shims for broken configurations or missing capabilities.

## Design Principles

1. **Graph-first internally, interop-capable at boundaries**
   DIGIMON v2 owns graph construction, graph retrieval, and graph-native method composition.

2. **Top-down design**
   Requirements drive the domain model; the domain model drives schema; schema drives implementation.

3. **Capabilities over named special cases**
   Operators and methods bind to graph capabilities and artifact contracts, not to ad hoc `if graph_type == ...` branches.

4. **Prompts as data**
   Extraction and synthesis prompts live in YAML/Jinja2 templates, not embedded Python strings.

5. **One execution engine**
   CLI, MCP, HTTP, and benchmarks all execute through the same runtime path.

6. **Projection, not collapse**
   DIGIMON exports graph artifacts into other ecosystem representations when needed, but it does not collapse its core into those representations.

## Domain Model

### Core Objects

- **`GraphBuildProfile`**
  Declares the graph family to build, extracted attribute set, ontology policy, canonicalization policy, and storage/runtime requirements.

- **`OntologyPolicy`**
  Controls extraction constraint mode and validation mode. At minimum: `open`, `closed`, `mixed`. Future extension: profile packs and severity routing.

- **`GraphArtifact`**
  The persisted result of a build. Contains graph metadata, build manifest, evidence links, and capability summary.

- **`GraphCapabilitySet`**
  Machine-checkable capabilities exposed by a graph artifact. Examples: `has_entity_types`, `has_edge_keywords`, `supports_ppr`, `supports_communities`, `supports_reified_events`.

- **`OperatorDescriptor`**
  Typed description of what an operator consumes, produces, costs, and requires.

- **`MethodPlan`**
  An ordered operator chain with explicit wiring, validation rules, and benchmark identity.

- **`ProjectionArtifact`**
  An export view derived from a graph artifact. Examples: assertion set, table projection, evidence packet, benchmark trace.

### Supported Graph Families

- `chunk_tree`
- `passage_graph`
- `kg`
- `tkg`
- `rkg`
- `reified_event_graph`

### Ontology and Constraint Posture

- **Open mode**
  Explore freely. Accept novel types and relations.

- **Closed mode**
  Extract only from approved vocabularies and fail validation on out-of-schema output.

- **Mixed mode**
  Prefer approved vocabularies, allow proposals, and record them explicitly for review.

These policies apply to graph builds. They do not force DIGIMON to use a non-graph-native internal model.

## System Architecture

### Layer 1: Configuration and Contracts

- `config/config.yaml`
- Pydantic settings and models
- graph profile definitions
- acceptance-gate contracts

### Layer 2: Build Runtime

- corpus ingestion
- chunking
- extraction prompts
- graph construction
- post-build canonicalization and validation

### Layer 3: Retrieval Runtime

- operator registry
- capability validator
- chain planner
- method execution engine

### Layer 4: Projection and Integration

- graph-to-assertion projection
- graph-to-table projection
- evidence/provenance exports
- benchmark trace artifacts

### Layer 5: Interfaces

- CLI
- MCP
- HTTP
- benchmark harness

All interfaces call Layer 3. None may bypass it.

## Phased Delivery

### Phase 0: Planning Foundation

**Purpose**
Freeze requirements, architecture, and acceptance gates before implementation.

**Deliverables**
- architecture blueprint
- design-phase plan
- machine-readable gate
- config-driven validator
- execution evidence report

**Acceptance Criteria**
- Planning artifacts exist in repo.
- Validator passes and writes evidence.
- Validator failure mode is loud for missing or malformed artifacts.

**Exit Evidence**
- `python scripts/validate_digimon_v2_planning_phase.py`
- `pytest --noconftest tests/unit/test_validate_digimon_v2_planning_phase.py -v --junitxml=docs/reports/digimon_v2_planning_phase_pytest.xml`

### Phase 1: Executable Kernel

**Purpose**
Establish the smallest runnable DIGIMON v2 package with strict config loading and typed domain models.

**Deliverables**
- `pyproject.toml`
- package skeleton
- config loader from `config/config.yaml`
- Pydantic models for core objects
- structured logging bootstrap

**Acceptance Criteria**
- Missing or invalid config fails at startup with actionable errors.
- Core models validate under real tests.
- `mypy --strict` passes on the new package.
- No legacy imports from current DIGIMON runtime remain in the v2 package.

**Exit Evidence**
- `pytest tests/unit/test_config.py tests/unit/test_models.py -v`
- `mypy --strict digimon_v2/`

### Phase 2: Graph Build Engine

**Purpose**
Implement graph-family builds and post-build validation without query-time complexity.

**Deliverables**
- graph build profiles
- prompt templates in `prompts/`
- graph artifact manifest
- canonicalization/validation pipeline

**Acceptance Criteria**
- At least `kg`, `tkg`, `rkg`, and `reified_event_graph` build from the same runtime.
- Build outputs include capability summaries and evidence references.
- Closed and mixed ontology modes fail loudly on invalid output.

**Exit Evidence**
- corpus-backed integration tests with real sample data
- build manifest snapshots committed as test fixtures

### Phase 3: Operator Runtime

**Purpose**
Implement typed operators and the single execution engine.

**Deliverables**
- operator registry
- capability validator
- chain validator
- runtime executor

**Acceptance Criteria**
- Operators declare required artifacts and required capabilities.
- Invalid plans fail before execution.
- A valid chain executes end-to-end through one runtime path.

**Exit Evidence**
- `pytest tests/integration/test_operator_runtime.py -v`
- runtime logs showing pre-execution validation and output registration

### Phase 4: Reference Methods

**Purpose**
Encode named GraphRAG methods as `MethodPlan` definitions on top of the operator runtime.

**Deliverables**
- reference plans for core JayLZhou-style methods
- method metadata
- benchmarkable method catalog

**Acceptance Criteria**
- Each method is represented as data, not hidden Python branching.
- At least one local-search, one global/community, one entity-centric, and one reified-event workflow run through the same executor.
- Method outputs are benchmark-traceable.

**Exit Evidence**
- corpus-backed benchmark smoke runs
- method catalog artifact committed in repo

### Phase 5: Projection and Ecosystem Interop

**Purpose**
Add boundary projections so DIGIMON v2 can feed other projects without changing its core.

**Deliverables**
- graph-to-assertion projection
- graph-to-table projection
- evidence packet export
- projection validation tests

**Acceptance Criteria**
- Projection artifacts are deterministic for fixed input graphs.
- Projected artifacts preserve evidence references and capability provenance.
- DIGIMON internals remain graph-first; no dual-write requirement is introduced.

**Exit Evidence**
- projection fixtures and round-trip tests
- exported artifacts inspected by real tests, not mocks

### Phase 6: Unified Interfaces

**Purpose**
Expose the runtime through CLI, MCP, and HTTP without forking behavior.

**Deliverables**
- CLI
- MCP surface
- HTTP API
- shared request/response models

**Acceptance Criteria**
- All interfaces call the same execution engine.
- Interface-level errors preserve underlying failure causes.
- Tool surface is task-oriented and small enough for agent use.

**Exit Evidence**
- interface smoke tests
- one end-to-end scenario per interface

### Phase 7: Hardening and Evaluation

**Purpose**
Lock the repo into a maintainable, benchmarkable, observable release posture.

**Deliverables**
- benchmark suite
- documentation pack
- operator/method coverage report
- packaging and install docs

**Acceptance Criteria**
- Benchmark runs are reproducible from repo instructions.
- Documentation names one canonical architecture and one canonical execution path.
- Acceptance gates exist for major shipped capabilities.

**Exit Evidence**
- benchmark run artifacts
- doc-coupling validation
- release checklist

## Success Criteria by Phase

| Phase | Success means |
|------|---------------|
| Phase 0 | The rebuild plan is explicit, machine-checkable, and verified by execution |
| Phase 1 | The new package boots with strict config and typed contracts |
| Phase 2 | Graph builds work across graph families with fail-loud ontology policy |
| Phase 3 | Operators run through one validated engine |
| Phase 4 | Named methods are data-defined and benchmarkable |
| Phase 5 | DIGIMON exports ecosystem-friendly artifacts without losing graph identity |
| Phase 6 | CLI, MCP, and HTTP are thin shells over the same runtime |
| Phase 7 | The system is observable, reproducible, and documented as one coherent product |

## Phase 0 Exit Evidence

The planning phase is complete when all three are true:

1. `docs/plans/02_digimon_v2_greenfield_planning_phase.md` exists and is internally complete.
2. `acceptance_gates/digimon_v2_planning_phase.yaml` validates against the planning package.
3. `docs/reports/digimon_v2_planning_phase_evidence.json` is generated by execution and confirms all required checks passed.

## Open Questions

1. Whether DIGIMON v2 should eventually move into its own repo once Phase 1 starts.
2. Whether community/global-search operators belong in Phase 3 or should wait until Phase 4.
3. Whether assertion projection should target a DIGIMON-owned schema first or align immediately to the wider ecosystem IR.
