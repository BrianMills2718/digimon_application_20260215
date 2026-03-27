# Repo Surface

DIGIMON preserves multiple capability lanes. They should not all sit on the
same operational path.

## Core

The `core` lane is the maintained default surface. It exists to support the
current thesis:

> adaptive graph-assisted retrieval for multi-hop QA should beat simpler
> baselines enough to justify further investment

Core includes:

- graph build and enrichment
- active retrieval operators needed for benchmark modes
- direct benchmark backend
- operator consolidation
- benchmark prompts
- graph manifests and evaluation
- the small set of tests required to keep that path reproducible

Core is allowed to block work. If core breaks, the repo is not healthy.

## Experimental

The `experimental` lane preserves broader capabilities that may become
important again, but are not the default maintained path today.

Examples:

- agent-platform and orchestration work
- memory systems
- social-media analysis tooling
- cross-modal tooling
- broader integration experiments

Experimental capabilities should be:

- lazy-loaded or explicitly enabled
- documented as non-default
- tested separately from core

Experimental breakage should not block core thesis work.

## Historical

The `historical` lane preserves older workflows, tests, and docs that still
carry reference value but are not portable or current enough to define repo
health.

Examples:

- machine-specific end-to-end tests
- old UI workflows
- obsolete scripts with old repo assumptions

Historical assets should be kept only when they still provide recovery value,
reference value, or a migration path.

## Default Rule

Ask one question before putting anything on the default path:

> does this capability need to work, by default, to prove the DIGIMON thesis?

If the answer is no, preserve it outside the default surface.
