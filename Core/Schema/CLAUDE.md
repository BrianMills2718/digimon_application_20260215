# Core/Schema

This subtree contains DIGIMON's typed slot and operator schema contracts.

## Working Rules

- Treat slot types, descriptors, and execution-plan models as first-class
  contracts.
- Schema drift here can invalidate composition and MCP behavior elsewhere, so
  keep it tightly coupled to runtime code.
