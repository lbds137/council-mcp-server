"""Orchestrator: runs tools, caches results that may be reused, and counts executions."""

import logging
import time
from typing import Any, Dict, Optional

from ..services.cache import ResponseCache
from ..tools.base import ToolOutput
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """Runs tools for the server, with caching and execution counts."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        model_manager: Any,
        cache: Optional[ResponseCache] = None,
    ):
        self.tool_registry = tool_registry
        self.model_manager = model_manager
        self.cache = cache or ResponseCache()
        self.total_executions = 0
        self.successful_executions = 0
        self.total_execution_ms = 0.0

    async def execute_tool(
        self, tool_name: str, parameters: Dict[str, Any], request_id: Optional[str] = None
    ) -> ToolOutput:
        """Execute a single tool, serving a cached result when the tool allows it."""
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            output = ToolOutput(success=False, error=f"Unknown tool: {tool_name}")
            output.tool_name = tool_name
            return output

        cache_key = self._cache_key(tool, tool_name, parameters)
        if cache_key:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for {tool_name}")
                return cached_result

        started = time.monotonic()
        output = await tool.execute(parameters)
        output.execution_time_ms = (time.monotonic() - started) * 1000

        # A tool can veto caching one result, e.g. a partial one
        if cache_key and output.success and output.metadata.get("cacheable", True):
            self.cache.set(cache_key, output)

        self.total_executions += 1
        if output.success:
            self.successful_executions += 1
        self.total_execution_ms += output.execution_time_ms

        return output

    def _cache_key(self, tool: Any, tool_name: str, parameters: Dict[str, Any]) -> Optional[str]:
        """The cache key for this call, or None when the result must not be cached.

        The key names the model that will answer, so switching the active
        model never serves the previous model's answer.
        """
        if not tool.is_cacheable(parameters):
            return None
        model = parameters.get("model") or getattr(self.model_manager, "active_model", None)
        return self.cache.create_key(tool_name, {"parameters": parameters, "model": model})

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics about tool executions."""
        total = self.total_executions
        successful = self.successful_executions
        failed = total - successful
        avg_time = self.total_execution_ms / total if total else 0.0

        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "average_execution_time_ms": avg_time,
            "cache_stats": self.cache.get_stats(),
        }
