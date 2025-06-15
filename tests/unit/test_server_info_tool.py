"""Tests for the server info tool."""

import json
from unittest.mock import Mock, patch

import pytest

from gemini_mcp.tools.server_info import ServerInfoTool


class TestServerInfoTool:
    """Test cases for ServerInfoTool."""

    @pytest.fixture
    def tool(self):
        """Create a ServerInfoTool instance."""
        return ServerInfoTool()

    def test_name(self, tool):
        """Test tool name property."""
        assert tool.name == "server_info"

    def test_description(self, tool):
        """Test tool description property."""
        assert tool.description == "Get server version and status"

    def test_input_schema(self, tool):
        """Test tool input schema property."""
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert schema["required"] == []

    @pytest.mark.asyncio
    async def test_execute_without_server_instance(self, tool):
        """Test execute when server instance is not available."""
        # Mock gemini_mcp module without server instance
        mock_gemini_mcp = Mock()
        mock_gemini_mcp._server_instance = None

        with patch.dict("sys.modules", {"gemini_mcp": mock_gemini_mcp}):
            result = await tool.execute({})

        assert result.success is True
        assert "🤖 Gemini MCP Server v3.0.0" in result.result

        # Parse JSON from result
        json_str = result.result.split("\n\n", 1)[1]
        info = json.loads(json_str)

        assert info["version"] == "3.0.0"
        assert info["architecture"] == "modular"
        assert info["status"] == "running"
        assert "Full stats unavailable" in info["note"]

    @pytest.mark.asyncio
    async def test_execute_with_full_server_instance(self, tool):
        """Test execute with full server instance available."""
        # Create mock server components
        mock_tool_registry = Mock()
        mock_tool_registry.list_tools.return_value = [
            "ask_gemini",
            "gemini_brainstorm",
            "server_info",
        ]

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {"size": 5, "max_size": 100, "hits": 10, "misses": 2}

        mock_memory = Mock()
        mock_memory.get_stats.return_value = {"turns_count": 3, "entries_count": 5}

        mock_model_manager = Mock()
        mock_model_manager.primary_model_name = "gemini-2.0-flash-exp"
        mock_model_manager.fallback_model_name = "gemini-1.5-pro"
        mock_model_manager.get_stats.return_value = {
            "primary_model": "gemini-2.0-flash-exp",
            "fallback_model": "gemini-1.5-pro",
            "total_calls": 25,
            "primary_calls": 20,
            "fallback_calls": 5,
            "primary_failures": 2,
            "primary_success_rate": 0.9,
            "timeout_seconds": 600.0,
        }

        mock_orchestrator = Mock()
        mock_orchestrator.get_execution_stats.return_value = {
            "total_executions": 15,
            "successful": 14,
            "failed": 1,
        }

        # Create mock server instance
        mock_server = Mock()
        mock_server.tool_registry = mock_tool_registry
        mock_server.cache = mock_cache
        mock_server.memory = mock_memory
        mock_server.model_manager = mock_model_manager
        mock_server.orchestrator = mock_orchestrator

        # Mock gemini_mcp module
        mock_gemini_mcp = Mock()
        mock_gemini_mcp._server_instance = mock_server

        with patch.dict("sys.modules", {"gemini_mcp": mock_gemini_mcp}):
            result = await tool.execute({})

        assert result.success is True
        assert "🤖 Gemini MCP Server v3.0.0" in result.result

        # Parse JSON from result
        json_str = result.result.split("\n\n", 1)[1]
        info = json.loads(json_str)

        assert info["version"] == "3.0.0"
        assert info["architecture"] == "modular"
        assert "ask_gemini" in info["available_tools"]
        assert info["components"]["tools_registered"] == 3
        assert info["models"]["initialized"] is True
        assert info["models"]["primary"] == "gemini-2.0-flash-exp"
        assert info["models"]["stats"]["total_calls"] == 25
        assert info["models"]["stats"]["primary_calls"] == 20
        assert info["models"]["stats"]["fallback_calls"] == 5
        assert info["models"]["stats"]["primary_failures"] == 2
        assert info["models"]["stats"]["primary_success_rate"] == 0.9
        assert info["models"]["stats"]["timeout_seconds"] == 600.0
        assert info["execution_stats"]["total_executions"] == 15

    @pytest.mark.asyncio
    async def test_execute_with_partial_server_instance(self, tool):
        """Test execute with server instance but no orchestrator."""
        # Create mock server with minimal components
        mock_tool_registry = Mock()
        mock_tool_registry.list_tools.return_value = ["ask_gemini"]

        mock_server = Mock()
        mock_server.tool_registry = mock_tool_registry
        mock_server.cache = None
        mock_server.memory = None
        mock_server.model_manager = None
        mock_server.orchestrator = None

        # Mock gemini_mcp module
        mock_gemini_mcp = Mock()
        mock_gemini_mcp._server_instance = mock_server

        with patch.dict("sys.modules", {"gemini_mcp": mock_gemini_mcp}):
            result = await tool.execute({})

        assert result.success is True

        # Parse JSON from result
        json_str = result.result.split("\n\n", 1)[1]
        info = json.loads(json_str)

        assert info["models"]["initialized"] is False
        assert info["models"]["stats"] is None
        assert "execution_stats" not in info

    @pytest.mark.asyncio
    async def test_execute_with_model_stats_exception(self, tool):
        """Test execute handles model stats exception gracefully."""
        # Create mock server with model_manager that raises exception
        mock_model_manager = Mock()
        mock_model_manager.primary_model_name = "gemini-2.0-flash-exp"
        mock_model_manager.fallback_model_name = "gemini-1.5-pro"
        mock_model_manager.get_stats.side_effect = Exception("Stats error")

        mock_server = Mock()
        mock_server.tool_registry = Mock()
        mock_server.tool_registry.list_tools.return_value = ["ask_gemini"]
        mock_server.model_manager = mock_model_manager
        mock_server.cache = None
        mock_server.memory = None
        mock_server.orchestrator = None

        # Mock gemini_mcp module
        mock_gemini_mcp = Mock()
        mock_gemini_mcp._server_instance = mock_server

        with patch.dict("sys.modules", {"gemini_mcp": mock_gemini_mcp}):
            result = await tool.execute({})

        # Should still succeed but stats should be None
        assert result.success is True
        json_str = result.result.split("\n\n", 1)[1]
        info = json.loads(json_str)
        assert info["models"]["initialized"] is True
        assert info["models"]["stats"] is None

    @pytest.mark.asyncio
    async def test_execute_with_exception(self, tool):
        """Test execute handles exceptions gracefully."""
        # Mock gemini_mcp to raise an exception
        with patch(
            "src.gemini_mcp.tools.server_info.json.dumps", side_effect=Exception("JSON error")
        ):
            result = await tool.execute({})

        assert result.success is False
        assert "Error getting server info" in result.error
        assert "JSON error" in result.error

    def test_get_mcp_definition(self, tool):
        """Test get_mcp_definition returns correct format."""
        definition = tool.get_mcp_definition()

        assert definition["name"] == "server_info"
        assert definition["description"] == "Get server version and status"
        assert definition["inputSchema"]["type"] == "object"
        assert definition["inputSchema"]["properties"] == {}
