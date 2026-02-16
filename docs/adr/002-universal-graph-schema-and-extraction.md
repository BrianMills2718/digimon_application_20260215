# ADR-002: Universal Graph Schema and Configurable Extraction

**Status**: Proposed
**Date**: 2026-02-16
**Context**: DIGIMON currently has 5 graph types with hardcoded extraction prompts. Onto-canon defines a superset attribute schema. We need a unified architecture where graph type configuration drives extraction, ontology constraints, and post-build enrichment.

---

## Problem

Three independent problems that share a root cause:

1. **Extraction prompts are hardcoded Python strings** in `Core/Prompt/GraphPrompt.py`. Adding a new graph type or modifying extraction behavior requires editing Python code. Violates "Prompts as Data" principle.

2. **No ontology enforcement**. The `custom_ontology_path` config appends guidance text to prompts, but the LLM can ignore it. No validation, no closed-vocabulary enforcement, no mixed-mode "approved list + propose new" workflow.

3. **No n-ary relationships or reification**. All extraction produces binary `(source, relation, target)` tuples. Events involving 3+ participants are flattened into multiple binary edges that lose role information ("who did what to whom").

4. **No post-build enrichment pipeline**. Entity canonicalization, Q-code resolution, and schema validation are not part of the build process. The graph goes straight from raw LLM output to persistence.

## Decision

### 1. Attribute Schema: Onto-Canon as Superset

Every graph attribute lives in a single schema. Graph types are subsets.

**Node Attributes:**

| Attribute | Type | Source | Graph Types |
|-----------|------|--------|-------------|
| `name` | str | Extraction | All |
| `type` | str | Extraction | TKG, RKG, Reified |
| `description` | str | Extraction | TKG, RKG, Reified |
| `qcode` | str | Post-build enrichment | Any (optional) |
| `canonical_name` | str | Post-build canonicalization | Any (optional) |
| `source_ids` | list[str] | Extraction | All |

**Edge Attributes:**

| Attribute | Type | Source | Graph Types |
|-----------|------|--------|-------------|
| `relation_name` | str | Extraction | KG, RKG, Reified |
| `description` | str | Extraction | TKG, RKG, Reified |
| `weight` | float | Extraction | All |
| `keywords` | list[str] | Extraction | RKG |
| `source_ids` | list[str] | Extraction | All |
| `amr_predicate` | str | Post-build enrichment | Any (optional) |
| `probability` | float | Post-build enrichment | Any (optional) |

**Role Attributes (Reified graph type only):**

| Attribute | Type | Source |
|-----------|------|--------|
| `role` | str | Extraction (ARG0, ARG1, ARG2, ...) |
| `role_label` | str | Extraction (agent, patient, instrument, ...) |

### 2. Graph Type Configs Drive Prompt Selection

Each graph type is defined by a YAML config that specifies:

```yaml
# prompts/graph_types/tkg.yaml
graph_type: "tkg"
display_name: "Typed Knowledge Graph"

# Which attributes this graph type extracts
node_attributes: [name, type, description]
edge_attributes: [relation_name, description, weight]
reification: false

# Prompt template for extraction
extraction_template: "prompts/extraction/tkg_extraction.yaml"

# Prompt template for gleaning (follow-up "did you miss anything?")
gleaning_template: "prompts/extraction/gleaning.yaml"

# Output parser (how to interpret LLM output)
parser: "delimiter"  # "delimiter" | "json" | "amr"
```

```yaml
# prompts/graph_types/reified.yaml
graph_type: "reified"
display_name: "Reified Event Graph"

node_attributes: [name, type, description]
edge_attributes: [relation_name, description, weight, role, role_label]
reification: true

extraction_template: "prompts/extraction/reified_extraction.yaml"
gleaning_template: "prompts/extraction/gleaning.yaml"
parser: "json"
```

The extraction prompt templates use Jinja2 and are stored in `prompts/extraction/`:

```yaml
# prompts/extraction/tkg_extraction.yaml
system: |
  You are an entity and relationship extraction system.

user: |
  Given the following text, extract all entities and relationships.

  {% if ontology_mode == "closed" %}
  You MUST only use entity types from this list: {{ entity_types | join(", ") }}
  You MUST only use relationship types from this list: {{ relation_types | join(", ") }}
  If you encounter an entity or relationship that doesn't fit these types, skip it.
  {% elif ontology_mode == "mixed" %}
  Prefer these entity types: {{ entity_types | join(", ") }}
  Prefer these relationship types: {{ relation_types | join(", ") }}
  If you encounter something that clearly doesn't fit any of these types but is important,
  you may propose a new type. Mark proposed types with [NEW] prefix.
  {% else %}
  {# open mode - no constraints #}
  Extract all entity types you find relevant.
  {% endif %}

  {% if custom_guidance %}
  {{ custom_guidance }}
  {% endif %}

  Text: {{ input_text }}
```

