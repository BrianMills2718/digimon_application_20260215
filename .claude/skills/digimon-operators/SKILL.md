---
name: digimon-operators
description: DIGIMON operator signatures, common chains, and output-to-input mappings for composing retrieval DAGs via execute_operator_chain
---

# DIGIMON Operator Composition Guide

Use `execute_operator_chain` to compose operators as Python code. Intermediates stay in variables — only print() output enters your context.

## Pattern: Plan Then Code

1. Call `semantic_plan(question)` to decompose the question into atoms
2. Write Python code that chains operators based on the plan
3. Execute via `execute_operator_chain(code)`

## Core Operators (most common)

### Entity Search
```python
# Vector similarity search — START HERE for most questions
result = json.loads(await entity_vdb_search(query_text="Shield AI", top_k=5))
# result["similar_entities"]: [{"entity_name": "Shield AI", "similarity": 0.95}, ...]
entity_names = [e["entity_name"] for e in result["similar_entities"]]
```

### Entity Extraction (from question text)
```python
# Extract entity mentions from natural language
result = json.loads(await meta_extract_entities(query_text="Who founded Shield AI?"))
# result["entities"]: [{"entity_name": "Shield AI"}, ...]
```

### Entity Link (fuzzy match to graph)
```python
# Match extracted names to graph entities
result = json.loads(await entity_link(source_entities=["Shield AI", "V-BAT"]))
# result["linked_entities"]: [{"source": "Shield AI", "target": "shield_ai", "score": 0.98}]
```

### Relationship Traversal
```python
# One-hop relationships from entities
result = json.loads(await relationship_onehop(
    entity_ids=["shield_ai", "v-bat"],
    graph_reference_id=graph_id
))
# result["relationships"]: [{"src_id": "shield_ai", "tgt_id": "us_coast_guard", "relation_name": "contract"}, ...]
```

### Chunk Retrieval
```python
# Get text chunks mentioning entities
result = json.loads(await chunk_occurrence(
    target_entity_pairs=[{"src": "shield_ai", "tgt": "us_coast_guard"}],
    top_k=5
))
# result["chunks"]: [{"chunk_id": "c1", "text_content": "Shield AI was awarded..."}, ...]
context = [c["text_content"] for c in result["chunks"]]
```

### Answer Generation
```python
# TERMINAL: synthesize answer from chunks
answer = await meta_generate_answer(
    query_text="What contracts does Shield AI have?",
    context_chunks=context
)
print(answer)  # Only this enters your context
```

## Common Chains

### Simple lookup (1-2 hop)
```python
entities = json.loads(await entity_vdb_search(query_text=question, top_k=5))
names = [e["entity_name"] for e in entities["similar_entities"]]
chunks = json.loads(await chunk_get_text_by_entity_ids(entity_names=names))
answer = await meta_generate_answer(query_text=question, context_chunks=[c["text_content"] for c in chunks["chunks"]])
print(answer)
```

### Relationship-based (2-3 hop)
```python
entities = json.loads(await entity_vdb_search(query_text=question, top_k=5))
names = [e["entity_name"] for e in entities["similar_entities"]]
rels = json.loads(await relationship_onehop(entity_ids=names, graph_reference_id=graph_id))
rel_strings = [f"{r['src_id']}->{r['tgt_id']}" for r in rels["relationships"]]
chunks = json.loads(await chunk_from_relationships(target_relationships=rel_strings, top_k=10))
answer = await meta_generate_answer(query_text=question, context_chunks=[c["text_content"] for c in chunks["chunks"]])
print(answer)
```

### Multi-hop with PageRank
```python
seeds = json.loads(await entity_vdb_search(query_text=question, top_k=3))
seed_ids = [e["entity_name"] for e in seeds["similar_entities"]]
ranked = json.loads(await entity_ppr(graph_reference_id=graph_id, seed_entity_ids=seed_ids, top_k=15))
# ranked["ranked_entities"]: [[entity_id, score], ...]
top_entities = [e[0] for e in ranked["ranked_entities"][:10]]
chunks = json.loads(await chunk_get_text_by_entity_ids(entity_names=top_entities))
answer = await meta_generate_answer(query_text=question, context_chunks=[c["text_content"] for c in chunks["chunks"]])
print(answer)
```

### Question decomposition (AoT)
```python
plan = json.loads(await semantic_plan(question=question))
sub_answers = []
for atom in plan["atoms"]:
    entities = json.loads(await entity_vdb_search(query_text=atom["sub_question"], top_k=3))
    names = [e["entity_name"] for e in entities["similar_entities"]]
    chunks = json.loads(await chunk_get_text_by_entity_ids(entity_names=names))
    sub_answer = await meta_generate_answer(
        query_text=atom["sub_question"],
        context_chunks=[c["text_content"] for c in chunks["chunks"]]
    )
    sub_answers.append(f"Q: {atom['sub_question']}\nA: {sub_answer}")
# Final synthesis
final = await meta_generate_answer(
    query_text=question,
    context_chunks=sub_answers
)
print(final)
```

## Output-to-Input Mappings

| From | Output field | To | Input param |
|------|-------------|-----|-------------|
| entity_vdb_search | similar_entities[].entity_name | entity_ppr | seed_entity_ids |
| entity_vdb_search | similar_entities[].entity_name | relationship_onehop | entity_ids |
| entity_vdb_search | similar_entities[].entity_name | chunk_get_text_by_entity_ids | entity_names |
| meta_extract_entities | entities[].entity_name | entity_link | source_entities |
| entity_ppr | ranked_entities[][0] | relationship_onehop | entity_ids |
| relationship_onehop | relationships[] src_id->tgt_id | chunk_from_relationships | target_relationships |
| chunk_* | chunks[].text_content | meta_generate_answer | context_chunks |

## Key Params

- `graph_reference_id`: usually the dataset name. Check `list_available_resources`.
- `top_k`: controls result count. Default 5-10. Increase for broader search.
- All operators return JSON strings — always `json.loads()` the result.
- All operators are async — always `await`.
