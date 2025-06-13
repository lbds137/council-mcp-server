"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import time
import logging

from ..models.base import ToolInput, ToolOutput, ToolMetadata

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Abstract base class for all tools."""
    
    def __init__(self):
        self.metadata = self._get_metadata()
        self._validate_metadata()
    
    @abstractmethod
    def _get_metadata(self) -> ToolMetadata:
        """Return metadata for this tool."""
        pass
    
    @abstractmethod
    async def _execute(self, input_data: ToolInput) -> Any:
        """Execute the tool logic. Can be async for I/O operations."""
        pass
    
    def _validate_metadata(self):
        """Validate that metadata is properly configured."""
        if not self.metadata.name:
            raise ValueError("Tool must have a name")
        if not self.metadata.description:
            raise ValueError("Tool must have a description")
    
    async def run(self, input_data: ToolInput) -> ToolOutput:
        """Run the tool with timing and error handling."""
        start_time = time.time()
        
        try:
            logger.info(f"Executing tool: {self.metadata.name}")
            result = await self._execute(input_data)
            
            execution_time = (time.time() - start_time) * 1000
            
            return ToolOutput(
                tool_name=self.metadata.name,
                result=result,
                success=True,
                execution_time_ms=execution_time,
                metadata={"tags": self.metadata.tags}
            )
            
        except Exception as e:
            logger.error(f"Tool {self.metadata.name} failed: {e}")
            execution_time = (time.time() - start_time) * 1000
            
            return ToolOutput(
                tool_name=self.metadata.name,
                result=None,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    def get_mcp_definition(self) -> Dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "inputSchema": self._get_input_schema()
        }
    
    @abstractmethod
    def _get_input_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for tool inputs."""
        pass