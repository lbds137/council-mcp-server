"""Gemini MCP Server - Enable Claude to collaborate with Google's Gemini AI"""

__version__ = "2.0.0"
__author__ = "Your Name"

from .server import GeminiMCPServer, DualModelManager

__all__ = ["GeminiMCPServer", "DualModelManager"]