"""Integration tests for the orchestrator."""

from typing import Any, Dict

import pytest

from council.core.orchestrator import ConversationOrchestrator
from council.core.registry import ToolRegistry
from council.services.cache import ResponseCache
from council.tools.base import MCPTool, ToolOutput
from tests.fixtures import create_mock_model_manager


class MockTestTool(MCPTool):
    """Mock tool for integration tests."""

    def __init__(self, tool_name: str = "test_tool", cacheable: bool = True):
        self._name = tool_name
        self.cacheable = cacheable
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

    def is_cacheable(self, parameters: Dict[str, Any]) -> bool:
        return self.cacheable

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
        cache = ResponseCache()

        # Register test tools
        test_tool = MockTestTool("test_tool")
        registry._tools["test_tool"] = test_tool

        orchestrator = ConversationOrchestrator(
            tool_registry=registry, model_manager=model_manager, cache=cache
        )

        return orchestrator, registry, model_manager, cache

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, setup_orchestrator):
        """Test successful tool execution."""
        orchestrator, registry, model_manager, cache = setup_orchestrator

        result = await orchestrator.execute_tool(
            "test_tool", {"param": "value"}, request_id="test-123"
        )

        assert result.success is True
        assert "Executed test_tool with {'param': 'value'}" in result.result

        assert orchestrator.total_executions == 1
        assert orchestrator.successful_executions == 1
        assert result.execution_time_ms is not None

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, setup_orchestrator):
        """Test executing an unknown tool."""
        orchestrator, _, _, _ = setup_orchestrator

        result = await orchestrator.execute_tool("unknown_tool", {"param": "value"})

        assert result.success is False
        assert "Unknown tool: unknown_tool" in result.error

    @pytest.mark.asyncio
    async def test_cache_integration(self, setup_orchestrator):
        """Test that caching works correctly."""
        orchestrator, registry, _, cache = setup_orchestrator

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
    async def test_a_result_can_veto_its_own_caching(self, setup_orchestrator):
        """Test a result flagged cacheable=False (e.g. a partial debate) is not cached."""
        orchestrator, registry, _, cache = setup_orchestrator

        class PartialTool(MockTestTool):
            async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
                self.call_count += 1
                output = ToolOutput(success=True, result="partial")
                output.metadata["cacheable"] = False
                return output

        partial = PartialTool("partial_tool")
        registry._tools["partial_tool"] = partial

        await orchestrator.execute_tool("partial_tool", {"q": 1})
        await orchestrator.execute_tool("partial_tool", {"q": 1})

        assert partial.call_count == 2
        assert cache.get_stats()["size"] == 0

    @pytest.mark.asyncio
    async def test_tools_that_do_not_opt_in_are_never_cached(self, setup_orchestrator):
        """Test a state-changing tool runs on every call, even with the same input."""
        orchestrator, registry, _, cache = setup_orchestrator
        stateful = MockTestTool("set_something", cacheable=False)
        registry._tools["set_something"] = stateful

        await orchestrator.execute_tool("set_something", {"model": "x"})
        await orchestrator.execute_tool("set_something", {"model": "x"})

        assert stateful.call_count == 2
        assert cache.get_stats()["size"] == 0

    @pytest.mark.asyncio
    async def test_switching_the_active_model_misses_the_cache(self, setup_orchestrator):
        """Test an answer cached under one active model isn't served for another."""
        orchestrator, registry, model_manager, _ = setup_orchestrator
        tool = registry.get_tool("test_tool")

        model_manager.active_model = "model-a"
        await orchestrator.execute_tool("test_tool", {"question": "hi"})
        model_manager.active_model = "model-b"
        await orchestrator.execute_tool("test_tool", {"question": "hi"})
        model_manager.active_model = "model-a"
        await orchestrator.execute_tool("test_tool", {"question": "hi"})

        assert tool.call_count == 2

    @pytest.mark.asyncio
    async def test_model_override_is_part_of_the_cache_key(self, setup_orchestrator):
        """Test the same question to two override models runs twice."""
        orchestrator, registry, _, _ = setup_orchestrator
        tool = registry.get_tool("test_tool")

        await orchestrator.execute_tool("test_tool", {"question": "hi", "model": "a"})
        await orchestrator.execute_tool("test_tool", {"question": "hi", "model": "b"})

        assert tool.call_count == 2

    @pytest.mark.asyncio
    async def test_context_injection(self, setup_orchestrator):
        """Test that global model_manager is set for tools."""
        orchestrator, registry, model_manager, _ = setup_orchestrator

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
        orchestrator, registry, _, cache = setup_orchestrator

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

    def test_get_execution_stats(self, setup_orchestrator):
        """Test execution statistics."""
        orchestrator, _, _, _ = setup_orchestrator

        orchestrator.total_executions = 3
        orchestrator.successful_executions = 2
        orchestrator.total_execution_ms = 35.0

        stats = orchestrator.get_execution_stats()

        assert stats["total_executions"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == 2 / 3
        assert stats["average_execution_time_ms"] == 35 / 3  # (10+20+5)/3
        assert "cache_stats" in stats
