"""Unit tests for the base tool."""

import asyncio

import pytest

from gemini_mcp.models.base import ToolInput, ToolMetadata
from gemini_mcp.tools.base import BaseTool


class ConcreteTestTool(BaseTool):
    """Concrete implementation for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.execution_count = 0
        super().__init__()

    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(name="test_tool", description="A test tool", tags=["test", "example"])

    async def _execute(self, input_data: ToolInput) -> str:
        self.execution_count += 1
        if self.should_fail:
            raise ValueError("Test error")
        return f"Processed: {input_data.parameters.get('input', 'no input')}"

    def _get_input_schema(self):
        return {
            "type": "object",
            "properties": {"input": {"type": "string", "description": "Test input"}},
            "required": ["input"],
        }


class TestBaseTool:
    """Test suite for BaseTool."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful tool execution."""
        tool = ConcreteTestTool()
        input_data = ToolInput(tool_name="test_tool", parameters={"input": "test value"})

        result = await tool.run(input_data)

        assert result.success is True
        assert result.tool_name == "test_tool"
        assert result.result == "Processed: test value"
        assert result.error is None
        assert result.execution_time_ms > 0
        assert tool.execution_count == 1

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        """Test tool execution with error."""
        tool = ConcreteTestTool(should_fail=True)
        input_data = ToolInput(tool_name="test_tool", parameters={"input": "test value"})

        result = await tool.run(input_data)

        assert result.success is False
        assert result.tool_name == "test_tool"
        assert result.result is None
        assert "Test error" in result.error
        assert result.execution_time_ms > 0
        assert tool.execution_count == 1

    def test_metadata_validation(self):
        """Test that metadata validation works."""

        class InvalidTool(BaseTool):
            def _get_metadata(self):
                return ToolMetadata(name="", description="Test")

            async def _execute(self, input_data):
                return "test"

            def _get_input_schema(self):
                return {}

        with pytest.raises(ValueError, match="Tool must have a name"):
            InvalidTool()

    def test_get_mcp_definition(self):
        """Test MCP definition generation."""
        tool = ConcreteTestTool()
        definition = tool.get_mcp_definition()

        assert definition["name"] == "test_tool"
        assert definition["description"] == "A test tool"
        assert "inputSchema" in definition
        assert definition["inputSchema"]["type"] == "object"
        assert "input" in definition["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_execution_timing(self):
        """Test that execution time is measured correctly."""
        tool = ConcreteTestTool()
        input_data = ToolInput(tool_name="test_tool", parameters={"input": "test"})

        # Add a small delay to the tool
        original_execute = tool._execute

        async def delayed_execute(input_data):
            await asyncio.sleep(0.01)  # 10ms delay
            return await original_execute(input_data)

        tool._execute = delayed_execute

        result = await tool.run(input_data)

        assert result.execution_time_ms >= 10  # At least 10ms
        assert result.execution_time_ms < 100  # But not too long

    @pytest.mark.asyncio
    async def test_metadata_in_output(self):
        """Test that tool metadata is included in output."""
        tool = ConcreteTestTool()
        input_data = ToolInput(tool_name="test_tool", parameters={"input": "test"})

        result = await tool.run(input_data)

        assert result.metadata is not None
        assert result.metadata["tags"] == ["test", "example"]
