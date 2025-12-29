"""Base class for all tools."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Simplified ToolOutput for bundled tools
class ToolOutput:
    """Standard output format for tool execution."""

    def __init__(self, success: bool, result: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.result = result
        self.error = error
        self.metadata: Dict[str, Any] = {}
        # Add missing attributes for compatibility with orchestrator
        self.tool_name: str = ""
        self.execution_time_ms: Optional[float] = None
        self.model_used: Optional[str] = None
        self.timestamp = None


class MCPTool(ABC):
    """Abstract base class for all tools using simplified property-based approach."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the tool description."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for tool inputs."""
        pass

    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        pass

    def get_mcp_definition(self) -> Dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


# Keep the original BaseTool for backwards compatibility during migration
class BaseTool(MCPTool):
    """Legacy base class that wraps MCPTool for backwards compatibility."""

    def __init__(self):
        # No-op for legacy compatibility
        pass

    @property
    def name(self) -> str:
        """Default to empty string for legacy tools."""
        return ""

    @property
    def description(self) -> str:
        """Default to empty string for legacy tools."""
        return ""

    @property
    def input_schema(self) -> Dict[str, Any]:
        """Default to empty schema for legacy tools."""
        return {"type": "object", "properties": {}, "required": []}
