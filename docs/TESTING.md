# Testing Guide

## Running Tests

```bash
make test        # .venv/bin/python -m pytest tests/ -v
make test-cov    # with a coverage report (terminal and htmlcov/)

# One file or one test
.venv/bin/python -m pytest tests/unit/test_council/test_manager.py -v
.venv/bin/python -m pytest tests/unit/test_council/test_manager.py -k routing -v
```

PyCharm's built-in pytest runner works too; point it at `tests/`.

## Test Structure

- `tests/unit/test_council/`: providers (OpenRouter, Z.ai), the model manager,
  credentials, the model registry and filters, sessions
- `tests/unit/`: one file per tool (`test_<tool>_tool.py`), plus JSON-RPC,
  `main.py`, the tool registry and which tools may be cached
- `tests/integration/`: the orchestrator with real registry and cache objects
- `tests/test_bundler.py`: the single-file bundle generator

No test calls a real model: every provider call is mocked. To check the real
thing end to end, build the bundle and drive it over stdio (see
`docs/DEVELOPMENT.md`, Debugging Tips).

## Gates

The pre-push hook and CI (Python 3.12 and 3.13) both run ruff (lint and format
check), mypy and the full suite. A push or merge with a failing gate doesn't go out.