### 3. Ontology Modes: Open, Closed, Mixed

Three modes configured per graph build:

```yaml
# In Config2.yaml or passed as config_overrides to graph_build_*
graph:
  ontology_mode: "mixed"  # "open" | "closed" | "mixed"

  # For closed/mixed modes:
  ontology:
    entity_types:
      - person: "A human individual"
      - organization: "A company, government, or group"
      - location: "A geographic place"
      - event: "A specific occurrence or happening"
    relation_types:
      - employed_by: "Person works for organization"
      - located_in: "Entity is in a location"
      - participated_in: "Entity took part in event"
    role_types:  # Only for reified graph type
      - agent: "The entity performing the action (ARG0)"
      - patient: "The entity being acted upon (ARG1)"
      - instrument: "The means by which action is performed (ARG2)"
```

**Enforcement levels:**

| Mode | Extraction | Validation | New types |
|------|-----------|------------|-----------|
| **Open** | No constraints in prompt | No validation | All accepted |
| **Closed** | Prompt constrains to list | Post-extraction rejects out-of-schema | Rejected |
| **Mixed** | Prompt prefers list, allows `[NEW]` | Post-extraction flags `[NEW]` types | Logged for review, accepted provisionally |

Mixed mode connects to onto-canon's predicate governance pipeline: `[NEW]` types are equivalent to `predicate_proposals` with status `pending`. An agent or human can later promote, reject, or merge them.

### 3b. Canonicalization Aggressiveness (Orthogonal to Ontology Mode)

Ontology mode controls what the LLM **extracts**. Canonicalization aggressiveness controls how hard we **merge** extracted output into canonical vocabularies **post-extraction**. These are independent dimensions:

```
                    Canonicalization Aggressiveness
                    none        conservative    aggressive
Extraction    ┌──────────────┬───────────────┬──────────────┐
Constraint    │              │               │              │
  open        │ current      │               │ "open-       │
              │ behavior     │               │  minimal"    │
              │              │               │              │
  mixed       │              │               │              │
              │              │               │              │
  closed      │              │               │ maximum      │
              │              │               │ constraint   │
              └──────────────┴───────────────┴──────────────┘
```

**"Open-minimal"** = open extraction (no prompt constraints — LLM extracts whatever it finds) + aggressive post-extraction canonicalization (merge everything into the smallest possible vocabulary). The ontology stays small not by constraining the LLM, but by canonicalizing its output.

Canonicalization applies to **three independent targets**, each with its own aggressiveness setting:

```yaml
# In Config2.yaml
post_build:
  canonicalize:
    entities:
      enabled: true
      aggressiveness: "conservative"  # "none" | "conservative" | "aggressive"
      # conservative: exact abbreviations, case variants only
      # aggressive: fuzzy semantic similarity via LLM
      merge_threshold: 0.85

    relations:
      enabled: true
      aggressiveness: "aggressive"
      # conservative: exact verb stem match to PropBank
      # aggressive: LLM maps "funded", "gave money to", "bankrolled" → fund-01
      vocabulary: "propbank"  # "propbank" | "framenet" | "custom"

    entity_types:
      enabled: true
      aggressiveness: "moderate"
      # conservative: exact SUMO type match
      # aggressive: LLM maps "spy agency" → GovernmentOrganization
      vocabulary: "sumo"  # "sumo" | "custom"
```

**Why SUMO/PropBank/FrameNet may make custom ontology lists unnecessary**: These canonical vocabularies already define a minimal, principled set of types and predicates:
- **PropBank**: ~7,000 verb senses with argument structure (fund-01, attack-01, employ-01)
- **SUMO**: ~100 top-level types in a formal hierarchy (Agent, Organization, Process, etc.)
- **FrameNet**: ~1,200 frames with named roles (Employer, Employee, Position, etc.)

A "closed" ontology with a hand-curated list of 10 entity types is just a subset of SUMO. A hand-curated list of 20 relation types is just a subset of PropBank. The canonical vocabularies ARE the principled version of what hand-curated lists approximate.

