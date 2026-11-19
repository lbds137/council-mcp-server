---
id: TASK-3
title: >-
  credentials: skip the decrypt-and-rebuild on same-process re-initialize, or
  class-default the _load_env_file fallback (N1-c)
status: Deferred
assignee: []
created_date: '2026-11-19T21:27:00Z'
labels:
  - credentials
  - deferred
dependencies: []
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred; trigger: the next unit touching credentials or initialize. Either skip the decrypt-and-rebuild on a same-process re-initialize when the orchestrator already exists, or replace the test-only hasattr fallback in _load_env_file with a class-level default. Source: CI review of PR #43, findings 1-2. Known edge, accepted 2026-11-11 (finding 1): in a credential-only setup a same-process re-initialize treats the credential-set key as pre-startup, decrypts again (about 3 s) and rebuilds the manager and orchestrator; rare, because reconnects are new processes.
<!-- SECTION:DESCRIPTION:END -->
