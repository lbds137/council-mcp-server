#!/usr/bin/env python
"""PyCharm-compatible test runner that handles file descriptor issues"""

import sys
import subprocess
import os

# Get the directory containing this script
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(test_dir)

# Run the tests using subprocess to isolate file descriptor issues
result = subprocess.run(
    [sys.executable, os.path.join(test_dir, "test_server.py")],
    cwd=project_root,
    capture_output=True,
    text=True
)

# Print the output
print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)

# Exit with the same code
sys.exit(result.returncode)