---
id: TASK-4
title: 'providers: lazy-import openai (0.46 s of the 0.59 s import)'
status: Deferred
assignee: []
created_date: '2026-11-19T21:27:00Z'
labels:
  - providers
  - perf
  - deferred
dependencies: []
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred; trigger: after the credentials/initialize tasks above ship AND startup time still matters. providers/openrouter.py:9 and providers/zai.py:15 pull 0.46 s of the 0.59 s import, about 4.6 s/day across background sessions (measured 2026-11-10). Cost: 26 test patches target the module-level OpenAI client, so the rewrite costs more than it saves on its own.
<!-- SECTION:DESCRIPTION:END -->
