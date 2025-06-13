"""Orchestrator for managing tool execution and conversation flow."""

import logging
from typing import Any, Dict, List, Optional

from ..models.base import ToolOutput
from ..protocols.debate import DebateProtocol
from ..services.cache import ResponseCache
from ..services.memory import ConversationMemory
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """Orchestrates tool execution and manages conversation flow."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        model_manager: Any,  # DualModelManager
        memory: Optional[ConversationMemory] = None,
        cache: Optional[ResponseCache] = None,
    ):
        self.tool_registry = tool_registry
        self.model_manager = model_manager
        self.memory = memory or ConversationMemory()
        self.cache = cache or ResponseCache()
        self.execution_history: List[ToolOutput] = []

    async def execute_tool(
        self, tool_name: str, parameters: Dict[str, Any], request_id: Optional[str] = None
    ) -> ToolOutput:
        """Execute a single tool with proper context injection."""

        # Check cache first
        cache_key = self.cache.create_key(tool_name, parameters)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {tool_name}")
            return cached_result

        # Get the tool
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return ToolOutput(
                tool_name=tool_name, result=None, success=False, error=f"Unknown tool: {tool_name}"
            )

        # Create tool input with context (kept for reference, though not used in new API)
        # tool_input = ToolInput(
        #     tool_name=tool_name,
        #     parameters=parameters,
        #     context={
        #         "model_manager": self.model_manager,
        #         "memory": self.memory,
        #         "orchestrator": self,
        #     },
        #     request_id=request_id,
        # )

        # Execute the tool with just parameters (new API)
        output = await tool.execute(parameters)

        # Cache successful results
        if output.success:
            self.cache.set(cache_key, output)

        # Store in execution history
        self.execution_history.append(output)

        # Update memory if needed
        if output.success and hasattr(tool, "update_memory"):
            tool.update_memory(self.memory, output)

        return output

    async def execute_protocol(
        self, protocol_name: str, initial_input: Dict[str, Any]
    ) -> List[ToolOutput]:
        """Execute a multi-step protocol (e.g., debate, synthesis)."""
        logger.info(f"Executing protocol: {protocol_name}")

        # Example: Simple sequential execution
        if protocol_name == "simple":
            return [
                await self.execute_tool(
                    initial_input.get("tool_name"), initial_input.get("parameters")
                )
            ]

        # Debate protocol
        elif protocol_name == "debate":
            topic = initial_input.get("topic", "")
            positions = initial_input.get("positions", [])

            if not topic or not positions:
                return [
                    ToolOutput(
                        tool_name="debate_protocol",
                        result=None,
                        success=False,
                        error="Debate protocol requires 'topic' and 'positions' parameters",
                    )
                ]

            debate = DebateProtocol(self, topic, positions)
            try:
                result = await debate.run()
                return [
                    ToolOutput(
                        tool_name="debate_protocol",
                        result=result,
                        success=True,
                        metadata={"protocol": "debate", "rounds": len(result.get("rounds", []))},
                    )
                ]
            except Exception as e:
                logger.error(f"Debate protocol error: {e}")
                return [
                    ToolOutput(
                        tool_name="debate_protocol", result=None, success=False, error=str(e)
                    )
                ]

        # Synthesis protocol (simple wrapper around synthesize tool)
        elif protocol_name == "synthesis":
            return [
                await self.execute_tool(
                    "synthesize_perspectives", initial_input.get("parameters", {})
                )
            ]

        # Protocol not implemented
        raise NotImplementedError(f"Protocol {protocol_name} not implemented")

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics about tool executions."""
        total = len(self.execution_history)
        successful = sum(1 for output in self.execution_history if output.success)
        failed = total - successful

        avg_time = 0
        if total > 0:
            times = [o.execution_time_ms for o in self.execution_history if o.execution_time_ms]
            avg_time = sum(times) / len(times) if times else 0

        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "average_execution_time_ms": avg_time,
            "cache_stats": self.cache.get_stats(),
        }
