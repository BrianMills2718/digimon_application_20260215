# DIGIMON Test Suite

This directory contains tests for multiple repo lanes. Not every preserved test
defines whether the current DIGIMON thesis lane is healthy.

## Test Lanes

Install `requirements.txt` for the core lane. Install
`requirements-dev.txt` when you want the broader pytest plugin/tooling surface
used by experimental and historical lanes.

### Core

Core tests cover the maintained default surface:

- benchmark harness
- graph manifest and capability checks
- active graph build CLI contracts
- operator package import safety

Run them with:

```bash
make test-core
make check-core
```

### Experimental

Experimental tests cover preserved but non-default capabilities:

- integration workflows
- broader agent-platform work
- preserved end-to-end experiments

Run them with:

```bash
make test-experimental
```

### Historical

Historical tests are preserved for reference but are not expected to be
portable-by-default. They often depend on machine-specific paths, old repo
layouts, or superseded workflows.

Run them with:

```bash
make test-historical
```

## Markers

- `@pytest.mark.core` - Maintained thesis-lane coverage
- `@pytest.mark.experimental` - Preserved but non-default capability coverage
- `@pytest.mark.historical` - Preserved legacy coverage
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.llm` - Tests requiring LLM API calls
- `@pytest.mark.requires_data` - Tests requiring specific data files

## Current Guidance

- New tests for benchmark, graph build, manifests, and active retrieval paths
  should default to `core`.
- Tests for preserved platform work should use `experimental`.
- Tests with hardcoded machine assumptions or obsolete workflows should use
  `historical` until repaired.

## Test Data

Test data files should be placed in `tests/fixtures/data/`. Use the
`test_data_dir` fixture to access them.

## CI And Verification

The repo should eventually enforce `core` as the default required lane. Until
then, treat `make test-core` as the authoritative health check for the active
surface and run experimental or historical lanes intentionally.
