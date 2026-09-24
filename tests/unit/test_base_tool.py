"""Unit tests for the base tool."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest

from council.tools.base import MCPTool, ToolOutput, get_model_manager, get_server


class ConcreteTestTool(MCPTool):
    """Concrete implementation for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.execution_count = 0

    @property
    def name(self) -> str:
        return "test_tool"

    @property
    def description(self) -> str:
        return "A test tool"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"input": {"type": "string", "description": "Test input"}},
            "required": ["input"],
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        self.execution_count += 1
        if self.should_fail:
            return ToolOutput(success=False, error="Test error")

        result = f"Processed: {parameters.get('input', 'no input')}"
        output = ToolOutput(success=True, result=result)
        output.metadata = {"tags": ["test", "example"]}
        return output


class InvalidTool(MCPTool):
    """Invalid tool for testing validation."""

    @property
    def name(self) -> str:
        return ""  # Invalid empty name

    @property
    def description(self) -> str:
        return "Test"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        return ToolOutput(success=True, result="test")


class TestBaseTool:
    """Test suite for BaseTool."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful tool execution."""
        tool = ConcreteTestTool()
        parameters = {"input": "test value"}

        result = await tool.execute(parameters)

        assert result.success is True
        assert result.result == "Processed: test value"
        assert result.error is None
        assert tool.execution_count == 1

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        """Test tool execution with error."""
        tool = ConcreteTestTool(should_fail=True)
        parameters = {"input": "test value"}

        result = await tool.execute(parameters)

        assert result.success is False
        assert result.result is None
        assert "Test error" in result.error
        assert tool.execution_count == 1

    def test_metadata_validation(self):
        """Test that tools can be created with empty names (no validation in new API)."""
        # The new API doesn't validate metadata in __init__
        # so we just test that the tool can be created
        tool = InvalidTool()
        assert tool.name == ""
        assert tool.description == "Test"

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
        """Test that execution with delay works correctly."""
        tool = ConcreteTestTool()
        parameters = {"input": "test"}

        # Add a small delay to the tool
        original_execute = tool.execute

        async def delayed_execute(params):
            await asyncio.sleep(0.01)  # 10ms delay
            return await original_execute(params)

        tool.execute = delayed_execute

        result = await tool.execute(parameters)

        assert result.success is True
        assert result.result == "Processed: test"

    @pytest.mark.asyncio
    async def test_metadata_in_output(self):
        """Test that tool metadata can be included in output."""
        tool = ConcreteTestTool()
        parameters = {"input": "test"}

        result = await tool.execute(parameters)

        assert result.metadata is not None
        assert result.metadata["tags"] == ["test", "example"]


class TestServerLookup:
    """How tools reach the running server and its model manager."""

    def test_nothing_before_the_server_starts(self):
        """With no server instance, both lookups return None."""
        with patch("council._server_instance", None):
            assert get_server() is None
            assert get_model_manager() is None

    def test_server_without_a_manager_yet(self):
        """A server whose manager isn't initialized gives no manager."""
        with patch("council._server_instance", SimpleNamespace(model_manager=None)):
            assert get_model_manager() is None

    def test_reads_the_current_instance_at_call_time(self):
        """The lookup sees an instance set after the tools module was imported."""
        manager = Mock()
        server = SimpleNamespace(model_manager=manager)
        with patch("council._server_instance", server):
            assert get_server() is server
            assert get_model_manager() is manager
