---
id: decision-3
title: devcontainer / Dockerfile
date: '2026-11-19T21:28:00Z'
status: ruled-out
---
## Context

A 2026-09-24 review proposed a devcontainer or Dockerfile for reproducible development environments.

## Decision

Ruled out 2026-09-24: the server runs on the host, from the venv that `scripts/install.sh` creates.

## Consequences

Development assumes the host toolchain (mise-managed Python, `.venv/bin/python -m pytest`). Containers stay limited to the podman services (postgres, redis) the environment already runs.
