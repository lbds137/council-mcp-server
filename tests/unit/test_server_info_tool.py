"""Tests for the server info tool."""

import json
from unittest.mock import Mock, patch

import pytest

from council.tools.server_info import ServerInfoTool


def extract_json_from_result(result_str: str) -> dict:
    """Extract and parse JSON from server_info result.

    The result format is:
    Council MCP Server v4.0.0

    {JSON}

    ## Quick Guide...

    This function extracts just the JSON portion.
    """
    # Split by double newline and get the JSON block
    parts = result_str.split("\n\n")
    for part in parts:
        part = part.strip()
        if part.startswith("{") and "}" in part:
            # Find the end of the JSON object
            brace_count = 0
            end_idx = 0
            for i, char in enumerate(part):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            json_str = part[:end_idx]
            return json.loads(json_str)
    raise ValueError("No JSON found in result")


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
        # Mock council module without server instance
        mock_council = Mock()
        mock_council._server_instance = None

        with patch.dict("sys.modules", {"council": mock_council}):
            result = await tool.execute({})

        assert result.success is True
        assert "Council MCP Server v4.0.0" in result.result

        # Parse JSON from result
        info = extract_json_from_result(result.result)

        assert info["version"] == "4.0.0"
        assert info["architecture"] == "modular"
        assert info["backend"] == "OpenRouter"
        assert info["status"] == "running"
        assert "Full stats unavailable" in info["note"]

        # Verify quick guide is included
        assert "## Quick Model Selection Guide" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_full_server_instance(self, tool):
        """Test execute with full server instance available."""
        # Create mock server components
        mock_tool_registry = Mock()
        mock_tool_registry.list_tools.return_value = [
            "ask",
            "brainstorm",
            "server_info",
        ]

        mock_cache = Mock()
        mock_cache.get_stats.return_value = {"size": 5, "max_size": 100, "hits": 10, "misses": 2}

        mock_memory = Mock()
        mock_memory.get_stats.return_value = {"turns_count": 3, "entries_count": 5}

        mock_model_manager = Mock()
        mock_model_manager.default_model = "google/gemini-3-pro-preview"
        mock_model_manager.active_model = "google/gemini-3-pro-preview"
        mock_model_manager.model_cache = None  # Prevent Mock from being serialized
        mock_model_manager.get_stats.return_value = {
            "provider": "openrouter",
            "active_model": "google/gemini-3-pro-preview",
            "default_model": "google/gemini-3-pro-preview",
            "total_calls": 25,
            "successful_calls": 23,
            "failed_calls": 2,
            "success_rate": "92.0%",
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

        # Mock council module
        mock_council = Mock()
        mock_council._server_instance = mock_server

        with patch.dict("sys.modules", {"council": mock_council}):
            result = await tool.execute({})

        assert result.success is True
        assert "Council MCP Server v4.0.0" in result.result

        # Parse JSON from result
        info = extract_json_from_result(result.result)

        assert info["version"] == "4.0.0"
        assert info["architecture"] == "modular"
        assert info["backend"] == "OpenRouter"
        assert "ask" in info["available_tools"]
        assert info["components"]["tools_registered"] == 3
        assert info["models"]["initialized"] is True
        assert info["models"]["default_model"] == "google/gemini-3-pro-preview"
        assert info["models"]["active_model"] == "google/gemini-3-pro-preview"
        assert info["models"]["stats"]["total_calls"] == 25
        assert info["execution_stats"]["total_executions"] == 15

        # Verify quick guide is included
        assert "## Quick Model Selection Guide" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_partial_server_instance(self, tool):
        """Test execute with server instance but no orchestrator."""
        # Create mock server with minimal components
        mock_tool_registry = Mock()
        mock_tool_registry.list_tools.return_value = ["ask"]

        mock_server = Mock()
        mock_server.tool_registry = mock_tool_registry
        mock_server.cache = None
        mock_server.memory = None
        mock_server.model_manager = None
        mock_server.orchestrator = None

        # Mock council module
        mock_council = Mock()
        mock_council._server_instance = mock_server

        with patch.dict("sys.modules", {"council": mock_council}):
            result = await tool.execute({})

        assert result.success is True

        # Parse JSON from result
        info = extract_json_from_result(result.result)

        assert info["models"]["initialized"] is False
        assert "execution_stats" not in info

        # Verify quick guide is included
        assert "## Quick Model Selection Guide" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_model_stats_exception(self, tool):
        """Test execute handles model stats exception gracefully."""
        # Create mock server with model_manager that raises exception
        mock_model_manager = Mock()
        mock_model_manager.default_model = "google/gemini-3-pro-preview"
        mock_model_manager.active_model = "google/gemini-3-pro-preview"
        mock_model_manager.model_cache = None  # Prevent Mock from being serialized
        mock_model_manager.get_stats.side_effect = Exception("Stats error")

        mock_server = Mock()
        mock_server.tool_registry = Mock()
        mock_server.tool_registry.list_tools.return_value = ["ask"]
        mock_server.model_manager = mock_model_manager
        mock_server.cache = None
        mock_server.memory = None
        mock_server.orchestrator = None

        # Mock council module
        mock_council = Mock()
        mock_council._server_instance = mock_server

        with patch.dict("sys.modules", {"council": mock_council}):
            result = await tool.execute({})

        # Should still succeed but stats should not be present
        assert result.success is True
        info = extract_json_from_result(result.result)
        assert info["models"]["initialized"] is True
        # Stats key may not be present if exception occurred
        assert "stats" not in info["models"] or info["models"]["stats"] is None

        # Verify quick guide is included
        assert "## Quick Model Selection Guide" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_exception(self, tool):
        """Test execute handles exceptions gracefully."""
        # Create a server that will cause an error
        mock_server = Mock()
        mock_server.tool_registry.list_tools.side_effect = Exception("Registry error")

        mock_council = Mock()
        mock_council._server_instance = mock_server

        with patch.dict("sys.modules", {"council": mock_council}):
            result = await tool.execute({})

        assert result.success is False
        assert "Error getting server info" in result.error

    def test_get_mcp_definition(self, tool):
        """Test get_mcp_definition returns correct format."""
        definition = tool.get_mcp_definition()

        assert definition["name"] == "server_info"
        assert definition["description"] == "Get server version and status"
        assert definition["inputSchema"]["type"] == "object"
        assert definition["inputSchema"]["properties"] == {}
