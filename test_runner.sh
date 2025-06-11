#!/bin/bash
# Test runner script for IDE integration
# This avoids the file descriptor issues with pytest

cd "$(dirname "$0")"

# Run tests directly with Python to avoid pytest's capture issues
python tests/test_server.py "$@"
