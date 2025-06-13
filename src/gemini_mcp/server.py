#!/usr/bin/env python3
"""
Minimal server entry point that imports and runs the modular MCP server.
This file exists for backwards compatibility and to provide a clean entry point.
"""

from .main import main

if __name__ == "__main__":
    main()
