---
id: decision-2
title: Dependency injection or a plugin architecture
date: '2026-11-19T21:28:00Z'
status: ruled-out
---
## Context

Tool discovery (`src/council/core/registry.py`) imports every `tools/*.py` file and registers each concrete `MCPTool` subclass it defines. A 2026-09-24 review proposed dependency injection or a plugin architecture for the tool wiring instead.

## Decision

Ruled out 2026-09-24: one owner, one process; the registry's discovery is enough.

## Consequences

Adding a tool stays one file plus a `tools/__init__.py` export. Revisit if multiple server processes or external tool packages ever arrive.
