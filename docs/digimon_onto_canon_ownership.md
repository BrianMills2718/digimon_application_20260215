# DIGIMON vs onto-canon6 Ownership Overlap

**Created:** 2026-04-04
**Purpose:** Explicit inventory of areas where DIGIMON and onto-canon6 share,
duplicate, or have ambiguous ownership. This document records the current state
only — it does not propose future changes (see Plan #23 for that work).

**Related plan:** `docs/plans/23_semantic_build_boundary_and_onto_canon_experiment.md`

---

## Background

DIGIMON and onto-canon6 started as distinct systems with clear roles:

- **onto-canon6** — governed-assertion middleware: takes candidate assertions,
  reviews them, promotes durable semantic state (canonical entities, aliases,
  provenance, epistemic confidence).
- **DIGIMON** — composable retrieval engine: builds retrieval-oriented graphs
  from text, exposes 28 typed operators, runs adaptive benchmark evaluation.

As onto-canon6 matured and DIGIMON added identity-hardening work (Plan #22),
the two systems now overlap in several areas. This document enumerates those
overlaps, describes the current state, and notes the resulting issues.

---

## Area 1: Entity Identity and Canonicalization

### Current State

**onto-canon6** owns the canonical identity infrastructure:
- `CanonicalGraphService` / `CanonicalGraphStore` manage promoted entity
  records with `entity_id` (slug), `entity_type`, and
  `first_candidate_id` provenance.
- The identity subsystem resolves aliases, merges duplicates, and tracks
  canonical clusters across source documents.
- Epistemic confidence scores are stored per candidate assertion and per
  entity in `epistemic_confidence_assessments`.

**DIGIMON** independently implements entity identity and canonicalization:
- `Core/Common/entity_name_hygiene.py` provides Unicode normalization,
  fuzzy match scoring, and canonical display-name separation
  (`build_identity_payload`).
- The `onto_canon_import.py` importer further applies `build_identity_payload`
  to entities received from onto-canon6, meaning onto-canon6's canonical
  identity is re-processed through DIGIMON's own normalization layer.
- Plan #22 extended DIGIMON's graph builders to store a separate canonical
  display name and normalized lookup key for each node — functionality that
  parallels onto-canon6's entity resolution model.

### Issues
- **Duplicate normalization stack.** When onto-canon6 entities are imported
  into DIGIMON, they pass through two independent normalization layers: once
  during onto-canon6's extraction/promotion pipeline, and again via
  `build_identity_payload` during import. The two layers may produce different
  canonical forms or scoring signals.
- **Alias loss.** The current flat JSONL seam discards onto-canon6's alias
  cluster and canonical-cluster membership. DIGIMON's importer receives only
  the primary human-readable name, not the full alias set, so its fuzzy-match
  infrastructure cannot use the richer resolution data that onto-canon6 already
  owns.
- **Parallel maintenance burden.** Both projects must maintain separate entity
  identity logic. A bug fix or improvement to one side does not automatically
  benefit the other.

---

## Area 2: Entity Type Vocabulary

### Current State

**onto-canon6** manages a governed ontology runtime (`ontology_runtime/`):
- Ontology packs define canonical entity type CURIEs with `oc:` and `sumo:`
  namespaces (e.g. `oc:Organization`, `sumo:Person`).
- Entity type validation, overlay application, and type-driven behavior are
  centralized in onto-canon6.

**DIGIMON** operates with an open or schema-guided entity type vocabulary:
- Operators accept `entity_type` as a free string field.
- `Core/Schema/SlotTypes.py` defines `EntityRecord.entity_type` as a plain
  `str` with no vocabulary constraint.
- Graph-building prompts may produce arbitrary entity type strings depending on
  extraction mode (`open`, `schema_guided`, `schema_constrained`), and those
  strings are stored and used for VDB partitioning.

When onto-canon6 entities are imported, the `entity_type` field is mapped
directly from the exported CURIE. DIGIMON's operators receive the CURIE string
but are unaware of the ontology tree, so type-based filtering or
type-constrained traversal treats `oc:Organization` as an opaque label
rather than a structured ontology node.

### Issues
- **Vocabulary mismatch.** DIGIMON-native builds may produce `entity_type`
  values like `"organization"`, `"person"`, or `"ORG"`, while onto-canon6
  imports produce `"oc:Organization"`, `"sumo:Person"`, etc. Queries that
  filter by entity type cannot span both populations.
- **No ontology hierarchy.** DIGIMON has no mechanism to treat
  `oc:Organization` as a supertype of `oc:Company`; each type string is an
  isolated label.

---

## Area 3: Relationship / Assertion Representation

### Current State

**onto-canon6** represents relationships as *promoted assertions* in a
structured schema:
- Each assertion has a `predicate`, an `assertion_id`, a claim text, role
  fillers (ARG0/ARG1 typed as entity or value), epistemic confidence, and
  provenance back to the source candidate.
- Directed structure: ARG0 is source, ARG1 is target.
- Relationships carry assertion-level lineage (candidate assertion ID, review
  decision, confidence).

**DIGIMON** represents relationships as undirected graph edges:
- `RelationshipRecord` fields: `src_id`, `tgt_id`, `relation_name`,
  `description`, `weight`, `keywords`, `source_id`.
- `_merge_relationships` in `onto_canon_import.py` collapses directed
  ARG0→ARG1 pairs into sorted, undirected endpoint tuples.
- Multiple relationships between the same entity pair are merged into a single
  edge (keyword and description fields are joined with `<SEP>`).

### Issues
- **Directionality loss.** onto-canon6 encodes directed predicate structure
  (ARG0→predicate→ARG1). The current import converts to undirected edges via
  `sorted((src_id, tgt_id))`. Traversal operators that depend on edge direction
  cannot use the richer directional information from onto-canon6.
- **Assertion-level lineage dropped.** The assertion ID, review decision, and
  epistemic confidence (beyond a scalar `weight`) are not preserved in the
  DIGIMON graph edge. Operators have no path back to onto-canon6 provenance at
  query time.
- **Many-to-one merge.** Multiple distinct assertions between the same entity
  pair (different predicates, different claim texts) are collapsed into one edge
  with concatenated fields. This loses assertion granularity.
- **Single-endpoint relationships skipped.** onto-canon6 exports relationships
  with empty `tgt_id` for single-argument predicates. The DIGIMON importer
  skips these (16 were skipped in the 2026-03-31 Shield AI verified run),
  silently dropping information.

---

## Area 4: Graph Build / Extraction Pipeline

### Current State

**onto-canon6** runs a full extraction and governance pipeline:
- LLM-based extraction → review → promotion. Extracts entities and assertions
  from text with `gemini/gemini-2.5-flash` by default.
- Handles duplicate review, epistemic tension, and supersession.
- Schema-guided extraction modes (`open`, `schema_guided`, `schema_constrained`)
  are parameterized through config and ontology packs.

**DIGIMON** also runs its own LLM-based extraction pipeline:
- `ERGraph` / `RKGraph` build pipelines extract entities and relationships
  from document chunks using LLM prompts.
- Has its own extraction prompt templates, schema modes, and config flags.
- Checkpointing, per-chunk isolation, and fallback chain are DIGIMON-local.

Both pipelines target the same class of input (document text) and produce the
same conceptual output (entities and relationships). They differ in governance
machinery (onto-canon6) vs. retrieval orientation (DIGIMON).

### Issues
- **Parallel extraction stacks.** A corpus must be processed twice — once by
  onto-canon6 for governed promotion, and once by DIGIMON for benchmark-graph
  building — if both representations are needed. There is no shared extraction
  output that satisfies both.
- **No reuse of onto-canon6 extraction output in DIGIMON's default lane.** The
  current benchmark lane uses DIGIMON-native extraction. The governed
  onto-canon6 extraction output is only usable via the thin JSONL import seam,
  which is not the default benchmark path.
- **Independent prompt maintenance.** Both systems maintain separate extraction
  prompts and schema iteration processes. Improvements to one side do not
  propagate.

---

## Area 5: Passage / Chunk Evidence

### Current State

**onto-canon6** stores assertion source lineage back to candidate assertions
and, through those, to source documents. It does not natively build
passage-level graph nodes for retrieval.

**DIGIMON** builds passage-level graph nodes via the `Passage`-type graph
builders and `augment_chunk_cooccurrence` enrichment. These nodes are central
to operators like `chunk.from_relation`, `chunk.occurrence`, and `chunk.vdb`.

The current JSONL export from onto-canon6 carries no passage node structure.
Imported graphs have no chunk/passage layer and cannot use chunk-based
operators.

### Issues
- **Passage gap in imported graphs.** Graphs imported from onto-canon6 only
  contain entity and relationship nodes; they cannot drive chunk-based retrieval
  operators. Any benchmark run against an onto-canon6-backed graph is
  structurally limited to entity/relationship operators.
- **Claim text is the only evidence.** The `description` field on DIGIMON
  relationship records is populated with onto-canon6's `claim_text`. This is a
  narrow, assertion-shaped evidence form, not the full document passage that
  chunk operators are designed to work with.

---

## Area 6: Graph Storage Format

### Current State

**onto-canon6** stores the promoted graph in SQLite (`CanonicalGraphStore`):
- Tables: `promoted_graph_entities`, `promoted_graph_assertions`,
  `promoted_graph_role_fillers`, `epistemic_confidence_assessments`.
- Queries through `CanonicalGraphService` and `CanonicalGraphStore` using
  typed Python dataclasses.

**DIGIMON** stores graphs as GraphML files on disk (NetworkX `nx_data.graphml`):
- All operators load the graph from the GraphML artifact at query time.
- Vector databases (FAISS) are separate artifacts built per dataset.

The two storage formats are incompatible at runtime. DIGIMON operators cannot
query into onto-canon6's SQLite graph directly; the JSONL export/import round
trip is required to materialize a DIGIMON-compatible artifact.

### Issues
- **Round-trip latency.** Any update to the onto-canon6 governed graph requires
  a full re-export and re-import to become visible to DIGIMON operators. There
  is no incremental sync.
- **No live query across the boundary.** DIGIMON operators cannot reach into
  onto-canon6's epistemic metadata (confidence scores, supersession history,
  review decisions) at query time. That information is lost after the JSONL
  round-trip.

---

## Summary Table

| Area | Owned by onto-canon6 | Owned by DIGIMON | Overlap / Gap |
|------|---------------------|-----------------|---------------|
| Entity identity + alias resolution | Yes — full cluster/alias model | Yes — `entity_name_hygiene.py`, Plan #22 extensions | Duplicate normalization; alias cluster not passed through |
| Entity type vocabulary | Yes — CURIE namespaces, ontology packs | Partial — free string, no hierarchy | Type strings incompatible across native and imported graphs |
| Relationship/assertion representation | Yes — directed, role-structured, with provenance | Yes — undirected edge + flat fields | Directionality and assertion lineage lost at import |
| Graph extraction pipeline | Yes — governed extraction + review | Yes — benchmark-native extraction | Parallel stacks; no shared extraction output |
| Passage / chunk evidence | No — not built | Yes — passage nodes, cooccurrence, chunk VDB | Imported graphs cannot use chunk operators |
| Graph storage / runtime | SQLite (onto-canon6 schema) | GraphML (NetworkX on disk) | No live cross-boundary query; round-trip only |

---

## Notes on Current Coupling Mechanism

The only implemented bridge is the thin JSONL seam:

```
onto-canon6 repo root:
  onto-canon6 export-digimon  →  entities.jsonl + relationships.jsonl

DIGIMON repo root:
  python scripts/import_onto_canon_jsonl.py  →  nx_data.graphml
```

- **Verified** on the Shield AI promoted graph (2026-03-31): 110 entities,
  99 relationships exported → 110 nodes, 78 edges imported (16 single-endpoint
  relationships skipped).
- This seam is explicitly classified as v1 proof-of-life only, not a long-term
  interchange contract. See Plan #23 for the comparison against richer options.
- The seam is one-way (onto-canon6 → DIGIMON). DIGIMON has no write path back.
