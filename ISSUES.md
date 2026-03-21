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

This is a real operational problem because benchmark/build reproducibility now
depends on manual dependency repair rather than one truthful bootstrap path.

**Next step:** create a focused environment repair plan or replace the broken
pin/install story with a tested Python 3.12-compatible bootstrap path.

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
