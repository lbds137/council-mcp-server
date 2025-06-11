.PHONY: help install install-dev test test-cov lint format type-check clean pre-commit update-mcp

help:
	@echo "Available commands:"
	@echo "  make install       Install package in production mode"
	@echo "  make install-dev   Install package with dev dependencies"
	@echo "  make test          Run tests"
	@echo "  make test-cov      Run tests with coverage"
	@echo "  make lint          Run linting (flake8)"
	@echo "  make format        Format code with black and isort"
	@echo "  make type-check    Run type checking with mypy"
	@echo "  make pre-commit    Run all pre-commit hooks"
	@echo "  make clean         Clean up generated files"
	@echo "  make update-mcp    Update MCP installation"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ -v --cov=gemini_mcp --cov-report=term-missing --cov-report=html

lint:
	flake8 src/ tests/

format:
	black src/ tests/
	isort src/ tests/

type-check:
	mypy src/

pre-commit:
	pre-commit run --all-files

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +

update-mcp:
	./scripts/update.sh
