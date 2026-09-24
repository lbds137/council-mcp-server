# Development Guide

This guide covers the development setup and workflow for the Council MCP Server project.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/lbds137/council-mcp-server.git
cd council-mcp-server

# Create the repo venv (the Makefile and pre-push hook use .venv)
python3 -m venv .venv

# Install with development dependencies and the git hooks
make install-dev
./scripts/install-hooks.sh

# Run tests
make test
```

## Development Tools

### Available Make Commands

```bash
make help          # Show all available commands
make install       # Install package in production mode
make install-dev   # Install package with dev dependencies
make test          # Run tests
make test-cov      # Run tests with coverage report
make lint          # Run ruff check
make format        # Sort imports and format code with ruff
make type-check    # Run mypy type checking
make pre-commit    # Run all pre-commit hooks
make clean         # Clean up generated files
make update-mcp    # Deploy to ~/.claude-mcp-servers/council (scripts/install.sh)
make check-models  # Find registry model IDs OpenRouter no longer lists
```

### Code Quality Tools

#### Ruff (Linter and Formatter)
- Lints (pycodestyle, pyflakes, isort, bugbear and pyupgrade rules) and formats
- Configuration in `pyproject.toml`
- Line length: 100 characters

```bash
# Lint
make lint

# Sort imports and format
make format

# Check formatting without changes
.venv/bin/python -m ruff format --check src/ tests/ scripts/
```

#### Mypy (Type Checker)
- Static type checking
- Checks untyped code too (`check_untyped_defs`)
- Configuration in `pyproject.toml`

```bash
# Run type checking
make type-check
```

### Pre-commit Hooks

Pre-commit hooks run automatically before each commit to ensure code quality.

#### Setup
```bash
# Install pre-commit hooks (done by make install-dev)
pre-commit install

# Run hooks manually
make pre-commit
```

#### Included Hooks
- **Trailing whitespace** removal
- **End-of-file fixer**
- **YAML/JSON/TOML** validation
- **Large file** prevention
- **Merge conflict** detection
- **ruff** linting and formatting

The pre-push hook (`hooks/pre-push`) runs ruff (lint and format check), mypy and
the full test suite before every push.

### Testing

#### Running Tests
```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test
.venv/bin/python -m pytest tests/unit/test_council/test_manager.py -v
```

#### Test Coverage
- Coverage reports in `htmlcov/` directory
- Minimum coverage target: 80%
- View HTML report: `open htmlcov/index.html`

### Continuous Integration

GitHub Actions runs on all pushes and pull requests:
- **Python versions**: 3.12, 3.13
- **Linting and formatting**: ruff
- **Type checking**: mypy
- **Tests**: pytest with coverage
- **Coverage**: Uploaded to Codecov

### Development Workflow

See "Shipping Changes" in `CLAUDE.md`: small fixes go straight to `main`, bigger
changes go through a pull request that is merged once CI is green.

1. **Create feature branch**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make changes and test**
   ```bash
   # Make your changes
   vim src/council/main.py

   # Run tests
   make test

   # Check code quality
   make lint format type-check
   ```

3. **Commit changes**
   ```bash
   # Pre-commit hooks run automatically
   git add .
   git commit -m "feat: add new feature"
   ```

4. **Push and create PR**
   ```bash
   git push origin feature/your-feature
   # Create pull request on GitHub
   ```

### Code Style Guidelines

1. **Follow PEP 8** with these modifications:
   - Line length: 100 characters
   - Use ruff for formatting

2. **Type hints** are required for all functions:
   ```python
   def process_data(input_str: str, count: int = 0) -> dict[str, Any]:
       """Process input data and return results."""
       ...
   ```

3. **Docstrings** required for all public functions:
   ```python
   def generate_content(self, prompt: str) -> tuple[str, str]:
       """
       Generate content with the active model.

       Args:
           prompt: The input prompt

       Returns:
           Tuple of (response_text, model_used)

       Raises:
           LLMProviderError: If generation fails
       """
   ```

4. **Import order** (handled by ruff):
   - Standard library
   - Third-party packages
   - Local imports

### Debugging Tips

1. **Enable debug logging**:
   ```python
   import logging

   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Run the server from source directly** (initialize first, then list tools):
   ```bash
   printf '%s\n' \
     '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"cli","version":"0"}}}' \
     '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | .venv/bin/python -m council.main
   ```

3. **Check pre-commit issues**:
   ```bash
   pre-commit run --all-files --verbose
   ```

### Release Process

1. **Update version** in:
   - `src/council/main.py`
   - `setup.py`
   - `CHANGELOG.md`

2. **Create and push tag**:
   ```bash
   git tag -a v2.1.0 -m "Release version 2.1.0"
   git push origin v2.1.0
   ```

3. **GitHub Actions** will automatically:
   - Run all tests
   - Build distribution packages
   - Create GitHub release
   - (Optional) Publish to PyPI
