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

**Update:** 2026-03-21

Two closure-aware live 10-chunk smoke builds now exist on the same MuSiQue
slice:

- `MuSiQue_TKG_smoke_closure`: `123` nodes / `68` edges
- `MuSiQue_TKG_smoke_closure_grounded`: `100` nodes / `70` edges

The grounded variant did reduce graph size, but it also over-pruned useful
named nodes that the policy is supposed to preserve:

- `silver ball` disappeared
- `throat cancer` disappeared
- Unicode-damaged IDs like `supercopa de espa a` still remain

So the residual problem is no longer "should we add the grounded flag at all?"
It is "how do we improve extraction quality without destroying useful named
entities on the real slice?"

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

### ISSUE-005: Grounded-entity prompt-eval can fail on long structural cases before scoring policy behavior

**Observed:** 2026-03-21  
**Status:** `planned`

The first live grounded-entity `prompt_eval` smoke run over the mixed frozen
case set exposed a new evaluation blocker:

- `grounded_entity_contract` on `musique_doc_1_barcelona_2006_07` produced a
  truncated response (`201360` chars) instead of a scoreable extraction output
- once one variant misses a scored input, `prompt_eval`'s paired-by-input
  comparison fails loudly because the scored input IDs no longer match across
  variants
- this means the current mixed fixture is too large or too open-ended for the
  first grounded-entity proof run, even though the shorter policy cases are the
  actual target of ADR-006

This is not evidence that the grounded-entity policy is wrong. It is evidence
that the first proof needs a smaller live slice aligned to the policy question
before the long structural cases are reintegrated.

**Next step:** continue [Plan #5](docs/plans/05_extraction_quality_repair.md)
by adding a short grounded-entity smoke fixture, running the first live policy
comparison there, and treating reintegration of the full mixed case set as a
follow-up gate rather than the first proof step.

### ISSUE-006: Extraction field-tag stripping erases valid angled entity-type values

**Observed:** 2026-03-21  
**Status:** `resolved`

The first successful grounded-entity smoke run on the short policy fixture did
not actually measure the intended policy well because both prompt variants were
systematically losing typed entities during scoring:

- every smoke case reported `entity_validity=0.0` for both variants
- the raw trial outputs show entity types emitted as angled values such as
  `<person>`
- `strip_extraction_field_markup("<person>")` currently returns the empty
  string, while `strip_extraction_field_markup("<Silver Ball>")` is preserved
- that means the current field-tag stripping regex is removing any single-token
  lowercase angled value, even when it is a legitimate entity type rather than
  leaked prompt markup

This is now the concrete blocker for meaningful grounded-entity policy
comparison. Until typed entity values survive scoring, the prompt-eval slice is
mostly measuring parser damage rather than keep/drop behavior.

**Next step:** continue [Plan #5](docs/plans/05_extraction_quality_repair.md)
by tightening field-tag stripping so it only removes known placeholder wrappers
instead of arbitrary lowercase angled values, then rerun the short grounded-
entity smoke fixture.

**Resolution:** 2026-03-21

`strip_extraction_field_markup()` now removes only known extraction placeholder
wrappers such as `<entity_type>` and preserves legitimate angled values such as
`<person>`. The short grounded-entity smoke fixture was rerun after the fix
(`execution_id=0bd80b942644`), and both prompt variants recovered
`entity_validity=1.0` across all four cases.

### ISSUE-007: Named relationship endpoints can still be missing as entity records

**Observed:** 2026-03-21  
**Status:** `planned`

After the field-tag stripper was repaired and the short grounded-entity smoke
fixture was rerun, the remaining non-perfect policy case was
`musique_doc_9_grounded_silver_ball`:

- both prompt variants recovered typed entities and scored near `1.0`
- both variants still emitted `Silver Ball` only as a relationship endpoint and
  not as a standalone entity record
- the current policy fixture therefore shows a graph-completeness problem, not
  just an abstraction-pruning problem

This matters because DIGIMON's entity-graph build path should not rely on a
named node existing only implicitly inside relationship records if the graph is
supposed to expose that node to downstream retrieval operators.

**Update:** 2026-03-21

ADR-007 accepted the closure rule and the live parser now rejects any
relationship whose endpoints do not both appear as entity records in the same
extraction output. A closure-aware rerun of the short grounded-entity smoke
fixture (`execution_id=04b5479be557`) showed that both prompt variants still
miss named endpoint entity records in some cases, especially `Silver Ball`.

The first live 10-chunk closure-aware smoke build
(`MuSiQue_TKG_smoke_closure`) confirms the same tradeoff:

- low-value abstractions like `form`, `fitness`, and `medical leave` are absent
  from the persisted graph
- named nodes such as `silver ball` and `throat cancer` still survive
- edge count dropped to `68` because incomplete relationships are now rejected
  instead of being persisted

**Next step:** continue [Plan #5](docs/plans/05_extraction_quality_repair.md)
by improving prompt completeness so named relationship endpoints are emitted as
entity records before another larger rebuild or graph-quality claim.

### ISSUE-008: Live extraction smoke builds still use mixed-model fallbacks

**Observed:** 2026-03-21  
**Status:** `confirmed`

Both live 10-chunk closure-aware smoke builds allowed provider fallback during
extraction:

- the non-grounded `MuSiQue_TKG_smoke_closure` run fell back from
  `gemini/gemini-2.5-flash` to `openrouter/deepseek/deepseek-chat`
- the grounded `MuSiQue_TKG_smoke_closure_grounded` run also fell back from
  Gemini to DeepSeek after a provider policy block

This is a real methodology problem. DIGIMON cannot treat live graph-artifact
comparisons as decision-grade evidence if the same build slice is generated by a
mixed provider/model path without the artifact or plan calling that out
explicitly.

**Next step:** extend the graph-build path to support a pure-lane/no-fallback
extraction mode for evaluation builds, then rerun the 10-chunk comparison on
that controlled path.

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
