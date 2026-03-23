# ADR-013: Represent Answer-Critical Facts by Operator Utility, Not Topic

**Status**: Accepted
**Date**: 2026-03-22

## Context

DIGIMON is a graph-based retrieval system, not just a graph-shaped storage
format. The core question is not whether a phrase "looks like an entity." The
core question is whether a fact must be directly operable for the retrieval and
reasoning patterns the benchmark requires.

Recent extraction-quality work exposed a recurring ambiguity:

- some answer-critical information can end up buried only in node descriptions
- that makes the fact visible to inspection, but not necessarily reachable by
  the operator families DIGIMON actually exposes
- if DIGIMON reacts by promoting every detailed phrase to a node, the ontology
  becomes noisy and benchmark-shaped

The missing design rule is how to choose between:

- node
- edge
- attribute
- chunk-only evidence

This decision must be driven by retrieval utility, not by topic labels such as
medical, sports, awards, or law.

## Decision

Choose fact representation by **operator utility** and **benchmark reasoning
role**, not by topic.

### Core Principle

The graph should contain the smallest amount of structure that unlocks the
retrieval/composition behaviors the benchmark actually needs.

### Representation Rules

1. **Node**
   - Use when the fact/concept needs identity-like behavior:
     - can act as a seed, target, or bridge
     - may recur across chunks/documents
     - benefits from traversal, linking, PPR, path extraction, or community use
     - needs evidence merged from multiple places

2. **Edge**
   - Use when the retrieval value is primarily in the connection between two
     addressable nodes:
     - relation traversal matters
     - path composition matters
     - relation ranking/aggregation matters

3. **Attribute**
   - Use when the fact mainly qualifies a node or edge:
     - scalar or low-branching value
     - mostly used for filtering, sorting, comparison, or answer rendering
     - does not usually need its own graph navigation
   - Important constraint: an attribute is only a good choice if DIGIMON has,
     or plans to add, operators that can actually use it.

4. **Chunk-Only Evidence**
   - Leave a fact in chunk evidence when:
     - it is local to one chunk
     - graph structure adds little compositional value
     - chunk retrieval can recover it reliably
     - it is mainly needed for support/synthesis rather than structural reuse

### Additional Constraints

- Do not materialize every detailed phrase as a node just because it is
  answer-relevant in one case.
- Do not leave answer-critical facts only as buried description text when the
  retrieval plan needs direct addressing.
- Compact profile outputs are acceptable, but there must be an explicit path to
  the best available full evidence.
- Representation decisions must be benchmark reasoning-pattern driven, not
  topic driven.

## Consequences

### Positive

- DIGIMON can reason about ontology choices in a benchmark-general way.
- Node explosion becomes easier to resist.
- Representation decisions align with the actual operator surface.
- Future extraction work can ask "what must be operable?" instead of "what noun
  phrase should become an entity?"

### Negative

- This raises the design bar for extraction changes; "recover one phrase" is no
  longer sufficient reasoning.
- DIGIMON must explicitly document where attribute support is currently weak.
- Some current extraction debates now require operator-surface decisions, not
  just prompt wording changes.

### DIGIMON-Specific Implication

Today DIGIMON is strongest on nodes and edges, weaker on attributes, and only
partially explicit about evidence resolution from compact profiles to full
supporting text. That means some facts that are theoretically attribute-shaped
may still need temporary node/edge treatment until the operator surface grows.
