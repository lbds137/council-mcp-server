"""Integration tests for the orchestrator."""

from typing import Any, Dict

import pytest

from gemini_mcp.core.orchestrator import ConversationOrchestrator
from gemini_mcp.core.registry import ToolRegistry
from gemini_mcp.services.cache import ResponseCache
from gemini_mcp.services.memory import ConversationMemory
from gemini_mcp.tools.base import MCPTool, ToolOutput
from tests.fixtures import create_mock_model_manager


class MockTestTool(MCPTool):
    """Mock tool for integration tests."""

    def __init__(self, tool_name: str = "test_tool"):
        self._name = tool_name
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Test tool {self._name}"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        self.call_count += 1
        # In the new architecture, model_manager is injected globally
        # For testing, we'll return a simple result
        return ToolOutput(success=True, result=f"Executed {self._name} with {parameters}")


class TestConversationOrchestrator:
    """Integration tests for ConversationOrchestrator."""

    @pytest.fixture
    def setup_orchestrator(self):
        """Set up orchestrator with dependencies."""
        registry = ToolRegistry()
        model_manager = create_mock_model_manager()
        memory = ConversationMemory()
        cache = ResponseCache()

        # Register test tools
        test_tool = MockTestTool("test_tool")
        registry._tools["test_tool"] = test_tool

        orchestrator = ConversationOrchestrator(
            tool_registry=registry, model_manager=model_manager, memory=memory, cache=cache
        )

        return orchestrator, registry, model_manager, memory, cache

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, setup_orchestrator):
        """Test successful tool execution."""
        orchestrator, registry, model_manager, memory, cache = setup_orchestrator

        result = await orchestrator.execute_tool(
            "test_tool", {"param": "value"}, request_id="test-123"
        )

        assert result.success is True
        assert "Executed test_tool with {'param': 'value'}" in result.result

        # Check execution history
        assert len(orchestrator.execution_history) == 1
        assert orchestrator.execution_history[0] == result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, setup_orchestrator):
        """Test executing an unknown tool."""
        orchestrator, _, _, _, _ = setup_orchestrator

        result = await orchestrator.execute_tool("unknown_tool", {"param": "value"})

        assert result.success is False
        assert "Unknown tool: unknown_tool" in result.error

    @pytest.mark.asyncio
    async def test_cache_integration(self, setup_orchestrator):
        """Test that caching works correctly."""
        orchestrator, registry, _, _, cache = setup_orchestrator

        # First execution
        result1 = await orchestrator.execute_tool("test_tool", {"param": "value"})

        # Check tool was called
        tool = registry.get_tool("test_tool")
        assert tool.call_count == 1

        # Second execution with same parameters
        result2 = await orchestrator.execute_tool("test_tool", {"param": "value"})

        # Should return cached result
        assert tool.call_count == 1  # Not called again
        assert result2.result == result1.result

        # Check cache stats
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_context_injection(self, setup_orchestrator):
        """Test that global model_manager is set for tools."""
        orchestrator, registry, model_manager, memory, _ = setup_orchestrator

        # Create a tool that uses global model_manager
        class ContextAwareTool(MCPTool):
            @property
            def name(self) -> str:
                return "context_tool"

            @property
            def description(self) -> str:
                return "Test"

            @property
            def input_schema(self) -> Dict[str, Any]:
                return {"type": "object"}

            async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
                # In bundled mode, model_manager would be global
                # For testing, we'll just verify the orchestrator has it
                assert orchestrator.model_manager is not None
                return ToolOutput(success=True, result="Context verified")

        # Register and execute
        context_tool = ContextAwareTool()
        registry._tools["context_tool"] = context_tool

        result = await orchestrator.execute_tool("context_tool", {})
        assert result.success is True
        assert result.result == "Context verified"

    @pytest.mark.asyncio
    async def test_failed_tool_not_cached(self, setup_orchestrator):
        """Test that failed tool executions are not cached."""
        orchestrator, registry, _, _, cache = setup_orchestrator

        # Create a failing tool
        class FailingTool(MockTestTool):
            async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
                self.call_count += 1
                return ToolOutput(success=False, error="Tool failed")

        failing_tool = FailingTool("failing_tool")
        registry._tools["failing_tool"] = failing_tool

        # Execute twice
        result1 = await orchestrator.execute_tool("failing_tool", {})
        result2 = await orchestrator.execute_tool("failing_tool", {})

        # Both should fail
        assert result1.success is False
        assert result2.success is False

        # Tool should be called twice (not cached)
        assert failing_tool.call_count == 2

        # Cache should have no hits
        stats = cache.get_stats()
        assert stats["hits"] == 0

    @pytest.mark.asyncio
    async def test_execute_protocol_simple(self, setup_orchestrator):
        """Test simple protocol execution."""
        orchestrator, _, _, _, _ = setup_orchestrator

        results = await orchestrator.execute_protocol(
            "simple", {"tool_name": "test_tool", "parameters": {"test": "value"}}
        )

        assert len(results) == 1
        assert results[0].success is True

    def test_get_execution_stats(self, setup_orchestrator):
        """Test execution statistics."""
        orchestrator, _, _, _, _ = setup_orchestrator

        # Create mock outputs with execution_time_ms attribute
        class MockOutput:
            def __init__(self, success, execution_time_ms):
                self.success = success
                self.execution_time_ms = execution_time_ms

        orchestrator.execution_history = [
            MockOutput(success=True, execution_time_ms=10),
            MockOutput(success=True, execution_time_ms=20),
            MockOutput(success=False, execution_time_ms=5),
        ]

        stats = orchestrator.get_execution_stats()

        assert stats["total_executions"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == 2 / 3
        assert stats["average_execution_time_ms"] == 35 / 3  # (10+20+5)/3
        assert "cache_stats" in stats
