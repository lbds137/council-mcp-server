"""Gemini MCP Server - Enable Claude to collaborate with Google's Gemini AI"""

__version__ = "3.0.0"
__author__ = "Your Name"

# Global server instance for tools to access
_server_instance = None

# Don't import server at package level to avoid circular imports
__all__ = []
