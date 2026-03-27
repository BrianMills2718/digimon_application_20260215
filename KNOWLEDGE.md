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
