"""
Tests for the main MCP server implementation.
"""

import os
from unittest.mock import MagicMock, patch

from gemini_mcp.main import GeminiMCPServer, main


class TestGeminiMCPServer:
    """Test the GeminiMCPServer class."""

    @patch("gemini_mcp.main.JsonRpcServer")
    @patch("gemini_mcp.main.ToolRegistry")
    @patch("gemini_mcp.main.ResponseCache")
    @patch("gemini_mcp.main.ConversationMemory")
    def test_init(self, mock_memory, mock_cache, mock_registry, mock_json_rpc):
        """Test server initialization."""
        server = GeminiMCPServer()

        # Verify components are initialized
        assert server.model_manager is None  # Not initialized until API key is set
        mock_registry.assert_called_once()
        mock_cache.assert_called_once_with(max_size=100, ttl_seconds=3600)
        mock_memory.assert_called_once_with(max_turns=50, max_entries=100)
        mock_json_rpc.assert_called_once_with("gemini-mcp-server")

        # Verify server instance is registered globally
        import gemini_mcp

        assert gemini_mcp._server_instance == server

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"})
    @patch("gemini_mcp.main.DualModelManager")
    def test_initialize_model_manager_with_api_key(self, mock_model_manager):
        """Test model manager initialization with API key."""
        server = GeminiMCPServer()
        result = server._initialize_model_manager()

        assert result is True
        mock_model_manager.assert_called_once()
        assert server.model_manager is not None

    @patch.dict(os.environ, {}, clear=True)
    def test_initialize_model_manager_without_api_key(self):
        """Test model manager initialization without API key."""
        server = GeminiMCPServer()
        result = server._initialize_model_manager()

        assert result is False
        assert server.model_manager is None

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key", "GEMINI_EXTRA": "value"})
    def test_initialize_model_manager_logs_gemini_vars(self, caplog):
        """Test that GEMINI env vars are logged."""
        server = GeminiMCPServer()
        with patch("gemini_mcp.main.DualModelManager"):
            server._initialize_model_manager()

        # Should not log env vars when API key is present
        assert "Found GEMINI env vars" not in caplog.text

    def test_setup_handlers(self):
        """Test that JSON-RPC handlers are registered."""
        server = GeminiMCPServer()

        # Verify handlers are registered
        expected_methods = ["initialize", "tools/list", "tools/call"]

        for method in expected_methods:
            assert method in server.server._handlers

    def test_handle_initialize(self):
        """Test initialize handler."""
        server = GeminiMCPServer()

        # Mock the model manager initialization
        with patch.object(server, "_initialize_model_manager", return_value=True):
            # Mock tool registry
            with patch.object(server.tool_registry, "discover_tools"):
                with patch.object(
                    server.tool_registry, "list_tools", return_value=["tool1", "tool2"]
                ):
                    response = server.handle_initialize(1, {})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["protocolVersion"] == "2024-11-05"
        assert response["result"]["serverInfo"]["name"] == "gemini-mcp-server"
        assert response["result"]["serverInfo"]["version"] == "3.0.0"

    def test_handle_initialize_without_api_key(self):
        """Test initialize handler without API key."""
        server = GeminiMCPServer()

        with patch.object(server, "_initialize_model_manager", return_value=False):
            with patch.object(server.tool_registry, "discover_tools"):
                with patch.object(server.tool_registry, "list_tools", return_value=[]):
                    response = server.handle_initialize(1, {})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        # When API key is missing, modelsAvailable should be False
        assert response["result"]["serverInfo"]["modelsAvailable"] is False

    def test_handle_tools_list(self):
        """Test tools/list handler."""
        server = GeminiMCPServer()

        # Mock tool definitions
        mock_tools = [
            {"name": "tool1", "description": "Test tool 1", "inputSchema": {}},
            {"name": "tool2", "description": "Test tool 2", "inputSchema": {}},
        ]
        with patch.object(
            server.tool_registry, "get_mcp_tool_definitions", return_value=mock_tools
        ):
            response = server.handle_tools_list(2, {})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        assert response["result"]["tools"] == mock_tools

    def test_handle_tools_call_without_orchestrator(self):
        """Test tools/call handler without orchestrator."""
        server = GeminiMCPServer()
        server.orchestrator = None  # Ensure no orchestrator

        response = server.handle_tool_call(3, {"name": "test_tool"})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 3
        assert "result" in response
        assert "not initialized" in response["result"]["content"][0]["text"]

    @patch("asyncio.get_event_loop")
    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    @patch("asyncio.get_running_loop")
    def test_handle_tools_call_with_orchestrator(
        self, mock_get_running, mock_new_loop, mock_set_loop, mock_get_loop
    ):
        """Test tools/call handler with orchestrator."""
        server = GeminiMCPServer()

        # Mock orchestrator and its async execute_tool method
        server.orchestrator = MagicMock()
        mock_output = MagicMock()
        mock_output.success = True
        mock_output.result = "Tool result"

        # Mock the event loop and async execution
        mock_loop = MagicMock()
        mock_get_running.side_effect = RuntimeError()
        mock_new_loop.return_value = mock_loop
        mock_get_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = mock_output

        params = {"name": "test_tool", "arguments": {"arg1": "value1"}}
        response = server.handle_tool_call(4, params)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 4
        assert response["result"]["content"] == [{"type": "text", "text": "Tool result"}]

        # Verify async execution was called
        mock_loop.run_until_complete.assert_called_once()

    @patch("asyncio.get_event_loop")
    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    @patch("asyncio.get_running_loop")
    def test_handle_tools_call_missing_name(
        self, mock_get_running, mock_new_loop, mock_set_loop, mock_get_loop
    ):
        """Test tools/call handler with missing tool name."""
        server = GeminiMCPServer()
        server.orchestrator = MagicMock()

        # Mock async execution to return error for None tool
        mock_output = MagicMock()
        mock_output.success = False
        mock_output.error = "Tool 'None' not found"

        mock_loop = MagicMock()
        mock_get_running.side_effect = RuntimeError()
        mock_new_loop.return_value = mock_loop
        mock_get_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = mock_output

        response = server.handle_tool_call(5, {})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 5
        assert "Tool name is required" in response["result"]["content"][0]["text"]

    @patch("asyncio.get_event_loop")
    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    @patch("asyncio.get_running_loop")
    def test_handle_tools_call_exception(
        self, mock_get_running, mock_new_loop, mock_set_loop, mock_get_loop
    ):
        """Test tools/call handler with exception."""
        server = GeminiMCPServer()
        server.orchestrator = MagicMock()

        # Mock async execution to raise exception
        mock_loop = MagicMock()
        mock_get_running.side_effect = RuntimeError()
        mock_new_loop.return_value = mock_loop
        mock_get_loop.return_value = mock_loop
        mock_loop.run_until_complete.side_effect = Exception("Test error")

        params = {"name": "test_tool"}
        response = server.handle_tool_call(6, params)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 6
        assert "Test error" in response["result"]["content"][0]["text"]

    # Remove tests for handlers that don't exist in the current implementation


