"""Council MCP Server - Multi-LLM collaboration server for Claude Code"""

from typing import Any

__version__ = "4.0.0"
__author__ = "lbds137"

# Global server instance for tools to access
# (a CouncilMCPServer; typed Any to avoid a circular import)
_server_instance: Any = None

# Don't import server at package level to avoid circular imports
__all__: list[str] = []
