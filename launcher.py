#!/usr/bin/env python3
"""Launcher script for Council MCP Server v4

This launcher handles the Python path setup needed to run the bundled server
with dependencies from the development virtual environment. This is particularly
useful on systems where the system Python doesn't have the required packages.
"""

import os
import sys

# Get the directory where this launcher is located
LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))

# Try to find venv site-packages in common locations
# Priority order: sibling .venv, parent project .venv, system packages
VENV_PATHS = [
    # Sibling .venv (when launcher is in project root)
    os.path.join(LAUNCHER_DIR, ".venv", "lib", "python3.13", "site-packages"),
    os.path.join(LAUNCHER_DIR, ".venv", "lib", "python3.12", "site-packages"),
    os.path.join(LAUNCHER_DIR, ".venv", "lib", "python3.11", "site-packages"),
    # Hardcoded fallback for gemini-mcp-server project
    "/home/deck/PycharmProjects/gemini-mcp-server/.venv/lib/python3.13/site-packages",
]

# Add the first existing venv path to sys.path
for venv_path in VENV_PATHS:
    if os.path.exists(venv_path):
        sys.path.insert(0, venv_path)
        break

# Add the launcher directory to Python path (for server.py)
sys.path.insert(0, LAUNCHER_DIR)

# Import and run the server (must be after sys.path manipulation)
import server  # noqa: E402

if __name__ == "__main__":
    # Apply the tool registry override before running
    server._apply_tool_registry_override()

    # Call the main function
    server.main()
