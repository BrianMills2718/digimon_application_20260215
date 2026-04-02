# Operational Knowledge — Digimon_for_KG_application

Shared findings from all agent sessions. Any agent brain can read and append.
Human-reviewed periodically.

## Findings

<!-- Append new findings below this line. Do not overwrite existing entries. -->
<!-- Format: ### YYYY-MM-DD — {agent} — {category}                          -->
<!-- Categories: bug-pattern, performance, schema-gotcha, integration-issue, -->
<!--             workaround, best-practice                                   -->
<!-- Agent names: claude-code, codex, openclaw                               -->

---

### 2026-03-27 — codex — workaround
`requirements-dev.txt` inherits `requirements.txt`, and the previous
`umap==0.1.1` pin broke `pip install -r requirements-dev.txt` on Python 3.12
with "No matching distribution found for umap==0.1.1". DIGIMON imports `umap`
from `umap-learn`, so removing the plain `umap` pin is the correct repair.

### 2026-03-27 — codex — integration-issue
After installing `pytest-asyncio`, `tests/test_digimon_mcp_tools.py` runs
instead of failing at collection. Current failures are real experimental-lane
issues: lazy-loading in `Core.MCP.digimon_mcp_server` breaks tests that patch
module-level symbols like `build_er_graph` and `chunk_get_text_for_entities_tool`,
`test_corpus_prepare_tool` asserts before the wrapper-written file is observed,
and `test_session_context_isolation` still expects a missing `load_yaml` path.

### 2026-03-27 — codex — best-practice
Direct-benchmark atom query forwarding now works at the tool layer: retrieval
tools can rewrite broad question-shaped queries to the active semantic-plan
atom and can prepend resolved dependency values from completed TODO items. In
the real `digimon` benchmark environment this changed retrieval queries from
free-form question text to atom-scoped searches like `performer III` and `Saint
Joseph birthplace`. The remaining failure mode is not query formulation but
atom closure: the model still often fails to mark `a1` done in `todo_write`, so
later retrieval never truly advances to `a2`.

### 2026-03-27 — codex — integration-issue
The `.venv` path is sufficient for unit tests but not for full MuSiQue direct
benchmark runs: `chunk_retrieve` failed there with `ModuleNotFoundError: No
module named 'llama_index.legacy'`, and FAISS-backed VDBs were unavailable.
The existing `/home/brian/miniconda3/envs/digimon/bin/python` environment has
the real graph/VDB retrieval stack, but that env is missing `prompt_eval`, so
benchmark execution completed and wrote JSON artifacts before crashing in the
post-run evaluation import path.

### 2026-03-27 — codex — bug-pattern
The current MuSiQue multi-hop bottleneck is no longer raw retrieval; it is
control-flow after subject resolution. The direct benchmark lane now supports
atom-scoped query rewriting, atom completion updates, automatic subject
profiling after high-confidence `entity_search(method='string')`, and
bridge-candidate probing off downstream clues. Even so, the Lady Godiva case
still loops when the outer agent ignores the resolved subject and falls back to
more `chunk_retrieve` calls. The next structural lever is to turn successful
subject resolution into an enforced state transition, not another advisory hint.

### 2026-03-27 — codex — bug-pattern
Direct benchmark result artifacts were overstating failed `submit_answer` calls
as grounded submits. The reliable signal is the observed tool-call payload, not
raw metadata. Recomputing `submit_answer_succeeded`,
`submit_validator_accepted`, `required_submit_missing`, and
`submit_completion_mode` from actual `submit_answer` tool results fixed the
false-positive acceptance leak.

### 2026-03-27 — codex — best-practice
Consolidated benchmark linearization must understand benchmark-mode raw payloads
such as `one_hop_relationships` and neighbor maps. Without that, graph evidence
looks empty or opaque to the model even when the raw payload contains the right
bridge entities. After teaching the linearizer those shapes, the remaining
Lady-Godiva bottleneck was no longer data loss but bridge-selection policy.

