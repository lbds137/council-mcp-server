"""Unit tests for the tool registry."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

from gemini_mcp.core.registry import ToolRegistry
from gemini_mcp.tools.base import BaseTool
from gemini_mcp.models.base import ToolMetadata


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(name="mock_tool", description="Mock tool for testing")
    
    async def _execute(self, input_data):
        return "mock result"
    
    def _get_input_schema(self):
        return {"type": "object", "properties": {}}


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
        registry._register_tool_class(MockTool)
        
        assert "mock_tool" in registry._tools
        assert "mock_tool" in registry._tool_classes
        assert isinstance(registry._tools["mock_tool"], MockTool)
        assert registry._tool_classes["mock_tool"] == MockTool
    
    def test_register_duplicate_tool(self):
        """Test that duplicate tools are not registered."""
        registry = ToolRegistry()
        
        # Register once
        registry._register_tool_class(MockTool)
        
        # Try to register again with a mock logger to check warning
        with patch('gemini_mcp.core.registry.logger') as mock_logger:
            registry._register_tool_class(MockTool)
            mock_logger.warning.assert_called_once()
    
    def test_get_tool(self):
        """Test getting a tool by name."""
        registry = ToolRegistry()
        registry._register_tool_class(MockTool)
        
        tool = registry.get_tool("mock_tool")
        assert tool is not None
        assert isinstance(tool, MockTool)
        
        # Test non-existent tool
        assert registry.get_tool("non_existent") is None
    
    def test_list_tools(self):
        """Test listing all tool names."""
        registry = ToolRegistry()
        
        # Register multiple tools
        class Tool1(MockTool):
            def _get_metadata(self):
                return ToolMetadata(name="tool1", description="Tool 1")
        
        class Tool2(MockTool):
            def _get_metadata(self):
                return ToolMetadata(name="tool2", description="Tool 2")
        
        registry._register_tool_class(Tool1)
        registry._register_tool_class(Tool2)
        
        tools = registry.list_tools()
        assert len(tools) == 2
        assert "tool1" in tools
        assert "tool2" in tools
    
    def test_get_mcp_tool_definitions(self):
        """Test getting MCP definitions for all tools."""
        registry = ToolRegistry()
        registry._register_tool_class(MockTool)
        
        definitions = registry.get_mcp_tool_definitions()
        assert len(definitions) == 1
        assert definitions[0]["name"] == "mock_tool"
        assert definitions[0]["description"] == "Mock tool for testing"
        assert "inputSchema" in definitions[0]
    
    @patch('importlib.import_module')
    @patch('pathlib.Path.glob')
    def test_discover_tools(self, mock_glob, mock_import):
        """Test tool discovery from directory."""
        # Setup mocks
        mock_glob.return_value = [Path("test_tool.py")]
        
        # Create a mock module with a tool class
        mock_module = MagicMock()
        mock_module.TestTool = MockTool
        mock_import.return_value = mock_module
        
        registry = ToolRegistry()
        registry.discover_tools()
        
        # Verify import was called
        mock_import.assert_called_once_with("gemini_mcp.tools.test_tool")
        
        # Verify tool was registered
        assert "mock_tool" in registry._tools
    
    def test_discover_tools_handles_errors(self):
        """Test that discovery handles import errors gracefully."""
        with patch('gemini_mcp.core.registry.logger') as mock_logger:
            with patch('pathlib.Path.glob') as mock_glob:
                with patch('importlib.import_module') as mock_import:
                    mock_glob.return_value = [Path("bad_tool.py")]
                    mock_import.side_effect = ImportError("Test error")
                    
                    registry = ToolRegistry()
                    registry.discover_tools()
                    
                    # Should log error but not crash
                    mock_logger.error.assert_called()
    
    def test_register_tool_with_invalid_metadata(self):
        """Test registering a tool that fails validation."""
        
        class BadTool(BaseTool):
            def _get_metadata(self):
                return ToolMetadata(name="", description="Bad tool")
            
            async def _execute(self, input_data):
                return "bad"
            
            def _get_input_schema(self):
                return {}
        
        registry = ToolRegistry()
        
        with patch('gemini_mcp.core.registry.logger') as mock_logger:
            registry._register_tool_class(BadTool)
            mock_logger.error.assert_called()
            
        # Tool should not be registered
        assert "" not in registry._tools