**The aggressiveness dimension replaces the need for hand-curated lists**: Instead of maintaining `entity_types: [person, organization, location]` per domain, set `entity_types.vocabulary: "sumo"` and `entity_types.aggressiveness: "aggressive"`. The LLM maps whatever it extracts into the SUMO hierarchy. Different aggressiveness levels control how forcefully:

| Target | Conservative | Aggressive |
|--------|-------------|-----------|
| **Entities** | Only merge "CIA" ↔ "Central Intelligence Agency" (exact abbreviation) | Also merge "the Agency" ↔ "CIA" (contextual reference) |
| **Relations** | Only map "fund" → fund-01 (exact stem) | Also map "bankrolled", "gave money to", "financed" → fund-01 |
| **Entity types** | Only map "person" → Human (exact match) | Also map "spy", "operative", "agent" → Human with role=IntelligenceAgent |

**Cypher/openCypher becomes valuable as canonicalization aggressiveness increases**: With open extraction + no canonicalization, edge labels are messy ("directed", "is the director of", "was directed by") — Cypher pattern matching fails on label mismatch. With aggressive relation canonicalization, all three become `direct-01` — and `MATCH (f:Film)-[:direct-01]->(p:Person)` works reliably. The value of structured queries scales directly with ontology constraint.

**Cypher implementation note**: [txtai](https://github.com/neuml/txtai) uses NetworkX as its default graph backend (same as DIGIMON) and has integrated [GrandCypher](https://github.com/aplbrain/grand-cypher) for Cypher queries over NetworkX graphs. This is a proven approach — no need to write a custom parser.

### 4. Reification for N-ary Relationships

For the `reified` graph type, extraction produces events as nodes with role-typed edges to participants:

**Current binary extraction:**
```
("relationship", "CIA", "Operation Cyclone", "CIA funded Operation Cyclone", 9)
```
→ One edge: CIA → Operation Cyclone

**Reified extraction:**
```json
{
  "event": {
    "name": "funding_001",
    "type": "event",
    "predicate": "fund-01",
    "description": "CIA funded Operation Cyclone through ISI"
  },
  "participants": [
    {"entity": "CIA", "role": "ARG0", "label": "agent"},
    {"entity": "Operation Cyclone", "role": "ARG1", "label": "patient"},
    {"entity": "ISI", "role": "ARG2", "label": "intermediary"}
  ]
}
```
→ One event node + three role-typed edges:
- CIA →[ARG0:agent]→ funding_001
- Operation Cyclone →[ARG1:patient]→ funding_001
- ISI →[ARG2:intermediary]→ funding_001

This is the diamond pattern on NetworkX. No storage layer changes needed. The event node has `type: "event"` and `predicate: "fund-01"`. The edges have `role` and `role_label` attributes.

**Operator compatibility**: Existing operators (onehop, PPR, VDB search) work unmodified — they traverse nodes and edges regardless of whether a node represents an entity or an event. The topology is the same. Operators that need to distinguish can check `node.type == "event"`.

### 5. Post-Build Enrichment Pipeline

After extraction and graph construction, optional enrichment steps run in sequence:

```yaml
# In Config2.yaml
post_build:
  - canonicalize_entities:
      enabled: true
      method: "llm_fuzzy"        # "llm_fuzzy" | "qcode" | "exact_only"
      batch_size: 100            # entities per LLM call
      merge_threshold: 0.85     # confidence threshold for auto-merge
  - resolve_qcodes:
      enabled: false             # Wikidata Q-code resolution
  - validate_schema:
      enabled: false             # reject/flag out-of-schema types (closed/mixed mode)
  - map_predicates:
      enabled: false             # map relation_name → AMR predicate via onto-canon
```

**Entity canonicalization** (the immediate need):

```python
async def canonicalize_entities(graph: NetworkXStorage, llm, config) -> CanonResult:
    """Post-build entity dedup via LLM fuzzy matching.

    1. Collect all node names from graph
    2. Batch into groups of ~100
    3. For each batch, ask LLM: "Which of these refer to the same entity?"
    4. For each merge group: pick canonical name, merge node attributes,
       redirect all edges, remove duplicate nodes
    5. Return stats: {merged: int, total_before: int, total_after: int}
    """
```

This reuses the prompt logic from `onto-canon/onto_canon/concept_dedup.py` (`match_entities_to_concepts`) but operates directly on the NetworkX graph without needing SQLite.

### 6. File Layout

```
prompts/
  graph_types/           # Graph type definitions
    kg.yaml              # Binary KG (name + relation + weight only)
    tkg.yaml             # Typed KG (+ type, descriptions)
    rkg.yaml             # Rich KG (+ keywords)
    reified.yaml         # Reified event graph (+ roles)
    tree.yaml            # Chunk tree
    passage.yaml         # Passage graph
  extraction/            # Extraction prompt templates (Jinja2)
    kg_extraction.yaml
    tkg_extraction.yaml
    rkg_extraction.yaml
    reified_extraction.yaml
    gleaning.yaml        # Shared gleaning template
  ontology/              # Ontology constraint files (for closed/mixed)
    hotpotqa_types.yaml  # Domain-specific type lists
    general_types.yaml   # General-purpose defaults
  canonicalization/      # Canonicalization prompts
    entity_dedup.yaml    # "Which of these are the same entity?"
```

## Integration Points

### With onto-canon

- **Entity canonicalization**: Reuse `match_entities_to_concepts` prompt from `onto-canon/prompts/concept_dedup/match_concepts.yaml`
- **Q-code resolution**: Call `onto-canon/onto_canon/wikidata_entity_search.py` in the `resolve_qcodes` post-build step
- **Predicate governance**: `[NEW]` types from mixed mode feed into onto-canon's `predicate_proposals` table
- **Schema validation**: Onto-canon's SUMO constraints can validate extracted types in the `validate_schema` step

### With existing DIGIMON code

- `GraphPrompt.py` becomes a loader that reads YAML templates instead of containing hardcoded strings
- `ERGraph`, `RKGraph` read their graph type config to select templates
- `_build_graph_from_records` / `_build_graph_from_tuples` gain a `reified` code path for diamond-pattern nodes
- `BaseGraph.build_graph()` gains a post-build enrichment hook
- `Config2.yaml` gains `ontology_mode`, `ontology`, and `post_build` sections
- No operator changes needed (topology-agnostic)

## Implementation Order

1. **Entity canonicalization post-build step** — The most immediate value. Adapts onto-canon's `match_entities_to_concepts()` for direct NetworkX graph operation. Configurable `merge_threshold`. No dependency on prompts-as-data.
2. **Prompts as data** — Move extraction prompts from `GraphPrompt.py` to YAML/Jinja2 templates. Load via `llm_client.render_prompt()`. No behavior change, just externalization. Unblocks ontology modes.
3. **Relation canonicalization post-build step** — Map extracted relation names to PropBank senses via onto-canon's AMR pipeline. Configurable aggressiveness. Unblocks Cypher.
4. **Ontology modes** — Add `ontology_mode` config + Jinja2 conditionals in templates. Open mode is current behavior. Closed/mixed add constraints. Consider: SUMO/PropBank as the canonical type/relation lists rather than hand-curated per-domain lists.
5. **Cypher query tool** — Integrate [GrandCypher](https://github.com/aplbrain/grand-cypher) for openCypher queries on NetworkX. Value scales with canonicalization aggressiveness — most useful after step 3.
6. **Entity type canonicalization** — Map extracted types to SUMO hierarchy. Configurable aggressiveness.
7. **Reified graph type** — New extraction template + JSON parser + diamond-pattern builder. For n-ary events (intelligence analysis use case, not needed for QA benchmarks).
8. **Full post-build pipeline** — Q-code resolution, schema validation as optional enrichment steps.

## Consequences

**Positive:**
- Graph types become data-driven, not code-driven
- New graph types can be added by writing YAML, not Python
- Ontology constraints are configurable per-build
- Entity canonicalization improves multi-hop traversal
- Reification enables event-centric reasoning (who did what to whom)
- Post-build enrichment is modular and optional

**Negative:**
- Template loading adds indirection vs hardcoded strings
- Reified graphs have more nodes (event nodes), increasing graph size
- LLM fuzzy dedup in post-build adds cost and latency to graph construction
- Mixed ontology mode requires human-in-the-loop or governance automation

**Risks:**
- Reified extraction may produce inconsistent event boundaries (LLM decides what constitutes "one event")
- Closed ontology mode may cause the LLM to force-fit entities into wrong types rather than skip them
- Entity canonicalization may over-merge (merge distinct entities with similar names)
