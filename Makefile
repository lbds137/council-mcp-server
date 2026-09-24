# The repo venv when there is one, so targets don't pick up the system Python
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

# Generated files to clean; find never descends into these
PRUNE = -path ./.venv -prune -o -path ./.git -prune -o

.PHONY: help install install-dev test test-cov lint format type-check clean pre-commit update-mcp check-models

help:
	@echo "Available commands:"
	@echo "  make install       Install package in production mode"
	@echo "  make install-dev   Install package with dev dependencies"
	@echo "  make test          Run tests"
	@echo "  make test-cov      Run tests with coverage"
	@echo "  make lint          Run linting (ruff check)"
	@echo "  make format        Format code and sort imports (ruff)"
	@echo "  make type-check    Run type checking with mypy"
	@echo "  make pre-commit    Run all pre-commit hooks"
	@echo "  make clean         Clean up generated files"
	@echo "  make update-mcp    Deploy to ~/.claude-mcp-servers/council (scripts/install.sh)"
	@echo "  make check-models  Find registry model IDs OpenRouter no longer lists"

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) -m pre_commit install

test:
	$(PYTHON) -m pytest tests/ -v

test-cov:
	$(PYTHON) -m pytest tests/ -v --cov=council --cov-report=term-missing --cov-report=html

lint:
	$(PYTHON) -m ruff check src/ tests/ scripts/

format:
	$(PYTHON) -m ruff check --fix --select I src/ tests/ scripts/
	$(PYTHON) -m ruff format src/ tests/ scripts/

type-check:
	$(PYTHON) -m mypy src/

pre-commit:
	$(PYTHON) -m pre_commit run --all-files

clean:
	find . $(PRUNE) -type d -name "__pycache__" -exec rm -rf {} +
	find . $(PRUNE) -type f \( -name "*.pyc" -o -name "*.pyo" -o -name ".coverage" -o -name "coverage.xml" \) -delete
	find . $(PRUNE) -type d \( -name "*.egg-info" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name "htmlcov" \) -exec rm -rf {} +
	rm -rf ./build ./dist

update-mcp:
	./scripts/install.sh

check-models:
	$(PYTHON) scripts/check_models.py
