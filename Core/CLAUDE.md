# Core

This subtree contains the production DIGIMON implementation: typed operator
contracts, composition logic, graph/runtime surfaces, MCP tools, and schema
definitions.

## Route By Responsibility

- operator-exposed MCP and agent tools -> `AgentTools/` and `MCP/`
- operator composition and execution-plan wiring -> `Composition/`
- operator implementations and registry -> `Operators/`
- typed contracts and slot schemas -> `Schema/`

## Working Rules

- Preserve the typed operator contract and the adaptive operator-routing model.
- Do not reintroduce fixed-pipeline assumptions into the core runtime.
