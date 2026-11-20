---
id: TASK-1
title: >-
  credentials: pin the .env-key degradation path when the first-call decrypt
  fails (N1-a)
status: Deferred
assignee: []
created_date: '2026-11-19T21:27:00Z'
updated_date: '2026-11-20T02:12:00Z'
labels:
  - credentials
  - deferred
dependencies: []
priority: medium
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred; trigger: the next unit touching credentials or initialize. Pin with a test that a .env-introduced key whose decrypt fails at the first tool call leaves the ModelManager building from the .env key (and fix the behavior if the pin fails). Source: PR #43 review note N1, 2026-11-11. Behavior verified by code-reading only, not runtime-confirmed.
<!-- SECTION:DESCRIPTION:END -->