### 2026-03-27 — codex — best-practice
The existing bridge probe was already ranking `Mercia` above `Leicester`,
`England`, and `Croyland Abbey` for `2hop__511454_120259`; the failure was the
auto-advance gate, not missing evidence. Making the probe margin configurable
and lowering the default score-gap threshold from `+1.0` to `+0.5` allowed the
harness to promote the bridge entity and made the frozen Lady Godiva case pass
end-to-end (`EM/F1 = 1.0`, run tag `atom_bridge_gap_r9`).

### 2026-03-27 — codex — integration-issue
Multi-question MuSiQue smoke runs can be invalidated by provider instability
even when the control logic is improving. In `atom_bridge_priority_smoke_r14`,
`2hop__511454_120259` failed before any tool calls because the agent LLM could
not reach OpenRouter, and `3hop1__305282_282081_73772` hit the 180s question
timeout after a provider timeout plus partial progress. Use bounded single-ID
reruns to validate logic changes before trusting larger slices.

### 2026-03-27 — codex — bug-pattern
The next post-Godiva failure family is namesake/person-vs-place resolution.
`2hop__199513_801817` originally auto-completed atom1 to `brazil` from a
relationship search even though the atom asked for a person. Filtering bridge
candidates by the current atom's expected coarse type removed that place
misclassification, but the run still drifted to `Saint Joseph of the Fields`,
which means the remaining bug is semantic interpretation of the city's name and
final answer gating, not the original place-vs-person bridge policy.

### 2026-03-28 — codex — best-practice
Direct benchmark scoring now drops unsupported terminal answers in two cases:
when `submit_answer` is explicitly rejected while atoms are still pending, and
when a forced-terminal freeform answer appears after tool disablement but the
last `[TODO_STATE]` still shows unfinished atoms. This prevents namesake/gloss
failures like `2hop__199513_801817` from being recorded as grounded answers
(`Saint Joseph of the Fields` / `Saint Joseph`) when the semantic-plan
contract never actually closed `a1` or `a2`.

### 2026-03-28 — codex — bug-pattern
The current namesake bottleneck is no longer false answer acceptance. After the
submit/finalization guards, `2hop__199513_801817` fails honestly as
`missing_required_submit`. Preserving alias-like entity queries grounded in
cached evidence (`Saint Joseph ...`) changed the search trajectory, but the
agent still does not canonically bridge the city-name gloss to the gold path
(`Nazareth`). The next repair target is saint-title / alias canonicalization
and higher-signal retrieval construction, not more answer gating.

### 2026-03-28 — codex — bug-pattern
The birthplace-evidence guard removed the previous `california` false
completion for `2hop__199513_801817`: `a1` now closes to `Saint Joseph`, and
`a2` stays unresolved instead of auto-completing from unrelated connected
places. The next bottleneck is softer than the earlier bug: the corpus reaches
`Nazareth` only indirectly (for example via Mary / Holy Family chunks), so the
control loop can retrieve the right place but still lacks a defensible
atom-completion update for the birthplace relation.

### 2026-03-28 — codex — best-practice
For the São José namesake family, harness-level subject-chunk probing is worth
keeping even before the final birthplace hop is solved. After a clean
`entity_search(string)` hit, internally fetching chunks linked to the resolved
subject entity restores deterministic `a1 -> Saint Joseph` closure on the
maintained direct lane without relying on the model to discover the
`by_entities` follow-up tool on its own. The remaining miss is now concentrated
in `a2`: retrieving indirect `Nazareth` evidence for Saint Joseph and turning
it into a defensible place completion.

### 2026-03-31 — codex — best-practice
The first safe repair for DIGIMON's current canonicalization failure family is
additive identity metadata, not a node-ID rewrite. Keeping legacy
`clean_str`-normalized node IDs while persisting `canonical_name`,
Unicode-aware `search_keys`, and optional `aliases` lets graph build, MCP
entity search, entity profiles, and onto-canon imports preserve human-readable
names immediately. This makes lossy nodes like `s o jos dos campos` resolvable
from `São José dos Campos` without changing graph topology or importer
compatibility.

