# Issues

Observed problems, concerns, and technical debt. Items start as **unconfirmed**
observations and get triaged through investigation into confirmed issues, plans,
or dismissed.

**Last reviewed:** 2026-03-21

---

## Status Key

| Status | Meaning | Next Step |
|--------|---------|-----------|
| `unconfirmed` | Observed, needs investigation | Investigate to confirm/dismiss |
| `monitoring` | Confirmed concern, watching for signals | Watch for trigger conditions |
| `confirmed` | Real problem, needs a fix | Create a plan |
| `planned` | Has a plan (link to plan) | Implement |
| `resolved` | Fixed | Record resolution |
| `dismissed` | Investigated, not a real problem | Record reasoning |

---

## Unconfirmed

(Add observations here with enough context to investigate later)

### ISSUE-001: (Title)

**Observed:** (date)
**Status:** `unconfirmed`

(What was observed. Why it might be a problem.)

**To investigate:** (What would confirm or dismiss this.)

---

## Monitoring

(Items confirmed as real but not yet urgent. Include trigger conditions.)

---

## Confirmed

(Items that need a fix but don't have a plan yet.)

### ISSUE-002: Python 3.12 environment install path is not truthful

**Observed:** 2026-03-21  
**Status:** `confirmed`

The declared environment story is currently inconsistent with the live runtime
path:

- a clean `pip install -r requirements.txt` fails on Python 3.12 because the
  file pins `umap==0.1.1`, which is not installable in this environment
- the project `.venv` was missing packages required by the actual server/build
  path (`mcp`, `llama-index-core`, `llama-index-embeddings-openai`,
  `llama-index-embeddings-ollama`, `umap-learn`, `scikit-learn`, plus earlier
  missing runtime packages such as `anthropic`, `instructor`, `loguru`, and
  `numpy`)
- the same `.venv` also lacked the sibling `prompt_eval` package even though
  Plan #5 prompt-iteration tooling now depends on it for controlled prompt
  experiments over frozen extraction cases

This is a real operational problem because benchmark/build reproducibility now
depends on manual dependency repair rather than one truthful bootstrap path.

**Next step:** create a focused environment repair plan or replace the broken
pin/install story with a tested Python 3.12-compatible bootstrap path.

### ISSUE-003: Real-corpus TKG smoke build still has low slot fidelity and weak typing

**Observed:** 2026-03-21  
**Status:** `planned`

The rebuilt alias architecture works on real MuSiQue data, but the first
`MuSiQue_TKG_smoke` run surfaced a separate quality problem in the extraction
layer:

- the artifact itself is structurally clean (`source_dataset_name=MuSiQue`,
  `dataset_name=MuSiQue_TKG_smoke`, no empty or single-letter node IDs)
- some extracted relations still have obvious slot inversions or malformed
  subject/object choices, for example:
  - `('barcelona', 'won by', 'extra time')`
  - `('messi', 'suffered', 'tear')`
  - `('medial collateral ligament', 'part of', 'left knee')`
  - `('located in', 'tear', 'medial collateral ligament')`
- some nodes still land with weak or null typing, including
  `left knee`, `medial collateral ligament`, `sextuple`, and `silver ball`
- after the stricter slot-discipline contract was wired end to end and
  `MuSiQue_TKG_smoke_strict_slots` was rebuilt, the specific malformed-slot
  failures improved, but the artifact still contains semantically weak entities
  such as `his`, `form`, and `medical leave`
- after deterministic anaphora filtering was added and
  `MuSiQue_TKG_smoke_strict_slots_no_anaphora` was rebuilt, `his` disappeared
  from the persisted graph and the artifact dropped from `105` nodes / `95`
  edges to `99` nodes / `78` edges on the same 10-chunk slice
- the remaining extraction-quality ambiguity is now the low-value abstraction
  policy: entities like `form` can still survive open `TKG` extraction even
  when slot structure and pronoun leakage are improved

This means the current build architecture is now good enough to isolate artifact
namespaces and provenance, but not yet good enough to claim TKG-quality schema
fidelity on real benchmark chunks.

**Next step:** execute [Plan #5](docs/plans/05_extraction_quality_repair.md)
to finish the extraction-quality repair path: keep the strict prompt contract,
add deterministic semantic entity filtering, and rerun the smoke slice before
any full rebuild or fixed-graph benchmark interpretation.

### ISSUE-004: Canonical entity identity still destroys Unicode-rich names

**Observed:** 2026-03-21  
**Status:** `planned`

Even after the stricter extraction-slot contract, the rebuilt smoke artifact
still stores normalization-damaged node IDs such as:

- `supercopa de espa a`
- `el cl sico`

This is not mainly a prompt problem. It is evidence that canonical entity
identity is still flowing through the current lossy normalization path instead
of a Unicode-preserving canonical-name contract.

This matters because DIGIMON cannot honestly reproduce richer GraphRAG methods
or compare retrieval operators if the build layer destroys the surface form of
real entities before indexing and retrieval.

**Next step:** continue [Plan #4](docs/plans/04_graph_build_rearchitecture.md)
to separate canonical identity from search normalization, then rebuild the
entity-graph slice from that contract instead of patching names ad hoc.

---

## Resolved

| ID | Description | Resolution | Date |
|----|-------------|------------|------|
| - | - | - | - |

---

## Dismissed

| ID | Description | Why Dismissed | Date |
|----|-------------|---------------|------|
| - | - | - | - |

---

## How to Use This File

1. **Observe something off?** Add under Unconfirmed with context and investigation steps
2. **Investigating?** Update the entry with findings, move to appropriate status
3. **Confirmed and needs a fix?** Create a plan, link it, move to Confirmed/Planned
4. **Not actually a problem?** Move to Dismissed with reasoning
5. **Watching a concern?** Move to Monitoring with trigger conditions
