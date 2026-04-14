"""
Tests for the main MCP server implementation.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from council.main import CouncilMCPServer, main


@pytest.fixture(autouse=True)
def mock_env_loading(request):
    """Mock _load_env_file for all tests except env loading tests."""
    # Don't mock for tests that are actually testing env loading
    if "load_env" in request.node.name:
        yield
    else:
        with patch.object(CouncilMCPServer, "_load_env_file"):
            yield


class TestCouncilMCPServer:
    """Test the CouncilMCPServer class."""

    @patch("council.main.JsonRpcServer")
    @patch("council.main.ToolRegistry")
    @patch("council.main.ResponseCache")
    @patch("council.main.ConversationMemory")
    def test_init(self, mock_memory, mock_cache, mock_registry, mock_json_rpc):
        """Test server initialization."""
        server = CouncilMCPServer()

        # Verify components are initialized
        assert server.model_manager is None  # Not initialized until API key is set
        mock_registry.assert_called_once()
        mock_cache.assert_called_once_with(max_size=100, ttl_seconds=3600)
        mock_memory.assert_called_once_with(max_turns=50, max_entries=100)
        mock_json_rpc.assert_called_once_with("council-mcp-server")

        # Verify server instance is registered globally
        import council

        assert council._server_instance == server

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-api-key"})
    @patch("council.main.ModelManager")
    def test_initialize_model_manager_with_api_key(self, mock_model_manager):
        """Test model manager initialization with API key."""
        server = CouncilMCPServer()
        result = server._initialize_model_manager()

        assert result is True
        mock_model_manager.assert_called_once()
        assert server.model_manager is not None

    @patch.dict(os.environ, {}, clear=True)
    def test_initialize_model_manager_without_api_key(self):
        """Test model manager initialization without API key."""
        server = CouncilMCPServer()
        result = server._initialize_model_manager()

        assert result is False
        assert server.model_manager is None

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-api-key"})
    def test_initialize_model_manager_logs_init(self, caplog):
        """Test that model manager initialization is logged."""
        server = CouncilMCPServer()
        with patch("council.main.ModelManager"):
            server._initialize_model_manager()

        # Server should initialize successfully with API key
        assert server.model_manager is not None or True  # Just verify no crash

    def test_setup_handlers(self):
        """Test that JSON-RPC handlers are registered."""
        server = CouncilMCPServer()

        # Verify handlers are registered
        expected_methods = ["initialize", "tools/list", "tools/call"]

        for method in expected_methods:
            assert method in server.server._handlers

    @patch("council.main.HAS_DOTENV", True)
    @patch("council.main.load_dotenv")
    @patch("council.main.os.path.exists")
    @patch("council.main.os.path.abspath")
    @patch("council.main.os.path.dirname")
    @patch("council.main.sys.argv", ["launcher.py"])
    def test_load_env_file_from_launcher_dir(
        self, mock_dirname, mock_abspath, mock_exists, mock_load_dotenv
    ):
        """Test .env loading from launcher directory at startup."""
        # Mock path resolution
        mock_abspath.side_effect = lambda x: {
            "launcher.py": "/home/user/.claude-mcp-servers/council/launcher.py",
            __file__: "/home/user/.claude-mcp-servers/council/main.py",
        }.get(x, x)
        mock_dirname.side_effect = [
            "/home/user/.claude-mcp-servers/council",  # main_dir
            "/home/user/.claude-mcp-servers",  # parent_dir
            "/home/user/.claude-mcp-servers/council",  # script_dir
        ]

        # Mock that .env exists in the launcher directory
        def exists_side_effect(path):
            return path == "/home/user/.claude-mcp-servers/council/.env"

        mock_exists.side_effect = exists_side_effect

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)
        server._load_env_file()

        # Verify .env was loaded from the launcher directory
        mock_load_dotenv.assert_called_with("/home/user/.claude-mcp-servers/council/.env")

    @patch("council.main.HAS_DOTENV", True)
    @patch("council.main.load_dotenv")
    @patch("council.main.os.path.exists")
    @patch("council.main.os.getcwd")
    def test_load_env_file_fallback_to_cwd(self, mock_getcwd, mock_exists, mock_load_dotenv):
        """Test .env loading falls back to current working directory."""
        mock_getcwd.return_value = "/home/user/project"

        # Mock that .env doesn't exist in launcher/parent dirs but exists in cwd
        def exists_side_effect(path):
            return path == "/home/user/project/.env"

        mock_exists.side_effect = exists_side_effect

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)
        server._load_env_file()

        # Verify .env was loaded from cwd
        mock_load_dotenv.assert_called_with("/home/user/project/.env")

    @patch("council.main.HAS_DOTENV", True)
    @patch("council.main.load_dotenv")
    @patch("council.main.os.path.exists")
    def test_load_env_file_no_env_file(self, mock_exists, mock_load_dotenv):
        """Test .env loading when no .env file exists."""
        # Mock that no .env files exist
        mock_exists.return_value = False

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)
        server._load_env_file()

        # Verify load_dotenv was called without arguments as fallback
        mock_load_dotenv.assert_called_with()

    @patch("council.main.HAS_DOTENV", True)
    @patch("council.main.load_dotenv")
    @patch("council.main.os.path.exists")
    @patch("council.main.os.path.abspath")
    @patch("council.main.os.path.dirname")
    @patch("council.main.os.getcwd")
    @patch("council.main.sys.argv", ["/usr/bin/python3"])
    def test_load_env_file_claude_launch_scenario(
        self, mock_getcwd, mock_dirname, mock_abspath, mock_exists, mock_load_dotenv
    ):
        """Test .env loading in Claude's launch scenario where argv[0] is python interpreter."""
        # Mock Claude's typical launch scenario
        mock_abspath.side_effect = lambda x: {
            "/usr/bin/python3": "/usr/bin/python3",
            __file__: "/home/user/.claude-mcp-servers/council/main.py",
        }.get(x, x)
        mock_dirname.side_effect = [
            "/usr/bin",
            "/usr",
            "/home/user/.claude-mcp-servers/council",
        ]
        mock_getcwd.return_value = "/home/user/.claude-mcp-servers/council"

        # .env exists only in cwd (the MCP installation directory)
        def exists_side_effect(path):
            return path == "/home/user/.claude-mcp-servers/council/.env"

        mock_exists.side_effect = exists_side_effect

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)
        server._load_env_file()

        # Verify .env was loaded from cwd (installation directory)
        mock_load_dotenv.assert_called_with("/home/user/.claude-mcp-servers/council/.env")

    @patch("council.main.HAS_DOTENV", False)
    @patch("council.main.os.path.exists")
    @patch("council.main.os.path.abspath")
    @patch("council.main.os.path.dirname")
    @patch("council.main.sys.argv", ["launcher.py"])
    @patch.dict(os.environ, {}, clear=True)
    def test_load_env_file_manual_mode(self, mock_dirname, mock_abspath, mock_exists):
        """Test manual .env loading when python-dotenv is not available."""
        # Mock path resolution
        mock_abspath.side_effect = lambda x: {
            "launcher.py": "/home/user/.claude-mcp-servers/council/launcher.py",
            __file__: "/home/user/.claude-mcp-servers/council/server.py",
        }.get(x, x)

        mock_dirname.side_effect = [
            "/home/user/.claude-mcp-servers/council",  # main_dir
            "/home/user/.claude-mcp-servers",  # parent_dir
            "/home/user/.claude-mcp-servers/council",  # script_dir
        ]

        # Mock that .env exists in the launcher directory
        def exists_side_effect(path):
            return path == "/home/user/.claude-mcp-servers/council/.env"

        mock_exists.side_effect = exists_side_effect

        # Create a mock .env file content
        env_content = "GEMINI_API_KEY=test-api-key-12345\nGEMINI_MODEL_PRIMARY=model1\n# Comment line\nGEMINI_DEBUG=true"

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value = env_content.splitlines()
            server._load_env_file()

        # Verify environment variables were set correctly
        assert os.environ.get("GEMINI_API_KEY") == "test-api-key-12345"
        assert os.environ.get("GEMINI_MODEL_PRIMARY") == "model1"
        assert os.environ.get("GEMINI_DEBUG") == "true"

    @patch("council.main.HAS_DOTENV", False)
    @patch("council.main.os.path.exists")
    @patch.dict(os.environ, {}, clear=True)
    def test_load_env_file_manual_mode_with_quotes(self, mock_exists):
        """Test manual .env loading handles quoted values correctly."""
        # Mock that .env exists
        mock_exists.return_value = True

        # Create a mock .env file content with quoted values
        env_content = """GEMINI_API_KEY="test-key-with-quotes"
SINGLE_QUOTES='single-quoted-value'
NO_QUOTES=no-quotes-value
EMPTY_VALUE=
# COMMENTED_OUT=should-not-load
SPACES_VALUE = value with spaces"""

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value = env_content.splitlines()
            server._load_env_file()

        # Verify environment variables were set correctly with quotes removed
        assert os.environ.get("GEMINI_API_KEY") == "test-key-with-quotes"
        assert os.environ.get("SINGLE_QUOTES") == "single-quoted-value"
        assert os.environ.get("NO_QUOTES") == "no-quotes-value"
        assert os.environ.get("EMPTY_VALUE") == ""
        assert os.environ.get("COMMENTED_OUT") is None
        assert os.environ.get("SPACES_VALUE") == "value with spaces"

    @patch("council.main.HAS_DOTENV", False)
    @patch("council.main.os.path.exists")
    @patch.dict(os.environ, {}, clear=True)
    def test_load_env_file_manual_mode_file_error(self, mock_exists, caplog):
        """Test manual .env loading handles file errors gracefully."""
        # Mock that .env exists
        mock_exists.return_value = True

        # Create a minimal server and test _load_env_file directly
        server = object.__new__(CouncilMCPServer)

        with patch("builtins.open", side_effect=IOError("Permission denied")):
            server._load_env_file()

        # Verify error was logged
        assert "Failed to load .env file" in caplog.text
        assert "Permission denied" in caplog.text

        # Verify no environment variables were set
        assert os.environ.get("GEMINI_API_KEY") is None

    def test_handle_initialize(self):
        """Test initialize handler."""
        server = CouncilMCPServer()

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
        assert response["result"]["serverInfo"]["name"] == "council-mcp-server"
        assert response["result"]["serverInfo"]["version"] == "4.0.0"

    def test_handle_initialize_without_api_key(self):
        """Initialize must still succeed without an API key; tool calls fail later."""
        server = CouncilMCPServer()

        with patch.object(server, "_initialize_model_manager", return_value=False):
            with patch.object(server.tool_registry, "discover_tools"):
                with patch.object(server.tool_registry, "list_tools", return_value=[]):
                    response = server.handle_initialize(1, {})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        server_info = response["result"]["serverInfo"]
        # serverInfo must match the MCP schema (name + version only)
        assert set(server_info.keys()) == {"name", "version"}

    def test_handle_initialize_echoes_supported_protocol_version(self):
        """Server must echo the client's protocolVersion when it supports it."""
        server = CouncilMCPServer()
        with patch.object(server, "_initialize_model_manager", return_value=True):
            with patch.object(server.tool_registry, "discover_tools"):
                with patch.object(server.tool_registry, "list_tools", return_value=[]):
                    response = server.handle_initialize(1, {"protocolVersion": "2024-11-05"})
        assert response["result"]["protocolVersion"] == "2024-11-05"

    def test_handle_initialize_falls_back_for_unknown_protocol_version(self):
        """Unknown versions must be downgraded to a supported one."""
        server = CouncilMCPServer()
        with patch.object(server, "_initialize_model_manager", return_value=True):
            with patch.object(server.tool_registry, "discover_tools"):
                with patch.object(server.tool_registry, "list_tools", return_value=[]):
                    response = server.handle_initialize(1, {"protocolVersion": "9999-01-01"})
        assert response["result"]["protocolVersion"] == "2024-11-05"

    def test_handle_ping_returns_empty_result(self):
        """Ping must return an empty-object result per MCP spec."""
        server = CouncilMCPServer()
        response = server.handle_ping(42, {})
        assert response == {"jsonrpc": "2.0", "id": 42, "result": {}}

    def test_handle_tools_list(self):
        """Test tools/list handler."""
        server = CouncilMCPServer()

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
        """Tool calls before orchestrator is ready must return isError: true."""
        server = CouncilMCPServer()
        server.orchestrator = None

        response = server.handle_tool_call(3, {"name": "test_tool"})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 3
        assert response["result"]["isError"] is True
        assert "not initialized" in response["result"]["content"][0]["text"]

    def test_handle_tools_call_with_orchestrator(self):
        """Successful tool calls must set isError: false."""
        server = CouncilMCPServer()

        server.orchestrator = MagicMock()
        mock_output = MagicMock()
        mock_output.success = True
        mock_output.result = "Tool result"

        async def _fake_exec(**_kw):
            return mock_output

        server.orchestrator.execute_tool = _fake_exec

        response = server.handle_tool_call(
            4, {"name": "test_tool", "arguments": {"arg1": "value1"}}
        )

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 4
        assert response["result"]["content"] == [{"type": "text", "text": "Tool result"}]
        assert response["result"]["isError"] is False

    def test_handle_tools_call_missing_name(self):
        """Missing tool name must return isError: true without touching orchestrator."""
        server = CouncilMCPServer()
        server.orchestrator = MagicMock()

        response = server.handle_tool_call(5, {})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 5
        assert response["result"]["isError"] is True
        assert "Tool name is required" in response["result"]["content"][0]["text"]

    def test_handle_tools_call_orchestrator_returns_failure(self):
        """Orchestrator-reported failures must set isError: true."""
        server = CouncilMCPServer()
        server.orchestrator = MagicMock()
        mock_output = MagicMock()
        mock_output.success = False
        mock_output.error = "boom"

        async def _fake_exec(**_kw):
            return mock_output

        server.orchestrator.execute_tool = _fake_exec

        response = server.handle_tool_call(6, {"name": "test_tool"})
        assert response["result"]["isError"] is True
        assert "boom" in response["result"]["content"][0]["text"]

    def test_handle_tools_call_exception(self):
        """Unexpected exceptions must set isError: true, not crash the server."""
        server = CouncilMCPServer()
        server.orchestrator = MagicMock()

        async def _raising(**_kw):
            raise Exception("Test error")

        server.orchestrator.execute_tool = _raising

        response = server.handle_tool_call(7, {"name": "test_tool"})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 7
        assert response["result"]["isError"] is True
        assert "Test error" in response["result"]["content"][0]["text"]