class TestMainFunction:
    """Test the main function."""

    @patch("gemini_mcp.main.sys.exit")
    @patch("gemini_mcp.main.logging.basicConfig")
    @patch("gemini_mcp.main.GeminiMCPServer")
    def test_main_success(self, mock_server_class, mock_logging, mock_exit):
        """Test main function successful run."""
        mock_server_instance = MagicMock()
        mock_server_class.return_value = mock_server_instance

        main()

        # Verify logging was configured
        mock_logging.assert_called_once()

        # Verify server was created and run
        mock_server_class.assert_called_once()
        mock_server_instance.run.assert_called_once()

        # Should not exit with error
        mock_exit.assert_not_called()

    @patch("gemini_mcp.main.sys.exit")
    @patch("gemini_mcp.main.logging.basicConfig")
    @patch("gemini_mcp.main.GeminiMCPServer")
    def test_main_with_exception(self, mock_server_class, mock_logging, mock_exit):
        """Test main function with exception during server run."""
        mock_server_instance = MagicMock()
        mock_server_instance.run.side_effect = Exception("Test error")
        mock_server_class.return_value = mock_server_instance

        main()

        mock_server_instance.run.assert_called_once()
        # Should exit with error code 1
        mock_exit.assert_called_once_with(1)

    @patch("gemini_mcp.main.sys.exit")
    @patch("gemini_mcp.main.logging.basicConfig")
    @patch("gemini_mcp.main.GeminiMCPServer")
    def test_main_with_keyboard_interrupt(self, mock_server_class, mock_logging, mock_exit):
        """Test main function with keyboard interrupt."""
        mock_server_instance = MagicMock()
        mock_server_instance.run.side_effect = KeyboardInterrupt()
        mock_server_class.return_value = mock_server_instance

        # Should not raise exception
        main()

        mock_server_instance.run.assert_called_once()
        # Should not exit with error for keyboard interrupt
        mock_exit.assert_not_called()

    def test_run_method(self):
        """Test the run method of GeminiMCPServer."""
        server = GeminiMCPServer()

        # Mock the JSON-RPC server run method
        with patch.object(server.server, "run") as mock_run:
            with patch("gemini_mcp.main.sys.stdout"):
                with patch("gemini_mcp.main.sys.stderr"):
                    with patch("gemini_mcp.main.os.fdopen") as mock_fdopen:
                        # Mock fdopen to return mock file objects
                        mock_fdopen.return_value = MagicMock()

                        server.run()

        # Verify JSON-RPC server was run
        mock_run.assert_called_once()
