---
id: TASK-2
title: >-
  credentials: test the credential replacing a .env-introduced
  ZAI_CODING_API_KEY at initialize (N1-b)
status: Deferred
assignee: []
created_date: '2026-11-19T21:27:00Z'
updated_date: '2026-11-20T02:12:00Z'
labels:
  - credentials
  - tests
  - deferred
dependencies:
  - TASK-1
priority: medium
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred; trigger: the next unit touching credentials or initialize; ships with TASK-1. Add a test where a .env-introduced ZAI_CODING_API_KEY is replaced by the stored credential before ModelManager reads it at initialize. Source: CI review of PR #43, finding 3.
<!-- SECTION:DESCRIPTION:END -->
