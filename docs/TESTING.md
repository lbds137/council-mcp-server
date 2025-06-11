# Testing Guide

## Running Tests

The tests can now be run normally with pytest! The stdout/stderr modifications have been moved to only occur when the server is actually running, not during imports.

### Method 1: Using pytest (Recommended)
```bash
pytest
# or with verbose output
pytest -v
```

### Method 2: Direct Python Execution
```bash
python tests/test_server.py
```

### Method 3: In PyCharm/IDE

PyCharm should now work normally with its default pytest integration! You can:
- Right-click on test files or individual tests and run them
- Use the green arrows in the gutter
- Use the default pytest run configurations

## How It Works

The server now only modifies stdout/stderr when actually running as a server:
```python
def main():
    # Configure unbuffered output for proper MCP communication
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)
    
    server = GeminiMCPServer()
    server.run()
```

This ensures unbuffered output for proper JSON-RPC communication with Claude when running as an MCP server, while avoiding conflicts with pytest during testing.

## Test Structure

- `TestDualModelManager`: Tests the dual-model fallback functionality
- `TestGeminiMCPServer`: Tests the MCP protocol implementation

All tests use mocking to avoid actual API calls to Google's Gemini service.