### 2026-03-31 — codex — integration-issue
For the current Plan #22 canonicalization slice, the project-local `.venv`
supports the targeted unit-test surface, but not the full test suite. Verified:

- `.venv/bin/python -m pytest -q tests/unit/test_graph_build_manifest.py tests/unit/test_graph_config_profiles.py tests/unit/test_onto_canon_import.py tests/unit/test_entity_string_search.py tests/unit/test_prebuild_graph_cli.py`
  passes (`42 passed`)
- full `.venv/bin/python -m pytest -q` still fails at collection because
  optional experimental-lane dependencies such as `faiss` and `websockets`
  are not installed in that environment

Treat the targeted Plan #22 unit suite as the truthful verification path for
the maintained canonicalization slice until the broader env contract is
reconciled.

### 2026-03-31 — codex — integration-issue
A bounded 5-chunk MuSiQue rebuild with `--enable-chunk-cooccurrence` and
`--enable-passage-nodes` proved that the live projection path can materialize
`passage_chunk_*` nodes and `chunk_cooccurrence` edges under the maintained
DIGIMON build. The resulting `graph_build_manifest.json` still left
`config_flags.graph_profile` and `config_flags.enable_passage_nodes` null,
though, so artifact consumers should trust the built graph itself over those
two manifest fields until manifest truthfulness is repaired.

### 2026-03-31 — codex — integration-issue
In the direct benchmark lane, `--disable-embedding-tools` is not yet a full
semantic-search disable switch. It removes the embedding tools from the
exposed tool surface and skips VDB preload, but `entity_search(method='semantic')`
can still try to resolve `MuSiQue_entities` internally and then degrade into
empty-linearized VDB errors. Hold that runtime condition constant across
before/after graph comparisons, but treat it as the next benchmark-runtime
repair slice if projection changes alone do not move the frozen tranche.

### 2026-03-31 — codex — integration-issue
The current onto-canon6 import CLI path is repo-root-sensitive. Running
`scripts/import_onto_canon_jsonl.py` from outside the DIGIMON repo can fail
before JSONL loading because `Option/Config2.default()` looks for
`Option/Config2.yaml` via a relative path. The supported v1 consumer workflow
is therefore:

- run `onto-canon6` export from the `onto-canon6` repo root
- run `scripts/import_onto_canon_jsonl.py` from the DIGIMON repo root

Verified against the real Shield AI review DB on 2026-03-31: `110` exported
entities and `99` exported relationships imported as a DIGIMON GraphML artifact
with `110` nodes and `78` edges; `16` single-endpoint relationships were
skipped and the remaining relationship delta came from DIGIMON's duplicate
endpoint merge semantics.

