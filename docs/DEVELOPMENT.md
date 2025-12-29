# Development Guide

This guide covers the development setup and workflow for the Council MCP Server project.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/lbds137/council-mcp-server.git
cd council-mcp-server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with development dependencies
make install-dev

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
make lint          # Run flake8 linting
make format        # Format code with black and isort
make type-check    # Run mypy type checking
make pre-commit    # Run all pre-commit hooks
make clean         # Clean up generated files
make update-mcp    # Update MCP installation
```

### Code Quality Tools

#### Black (Code Formatter)
- Automatically formats Python code
- Configuration in `pyproject.toml`
- Line length: 100 characters

```bash
# Format all code
make format

# Check formatting without changes
black --check src/ tests/
```

#### isort (Import Sorter)
- Sorts and organizes imports
- Configured to work with Black
- Groups: stdlib, third-party, local

```bash
# Sort imports
isort src/ tests/

# Check import order
isort --check-only src/ tests/
```

#### Flake8 (Linter)
- Checks for Python style issues
- Configuration in `.flake8`
- Max line length: 100

```bash
# Run linting
make lint
```

#### Mypy (Type Checker)
- Static type checking
- Strict mode enabled
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
- **Black** formatting
- **isort** import sorting
- **Flake8** linting
- **Mypy** type checking

### Testing

#### Running Tests
```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test
pytest tests/test_server.py::TestDualModelManager::test_initialization_success -v
```

#### Test Coverage
- Coverage reports in `htmlcov/` directory
- Minimum coverage target: 80%
- View HTML report: `open htmlcov/index.html`

### Continuous Integration

GitHub Actions runs on all pushes and pull requests:
- **Python versions**: 3.8, 3.9, 3.10, 3.11, 3.12
- **Linting**: flake8
- **Formatting**: black, isort
- **Type checking**: mypy
- **Tests**: pytest with coverage
- **Coverage**: Uploaded to Codecov

### Development Workflow

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
   - Use Black for formatting

2. **Type hints** are required for all functions:
   ```python
   def process_data(input_str: str, count: int = 0) -> Dict[str, Any]:
       """Process input data and return results."""
       ...
   ```

3. **Docstrings** required for all public functions:
   ```python
   def generate_content(self, prompt: str) -> Tuple[str, str]:
       """
       Generate content using Gemini models.

       Args:
           prompt: The input prompt

       Returns:
           Tuple of (response_text, model_used)

       Raises:
           Exception: If both models fail
       """
   ```

4. **Import order** (handled by isort):
   - Standard library
   - Third-party packages
   - Local imports

### Debugging Tips

1. **Enable debug logging**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Test MCP server directly**:
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python -m council.main
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
