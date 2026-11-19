---
id: decision-1
title: Pydantic models for tool schemas
date: '2026-11-19T21:28:00Z'
status: ruled-out
---
## Context

The tools each carry a small hand-written JSON schema in `input_schema`. A 2026-09-24 review proposed declaring them as Pydantic models instead.

## Decision

Ruled out 2026-09-24: 17 small, hand-written schemas; the tests cover them, and a dependency adds nothing here.

## Consequences

Schemas stay hand-written. Revisit only if the schema count or validation needs grow.
