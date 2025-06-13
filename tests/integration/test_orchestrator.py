"""Integration tests for the orchestrator."""

import pytest

from gemini_mcp.core.orchestrator import ConversationOrchestrator
from gemini_mcp.core.registry import ToolRegistry
from gemini_mcp.models.base import ToolInput, ToolMetadata, ToolOutput
from gemini_mcp.services.cache import ResponseCache
from gemini_mcp.services.memory import ConversationMemory
from gemini_mcp.tools.base import BaseTool
from tests.fixtures import create_mock_model_manager


class MockTestTool(BaseTool):
    """Mock tool for integration tests."""

    def __init__(self, name: str = "test_tool"):
        self.name = name
        self.call_count = 0
        super().__init__()

    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(name=self.name, description=f"Test tool {self.name}")

    async def _execute(self, input_data: ToolInput) -> str:
        self.call_count += 1
        # Access model manager from context
        model_manager = input_data.context.get("model_manager")
        if model_manager:
            response, model = model_manager.generate_content("test prompt")
            return f"Tool result: {response}"
        return f"Executed {self.name} with {input_data.parameters}"

    def _get_input_schema(self):
        return {"type": "object", "properties": {}}


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
        assert result.tool_name == "test_tool"
        assert "Tool result: Test response" in result.result
        assert result.execution_time_ms > 0

        # Check execution history
        assert len(orchestrator.execution_history) == 1
        assert orchestrator.execution_history[0] == result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, setup_orchestrator):
        """Test executing an unknown tool."""
        orchestrator, _, _, _, _ = setup_orchestrator

        result = await orchestrator.execute_tool("unknown_tool", {"param": "value"})

        assert result.success is False
        assert result.error == "Unknown tool: unknown_tool"
        assert result.tool_name == "unknown_tool"

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
        assert result2 == result1

        # Check cache stats
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_context_injection(self, setup_orchestrator):
        """Test that context is properly injected into tools."""
        orchestrator, registry, model_manager, memory, _ = setup_orchestrator

        # Create a tool that uses context
        class ContextAwareTool(BaseTool):
            def _get_metadata(self):
                return ToolMetadata(name="context_tool", description="Test")

            async def _execute(self, input_data: ToolInput):
                context = input_data.context
                assert context.get("model_manager") == model_manager
                assert context.get("memory") == memory
                assert context.get("orchestrator") == orchestrator
                return "Context verified"

            def _get_input_schema(self):
                return {"type": "object"}

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
            async def _execute(self, input_data):
                self.call_count += 1
                raise ValueError("Tool failed")

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
        assert results[0].tool_name == "test_tool"

    def test_get_execution_stats(self, setup_orchestrator):
        """Test execution statistics."""
        orchestrator, _, _, _, _ = setup_orchestrator

        # Add some execution history
        orchestrator.execution_history = [
            ToolOutput(tool_name="tool1", result="ok", success=True, execution_time_ms=10),
            ToolOutput(tool_name="tool2", result="ok", success=True, execution_time_ms=20),
            ToolOutput(tool_name="tool3", result=None, success=False, execution_time_ms=5),
        ]

        stats = orchestrator.get_execution_stats()

        assert stats["total_executions"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == 2 / 3
        assert stats["average_execution_time_ms"] == 35 / 3  # (10+20+5)/3
        assert "cache_stats" in stats
