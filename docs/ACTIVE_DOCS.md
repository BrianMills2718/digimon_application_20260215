# Active Documentation

Use this file to find the current, supported documentation set.

## Canonical Docs

- `README.md`
  Entry point for repo purpose, quick start, and project structure.
- `FUNCTIONALITY.md`
  Supported workflow and explicit non-goals.
- `docs/SYSTEM_OVERVIEW.md`
  Architecture, storage model, and benchmark caveats.
- `docs/COMPETITIVE_ANALYSIS.md`
  Baselines, current evidence, and open thesis.
- `docs/plans/CLAUDE.md`
  Active implementation-plan index.
- `docs/plans/03_prove_adaptive_routing.md`
  Current investment-decision plan.

## Archive Policy

Historical UI, API, UKRF, social-media, and integration docs are not source-of-truth for the current repo surface.

Those materials live under `docs/archive/`.

If a document describes:

- `api.py`
- `main.py`
- `digimon_cli.py`
- Streamlit frontend workflows
- social-media UI workflows
- UKRF/master-orchestrator roadmaps

then it should be archived unless it is being actively rewritten to match the current repo.

## Current Product Story

DIGIMON is currently best understood as a research system for testing adaptive operator routing over graph retrieval for multi-hop QA.

It is not currently a maintained REST product, Streamlit product, or generalized social-media analysis product.
