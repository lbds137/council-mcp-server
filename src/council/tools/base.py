"""Base class for all tools."""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# Simplified ToolOutput for bundled tools
class ToolOutput:
    """Standard output format for tool execution."""

    def __init__(self, success: bool, result: str | None = None, error: str | None = None):
        self.success = success
        self.result = result
        self.error = error
        self.metadata: dict[str, Any] = {}
        # Add missing attributes for compatibility with orchestrator
        self.tool_name: str = ""
        self.execution_time_ms: float | None = None
        self.model_used: str | None = None
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
    def input_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool inputs."""
        pass

    @abstractmethod
    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        pass

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """Whether a successful result may be served again for the same input.

        Only tools whose answer depends on nothing but their input and the
        model opt in. A tool that reads or changes server state must not.
        """
        return False

    def get_mcp_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
