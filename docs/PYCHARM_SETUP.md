# PyCharm Setup Guide

## Current Status

The tests run successfully in PyCharm (you'll see "4 passed" or "8 passed"), but PyCharm's test runner may show an error at the end: `ValueError: I/O operation on closed file`. This is a cosmetic issue - your tests are actually passing!

## Recommended Solutions

### Option 1: Use Python Script Configuration (Best)

1. Go to **Run → Edit Configurations**
2. Click the **+** button → **Python**
3. Configure:
   - **Script path**: `tests/test_server.py`
   - **Working directory**: `$PROJECT_DIR$`
   - **Name**: "All Tests"

### Option 2: Use the PyCharm Test Runner

1. Go to **Run → Edit Configurations**
2. Click the **+** button → **Python**
3. Configure:
   - **Script path**: `tests/test_runner_pycharm.py`
   - **Working directory**: `$PROJECT_DIR$`
   - **Name**: "Tests (PyCharm Runner)"

### Option 3: Use Terminal

PyCharm's integrated terminal works perfectly:
```bash
python tests/test_server.py
# or
pytest
```

### Option 4: Live with the Cosmetic Error

The default pytest integration works - the tests pass! The error at the end is just PyCharm's test reporter having issues with closed file handles. You can:
1. Ignore the error message
2. Look for the "X passed" message to confirm tests ran successfully

## Running Individual Tests

### For Individual Test Methods/Classes:

1. **Create a Python configuration**:
   - Script path: `tests/test_server.py`
   - Parameters: `TestClassName::test_method_name`
   - Example: `TestDualModelManager::test_initialization_success`

2. **Or use pytest in terminal**:
   ```bash
   pytest tests/test_server.py::TestDualModelManager::test_initialization_success -v
   ```

## Debugging Tests

Debugging works fine with any of these methods! The file descriptor issue only affects test output capture, not the debugger.

## Pro Tips

1. **Keyboard Shortcuts**:
   - `Shift+F10`: Run last configuration
   - `Shift+F9`: Debug last configuration
   - `Alt+Shift+F10`: Choose configuration to run

2. **Test Results Window**:
   - Even with the error, test results often still appear
   - Look for the test tree on the left side

3. **Terminal Alternative**:
   - PyCharm's terminal works great: `python tests/test_server.py`

## Understanding the Issue

The MCP server needs unbuffered I/O for real-time communication with Claude. We moved the file descriptor modifications to only happen when running as a server:

```python
def main():
    # Configure unbuffered output for proper MCP communication
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)
    
    server = GeminiMCPServer()
    server.run()
```

However, PyCharm's test runner (`_jb_pytest_runner.py`) has special handling that can still conflict with any code that touches file descriptors, even indirectly. The tests run successfully, but the test reporter fails at the end when trying to write the final summary.

## Why Tests Still Pass

Despite the error message, your tests are running correctly because:
1. The actual test execution completes successfully
2. You see "X passed" in the output
3. The error only occurs in PyCharm's test reporter cleanup phase
4. The exit code issue is from PyCharm's wrapper, not your tests