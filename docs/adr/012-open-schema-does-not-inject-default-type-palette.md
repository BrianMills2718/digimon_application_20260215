# ADR-012: Open Schema Mode Does Not Inject a Hidden Default Type Palette

**Status**: Accepted
**Date**: 2026-03-22

## Context

DIGIMON now distinguishes `schema_mode=open`, `schema_guided`, and
`schema_constrained` in both config and docs. But the live extraction contract
was still inconsistent with that model:

- `GraphConfig` defaults to `schema_mode=open`
- `resolve_entity_type_names()` fell back to `DEFAULT_ENTITY_TYPES`
  (`organization`, `person`, `geo`, `event`) when no explicit type palette was
  declared
- the active one-pass and two-pass prompt builders rendered that fallback as
  `One of the following types when applicable: [...]`

That meant `open` mode was not actually open in practice. It quietly behaved
like a weak closed palette, and the remaining completeness misses (`throat
cancer`, `Silver Ball`) are exactly the kinds of entities excluded by that
fallback.

## Decision

For `schema_mode=open`, DIGIMON will no longer inject a hidden default entity
type palette when no explicit palette is declared.

Concrete rules:

1. If `schema_mode=open` and there is no explicit `schema_entity_types` list
   and no custom ontology entity list, `resolve_entity_type_names()` returns an
   empty list.
2. Prompt builders must treat an empty type list as a distinct contract:
   - do not say “one of the following types”
   - instead ask for a short reusable semantic class for the entity
3. If the caller explicitly provides `schema_entity_types` or a custom ontology
   entity list, that explicit palette remains authoritative even in `open`
   mode.
4. `schema_guided` and `schema_constrained` keep their existing declared-schema
   behavior.

## Consequences

### Positive

- `open` mode becomes truthful instead of silently constrained.
- Open-TKG extraction can emit classes such as diagnoses, awards, titles, and
  works without first fighting a four-class fallback palette.
- Docs, config semantics, and prompt behavior align.

### Negative

- Fully open extraction may produce a wider variety of type labels, which can
  increase normalization work later.
- Existing assumptions that `open` still implies the four default classes are
  no longer valid.

### Constraints

- TKG and RKG still require non-placeholder entity types; this ADR changes the
  source of the type vocabulary, not the requirement to type entities.
- Do not reintroduce a hidden fallback palette under another name. If DIGIMON
  wants a broader default open palette later, it must be explicit in config and
  manifest truth.