### 2026-04-02 — claude-code — best-practice
**Prompt iteration findings on 19q MuSiQue diagnostic set (Plan #17):**
- ANSWER_SYNTHESIS eliminated (3→0) by adding answer granularity matching
  ("what year" → year only), pre-submission verification step, and flexible
  relationship interpretation at atom resolution stage.
- CONTROL_FLOW fix: "submit immediately when all atoms done" fixed 1 question
  (511296 "Maria Shriver" — agent had answer but kept looping).
- QUERY_FORMULATION: "keep queries SHORT (2-5 keywords)" + "simplify when
  search returns nothing" + "fall back to graph traversal" guidance helped but
  most QF failures are entity VDB quality issues (entity_search returning wrong
  entities like Israel→"United States").
- **Sentinel question 731956 is stochastic** — passes ~50% of runs. Not a
  reliable regression indicator.
- Retrieval stagnation is the dominant terminal condition (53-63% of questions).
  Agent hits 4-turn stagnation limit well before the 20-call budget. The
  bottleneck is search quality, not search quantity.
- Remaining failures are split: QUERY_FORMULATION (6), INTERMEDIATE_ENTITY_ERROR
  (4), RETRIEVAL_RANKING (2), GRAPH_REPRESENTATION (1), ANSWER_SYNTHESIS (1).
  Most need VDB/graph improvements, not prompt fixes.
- **STAG_TURNS=6 is the best default** — halves stagnation rate (58%→32%),
  adds 2 new LLM-judge passes (94201 Mississippi River Delta, 619265 12 episodes).
- **entity_search top_k=10 is WORSE** than top_k=5 — dilutes results with
  noise, agent gets confused by more candidates. Reverted.

### 2026-04-02 — claude-code — bug-pattern
**Evidence pointer tracking is broken for DIGIMON's linearized tool results.**
The llm_client stagnation detector (`_tool_evidence_pointer_labels` in
`agent_artifacts.py`) parses tool results as JSON looking for `chunk_id`,
`evidence_refs` fields. DIGIMON's linearized results are plain text, not JSON,
so every evidence turn produces zero evidence pointers and the stagnation
detector fires incorrectly.

Impact: 100% of evidence turns counted as "stagnant" regardless of whether
the agent found new entities or chunks. STAG_TURNS=6 is the workaround.

Fix attempted: wrapping linearized text in JSON envelope with evidence_refs.
REVERTED — caused 6x latency regression because model struggled to parse
JSON-wrapped tool results.

Proper fix needed in llm_client: modify `_collect_evidence_pointer_labels`
to handle plain-text results, or add a separate metadata channel for
evidence pointers that doesn't change the visible tool result.

### 2026-04-02 — codex — best-practice
The `digimon-kgrag` FastMCP tool objects support planner metadata directly via
their `meta` field. Attaching `cost_tier`, `reliability_tier`, and `notes`
onto the live tool registry at import time, and failing startup if any
registered tool lacks explicit coverage, is the reliable way to keep
`list_tool_catalog`, deferred-tool discovery, and future budget attribution in
sync.

### 2026-04-02 — codex — integration-issue
The sanctioned governed-repo installer from `project-meta` now assumes DIGIMON
can generate `AGENTS.md` from `CLAUDE.md` using the shared renderer contract.
That means `CLAUDE.md` must expose non-empty `Commands`, `Principles`,
`Workflow`, and `References` H2 sections. DIGIMON previously symlinked
`AGENTS.md` to `CLAUDE.md`, which blocked rollout until those sections were
added and the symlink was replaced with a rendered file. Treat those sections
as part of the repo's mechanical coordination contract going forward.

### 2026-04-02 — codex — best-practice
`scripts/meta/complete_plan.py` in DIGIMON must not assume repo-wide
`tests/` collection is the truthful verification surface for every plan.
For coordination and governance slices, the plan's own `Required Tests`
command table is the authoritative contract. The closeout script now:

- launches subprocesses with `sys.executable` instead of bare `python`/`pytest`
- honors command-based verification rows in the plan file when present

This keeps repo-local closeout aligned with the plan's declared acceptance
criteria instead of failing on unrelated integration-lane collection debt.

### 2026-04-02 — codex — integration-issue
Plan #22's projection follow-through had a real resume-path bug: when
`ERGraph._build_graph()` re-entered with a checkpoint that already covered all
selected chunks, it returned success without clearing
`_checkpoint_processed.json`. That left the artifact in a permanent
"looks-incomplete" state for the followthrough harness even though the graph
itself could already be usable. The correct fix is to clear the checkpoint in
the `remaining == 0` path and let manifest persistence proceed.

### 2026-04-02 — codex — integration-issue
From this Codex sandbox, the live Plan #22 projection rebuild and tranche rerun
cannot complete because outbound DNS/network access to Gemini and OpenRouter is
blocked. The verified unit slice is still valid locally, but any end-to-end
benchmark or rebuild step that needs remote LLM calls must run in an
environment with provider network access.
