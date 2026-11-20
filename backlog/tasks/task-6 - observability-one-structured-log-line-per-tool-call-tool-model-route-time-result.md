---
id: TASK-6
title: >-
  observability: one structured log line per tool call (tool, model, route,
  time, result)
status: Deferred
assignee: []
created_date: '2026-11-19T21:27:00Z'
updated_date: '2026-11-20T02:12:00Z'
labels:
  - observability
  - deferred
dependencies: []
priority: low
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred; trigger: fallback rates need regular tracking. One log line per tool call with the tool, the model it resolved to, the route (Z.ai plan or OpenRouter), the time taken and the result would make how-often-does-the-plan-fall-back answerable from the log. server_info counters cover the basics today; the 2026-09-27 fallback question was answered with one pass over the existing log; the week to 2026-10-04 had 4 tool calls in all.
<!-- SECTION:DESCRIPTION:END -->
