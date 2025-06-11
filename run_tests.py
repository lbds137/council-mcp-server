#!/usr/bin/env python
"""Test runner script for IDE integration"""

import subprocess
import sys

# Run pytest with the given arguments or default to all tests
args = sys.argv[1:] if len(sys.argv) > 1 else ["tests/", "-v"]

# Run pytest directly without the -m flag to avoid file descriptor issues
result = subprocess.run([sys.executable, "-m", "pytest"] + args)

# Exit with the same code as pytest
sys.exit(result.returncode)
