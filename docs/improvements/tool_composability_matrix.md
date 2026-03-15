# Benchmark Tool Composability Matrix

This matrix defines how tools compose in benchmark QA runs.

## Artifact Kinds

- `QUERY_TEXT`: The question or a derived query string.
- `ENTITY_SET`: Candidate/confirmed entities.
- `RELATIONSHIP_SET`: Retrieved relationship records.
- `CHUNK_SET`: Retrieved source passages/chunks.
- `SUBGRAPH`: Path/tree/connected-structure evidence.

Initial artifacts at run start:

- `QUERY_TEXT`

## Tool Contracts (Benchmark)

| Tool | Consumes | Produces | Notes |
|---|---|---|---|
| `entity_vdb_search` | any of `QUERY_TEXT`,`ENTITY_SET`,`CHUNK_SET` | `ENTITY_SET` | semantic entity retrieval |
| `entity_onehop` | all `ENTITY_SET` | `ENTITY_SET` | graph neighborhood expansion |
| `entity_ppr` | all `ENTITY_SET` | `ENTITY_SET` | graph ranking from seeds |
| `entity_link` | any of `QUERY_TEXT`,`CHUNK_SET` | `ENTITY_SET` | lexical/entity linking |
| `entity_tfidf` | any of `QUERY_TEXT`,`CHUNK_SET` | `ENTITY_SET` | keyword entity retrieval |
| `relationship_onehop` | all `ENTITY_SET` | `RELATIONSHIP_SET` | relationship expansion |
| `relationship_score_aggregator` | any of `ENTITY_SET`,`RELATIONSHIP_SET` | `RELATIONSHIP_SET` | relationship scoring |
| `relationship_vdb_search` | any of `QUERY_TEXT`,`ENTITY_SET`,`CHUNK_SET` | `RELATIONSHIP_SET` | semantic relationship retrieval |
| `chunk_from_relationships` | all `RELATIONSHIP_SET` | `CHUNK_SET` | provenance chunk retrieval |
| `chunk_occurrence` | all `ENTITY_SET` | `CHUNK_SET` | co-occurrence chunk retrieval |
| `chunk_get_text` | dynamic (see below) | `CHUNK_SET` | entity/chunk-id fetch |
| `chunk_text_search` | all `QUERY_TEXT` | `CHUNK_SET` | TF-IDF keyword chunk retrieval |
| `chunk_vdb_search` | any of `QUERY_TEXT`,`ENTITY_SET`,`CHUNK_SET` | `CHUNK_SET` | semantic chunk retrieval |
| `chunk_aggregator` | any of `ENTITY_SET`,`RELATIONSHIP_SET` | `CHUNK_SET` | sparse-matrix chunk scoring |
| `subgraph_khop_paths` | all `ENTITY_SET` | `SUBGRAPH` | k-hop path search |
| `subgraph_steiner_tree` | all `ENTITY_SET` | `SUBGRAPH` | minimum connecting structure |
| `meta_pcst_optimize` | any of `ENTITY_SET`,`RELATIONSHIP_SET` | `SUBGRAPH` | PCST optimization |
| `bridge_disambiguate` | any of `ENTITY_SET`,`CHUNK_SET` | `ENTITY_SET` | bridge-entity selection |

## Dynamic Rule: `chunk_get_text`

`chunk_get_text` consumes different artifacts based on arguments:

- if `chunk_id` or `chunk_ids` is used: requires `CHUNK_SET`
- if `entity_ids` or `entity_names` is used: requires `ENTITY_SET`
- if both are used: requires both `CHUNK_SET` and `ENTITY_SET`

## Control/Planning Tools

These tools are control-plane operations and bypass artifact checks:

- `list_available_resources`
- `semantic_plan`
- `todo_write`
- `submit_answer`

## Runtime Enforcement

When `enforce_tool_contracts=True`:

- incompatible tool calls are rejected with explicit `Tool contract violation` errors
- violations are returned in tool-call traces (not silently ignored)
- final metadata includes:
  - `tool_contract_rejections`
  - `initial_artifacts`
  - `available_artifacts_final`