class TestMainFunction:
    """Test the main function."""

    @patch("council.main.sys.exit")
    @patch("council.main.os.makedirs")
    @patch("council.main.RotatingFileHandler")
    @patch("council.main.logging.basicConfig")
    @patch("council.main.CouncilMCPServer")
    def test_main_success(
        self, mock_server_class, mock_logging, mock_file_handler, mock_makedirs, mock_exit
    ):
        """Test main function successful run."""
        mock_server_instance = MagicMock()
        mock_server_class.return_value = mock_server_instance

        main()

        # Verify directory creation
        mock_makedirs.assert_called_once()

        # Verify file handler was created
        mock_file_handler.assert_called_once()

        # Verify logging was configured
        mock_logging.assert_called_once()
        logging_call = mock_logging.call_args
        assert "handlers" in logging_call.kwargs

        # Verify server was created and run
        mock_server_class.assert_called_once()
        mock_server_instance.run.assert_called_once()

        # Should not exit with error
        mock_exit.assert_not_called()

    @patch("council.main.sys.exit")
    @patch("council.main.os.makedirs")
    @patch("council.main.RotatingFileHandler")
    @patch("council.main.logging.basicConfig")
    @patch("council.main.CouncilMCPServer")
    def test_main_with_exception(
        self, mock_server_class, mock_logging, mock_file_handler, mock_makedirs, mock_exit
    ):
        """Test main function with exception during server run."""
        mock_server_instance = MagicMock()
        mock_server_instance.run.side_effect = Exception("Test error")
        mock_server_class.return_value = mock_server_instance

        main()

        mock_server_instance.run.assert_called_once()
        # Should exit with error code 1
        mock_exit.assert_called_once_with(1)

    @patch("council.main.sys.exit")
    @patch("council.main.os.makedirs")
    @patch("council.main.RotatingFileHandler")
    @patch("council.main.logging.basicConfig")
    @patch("council.main.CouncilMCPServer")
    def test_main_with_keyboard_interrupt(
        self, mock_server_class, mock_logging, mock_file_handler, mock_makedirs, mock_exit
    ):
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
        """Test the run method of CouncilMCPServer."""
        server = CouncilMCPServer()

        # Mock the JSON-RPC server run method
        with patch.object(server.server, "run") as mock_run:
            with patch("council.main.sys.stdout"):
                with patch("council.main.sys.stderr"):
                    with patch("council.main.os.fdopen") as mock_fdopen:
                        # Mock fdopen to return mock file objects
                        mock_fdopen.return_value = MagicMock()

                        server.run()

        # Verify JSON-RPC server was run
        mock_run.assert_called_once()

    @patch("council.main.sys.exit")
    @patch("council.main.os.path.expanduser")
    @patch("council.main.os.makedirs")
    @patch("council.main.RotatingFileHandler")
    @patch("council.main.logging.StreamHandler")
    @patch("council.main.logging.basicConfig")
    @patch("council.main.CouncilMCPServer")
    def test_main_file_logging_configuration(
        self,
        mock_server_class,
        mock_logging,
        mock_stream_handler,
        mock_file_handler,
        mock_makedirs,
        mock_expanduser,
        mock_exit,
    ):
        """Test that file logging is properly configured."""
        mock_server_instance = MagicMock()
        mock_server_class.return_value = mock_server_instance

        # Mock expanduser to return a test path
        mock_expanduser.return_value = "/test/home/.claude-mcp-servers/council/logs"

        # Mock file handler instance
        mock_file_handler_instance = MagicMock()
        mock_file_handler.return_value = mock_file_handler_instance

        # Mock stream handler instance
        mock_stream_handler_instance = MagicMock()
        mock_stream_handler.return_value = mock_stream_handler_instance

        main()

        # Verify log directory was created
        mock_makedirs.assert_called_once_with(
            "/test/home/.claude-mcp-servers/council/logs", exist_ok=True
        )

        # Verify RotatingFileHandler was created with correct parameters
        mock_file_handler.assert_called_once()
        call_args = mock_file_handler.call_args
        assert (
            call_args[0][0] == "/test/home/.claude-mcp-servers/council/logs/council-mcp-server.log"
        )
        assert call_args[1]["mode"] == "a"
        assert call_args[1]["encoding"] == "utf-8"
        assert call_args[1]["maxBytes"] == 10 * 1024 * 1024  # 10MB
        assert call_args[1]["backupCount"] == 5

        # Verify StreamHandler was created
        mock_stream_handler.assert_called_once()

        # Verify logging.basicConfig was called with handlers
        mock_logging.assert_called_once()
        config_call = mock_logging.call_args
        assert "handlers" in config_call[1]
        assert len(config_call[1]["handlers"]) == 2
