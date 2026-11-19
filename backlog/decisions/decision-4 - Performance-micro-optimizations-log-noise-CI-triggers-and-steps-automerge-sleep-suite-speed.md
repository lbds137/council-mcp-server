---
id: decision-4
title: >-
  Performance micro-optimizations (log noise, CI triggers and steps, automerge
  sleep, suite speed)
date: '2026-11-19T21:28:00Z'
status: ruled-out
---
## Context

The 2026-11-10 performance review measured startup, CI and test hot paths, then took one read-only Fable review over the numbers.

## Decision

Ruled out 2026-11-10, item by item - measured savings under the fix's cost:

- Startup log noise (`core/registry.py:83`, `json_rpc.py:86`, the second `_load_env_file()` at `main.py:212`): 346 KB per 10 days against 10 MB x 5 log rotation.
- CI running on both `push` and `pull_request` (`ci.yml:4-7`): ~2 free runner-minutes per push, no wall-clock, and branches without a PR would lose CI.
- CI step speedups: uv ~10 s, mypy cache ~5 s, coverage ~4 s; CI at ~62 s/job is not the critical path - the ~90 s review is.
- The automerge `sleep 30` (`claude-code-review.yml:181`): guards Dependabot merges, and the file is a shared template.
- The test suite (623 tests in 3 s) and tool discovery (~4 ms).

## Consequences

Re-run the measurement before revisiting any item; the numbers above are the recheck baseline.
