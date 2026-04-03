# Active Documentation

Use this file to find the current, supported documentation set.

## Core Thesis Docs

- `README.md`
  Entry point for repo purpose, quick start, and the supported default surface.
- `FUNCTIONALITY.md`
  Supported workflow and explicit non-goals.
- `docs/REPO_SURFACE.md`
  Canonical split between core, experimental, and historical repo lanes.
- `docs/SYSTEM_OVERVIEW.md`
  Architecture, storage model, and benchmark caveats.
- `docs/GRAPH_ATTRIBUTE_MODEL.md`
  Canonical graph schema, JayLZhou mapping, and projection strategy.
- `docs/GLOSSARY.md`
  Canonical term definitions for schema modes, profiles, and build/eval contracts.
- `docs/TOOL_CAPABILITY_MATRIX.md`
  Which tools apply to which graph builds, attributes, and artifacts.
- `docs/COMPETITIVE_ANALYSIS.md`
  Baselines, current evidence, and open thesis.
- `docs/plans/CLAUDE.md`
  Active implementation-plan index.
- `docs/ops/CAPABILITY_DECOMPOSITION.md`
  Repo-local capability ownership source of record for governed rollout and shared registry alignment.
- `docs/plans/03_prove_adaptive_routing.md`
  Closeout record for the original adaptive-routing investment decision.

## Experimental Capability Docs

- `docs/archive/README_STREAMLIT.md`
  Preserved historical UI workflow documentation.
- `docs/archive/README_SOCIAL_MEDIA_ANALYSIS.md`
  Preserved social-media analysis workflow documentation.
- `docs/archive/README_SOCIAL_MEDIA_UI.md`
  Preserved social-media UI documentation.

These documents are retained because the capabilities still exist in some form,
not because they define the current default repo surface.

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

Those capabilities are preserved as experimental or historical lanes and should
not be used as the default frame for the repository.
