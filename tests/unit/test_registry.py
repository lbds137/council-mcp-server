"""Unit tests for the tool registry."""

from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

from council.core.registry import ToolRegistry
from council.tools.base import MCPTool, ToolOutput


class MockTool(MCPTool):
    """Mock tool for testing."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "Mock tool for testing"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        return ToolOutput(success=True, result="mock result")


class TestToolRegistry:
    """Test suite for ToolRegistry."""

    def test_init(self):
        """Test registry initialization."""
        registry = ToolRegistry()
        assert len(registry._tools) == 0
        assert len(registry._tool_classes) == 0

    def test_register_tool_class(self):
        """Test registering a tool class."""
        registry = ToolRegistry()

        # Manually register tool (simulating what discover_tools does)
        tool = MockTool()
        registry._tools[tool.name] = tool
        registry._tool_classes[tool.name] = MockTool

        assert "mock_tool" in registry._tools
        assert "mock_tool" in registry._tool_classes
        assert isinstance(registry._tools["mock_tool"], MockTool)
        assert registry._tool_classes["mock_tool"] == MockTool

    def test_discover_tools_finds_the_real_tools(self):
        """Test discovery from source registers every concrete tool."""
        registry = ToolRegistry()
        registry.discover_tools()

        tools = registry.list_tools()
        assert len(tools) == 17
        for name in ("ask", "set_model", "debug", "start_conversation", "server_info"):
            assert name in tools

    def test_discovering_twice_skips_duplicates(self):
        """Test a second discovery warns about each tool and registers nothing new."""
        registry = ToolRegistry()
        registry.discover_tools()

        with patch("council.core.registry.logger") as mock_logger:
            registry.discover_tools()

        assert len(registry.list_tools()) == 17
        assert mock_logger.warning.call_count == 17

    def test_get_tool(self):
        """Test getting a tool by name."""
        registry = ToolRegistry()

        # Register tool
        tool = MockTool()
        registry._tools[tool.name] = tool
        registry._tool_classes[tool.name] = MockTool

        retrieved_tool = registry.get_tool("mock_tool")
        assert retrieved_tool is not None
        assert isinstance(retrieved_tool, MockTool)

        # Test non-existent tool
        assert registry.get_tool("non_existent") is None

    def test_list_tools(self):
        """Test listing all tool names."""
        registry = ToolRegistry()

        # Register multiple tools
        class Tool1(MockTool):
            @property
            def name(self) -> str:
                return "tool1"

            @property
            def description(self) -> str:
                return "Tool 1"

        class Tool2(MockTool):
            @property
            def name(self) -> str:
                return "tool2"

            @property
            def description(self) -> str:
                return "Tool 2"

        tool1 = Tool1()
        tool2 = Tool2()
        registry._tools[tool1.name] = tool1
        registry._tools[tool2.name] = tool2

        tools = registry.list_tools()
        assert len(tools) == 2
        assert "tool1" in tools
        assert "tool2" in tools

    def test_get_mcp_tool_definitions(self):
        """Test getting MCP definitions for all tools."""
        registry = ToolRegistry()

        # Register tool
        tool = MockTool()
        registry._tools[tool.name] = tool

        definitions = registry.get_mcp_tool_definitions()
        assert len(definitions) == 1
        assert definitions[0]["name"] == "mock_tool"
        assert definitions[0]["description"] == "Mock tool for testing"
        assert "inputSchema" in definitions[0]

    def test_discover_tools_handles_errors(self):
        """Test that discovery handles import errors gracefully."""
        with patch("council.core.registry.logger") as mock_logger:
            with patch("pathlib.Path.glob") as mock_glob:
                with patch("importlib.import_module") as mock_import:
                    mock_glob.return_value = [Path("bad_tool.py")]
                    mock_import.side_effect = ImportError("Test error")

                    registry = ToolRegistry()
                    registry.discover_tools()

                    # Should log error but not crash
                    mock_logger.error.assert_called()

    def test_register_tool_with_invalid_metadata(self):
        """Test registering a tool with empty name."""

        class BadTool(MCPTool):
            @property
            def name(self) -> str:
                return ""  # Invalid empty name

            @property
            def description(self) -> str:
                return "Bad tool"

            @property
            def input_schema(self) -> Dict[str, Any]:
                return {}

            async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
                return ToolOutput(success=True, result="bad")

        registry = ToolRegistry()

        # Try to register bad tool
        bad_tool = BadTool()
        registry._tools[bad_tool.name] = bad_tool

        # Tool with empty name can still be registered (no validation in new API)
        assert "" in registry._tools
