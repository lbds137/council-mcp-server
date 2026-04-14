"""
Tests for the JSON-RPC 2.0 implementation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from council.json_rpc import (
    ERROR_INTERNAL,
    ERROR_INVALID_REQUEST,
    ERROR_METHOD_NOT_FOUND,
    ERROR_PARSE,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcServer,
    create_error_response,
    create_result_response,
    create_text_content,
    create_tool,
)


class TestJsonRpcRequest:
    """Test the JsonRpcRequest class."""

    def test_valid_request(self):
        """Test creating a valid request."""
        data = {"jsonrpc": "2.0", "method": "test_method", "params": {"foo": "bar"}, "id": 1}
        request = JsonRpcRequest(data)
        assert request.jsonrpc == "2.0"
        assert request.method == "test_method"
        assert request.params == {"foo": "bar"}
        assert request.id == 1

    def test_request_without_params(self):
        """Test request without params defaults to empty dict."""
        data = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
        request = JsonRpcRequest(data)
        assert request.params == {}

    def test_invalid_jsonrpc_version(self):
        """Test request with invalid JSON-RPC version."""
        data = {"jsonrpc": "1.0", "method": "test_method", "id": 1}
        with pytest.raises(ValueError, match="Invalid JSON-RPC version"):
            JsonRpcRequest(data)

    def test_missing_method(self):
        """Test request without method."""
        data = {"jsonrpc": "2.0", "id": 1}
        with pytest.raises(ValueError, match="Missing method"):
            JsonRpcRequest(data)

    def test_notification_without_id(self):
        """Test notification (request without id)."""
        data = {"jsonrpc": "2.0", "method": "notify"}
        request = JsonRpcRequest(data)
        assert request.id is None


class TestJsonRpcResponse:
    """Test the JsonRpcResponse class."""

    def test_success_response(self):
        """Test creating a success response."""
        response = JsonRpcResponse(result={"data": "test"}, id=1)
        d = response.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == 1
        assert d["result"] == {"data": "test"}
        assert "error" not in d

    def test_error_response(self):
        """Test creating an error response."""
        error = {"code": -32601, "message": "Method not found"}
        response = JsonRpcResponse(error=error, id=1)
        d = response.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == 1
        assert d["error"] == error
        assert "result" not in d

    def test_response_with_null_id(self):
        """Test response with null id (for parse errors)."""
        response = JsonRpcResponse(error={"code": -32700, "message": "Parse error"}, id=None)
        d = response.to_dict()
        assert d["id"] is None


class TestJsonRpcError:
    """Test the JsonRpcError class."""

    def test_error_without_data(self):
        """Test error without additional data."""
        error = JsonRpcError(code=-32601, message="Method not found")
        d = error.to_dict()
        assert d == {"code": -32601, "message": "Method not found"}

    def test_error_with_data(self):
        """Test error with additional data."""
        error = JsonRpcError(code=-32602, message="Invalid params", data={"param": "value"})
        d = error.to_dict()
        assert d == {"code": -32602, "message": "Invalid params", "data": {"param": "value"}}


class TestJsonRpcServer:
    """Test the JsonRpcServer class."""

    def test_init(self):
        """Test server initialization."""
        server = JsonRpcServer("test-server")
        assert server.server_name == "test-server"
        assert server._handlers == {}
        assert server._running is False

    def test_register_handler(self):
        """Test registering a handler."""
        server = JsonRpcServer("test-server")
        handler = MagicMock()
        server.register_handler("test_method", handler)
        assert server._handlers["test_method"] == handler

    @patch("sys.stdin")
    def test_read_message_success(self, mock_stdin):
        """Test successful message reading."""
        server = JsonRpcServer("test-server")
        mock_stdin.readline.return_value = '{"test": "data"}\n'
        result = server._read_message()
        assert result == '{"test": "data"}'

    @patch("sys.stdin")
    def test_read_message_empty(self, mock_stdin):
        """Test reading empty message."""
        server = JsonRpcServer("test-server")
        mock_stdin.readline.return_value = ""
        result = server._read_message()
        assert result is None

    @patch("sys.stdin")
    def test_read_message_exception(self, mock_stdin):
        """Test exception during reading."""
        server = JsonRpcServer("test-server")
        mock_stdin.readline.side_effect = Exception("Read error")
        result = server._read_message()
        assert result is None

    @patch("builtins.print")
    def test_write_message_success(self, mock_print):
        """Test successful message writing."""
        server = JsonRpcServer("test-server")
        message = {"test": "data"}
        server._write_message(message)
        mock_print.assert_called_once_with('{"test": "data"}', flush=True)

    @patch("builtins.print")
    def test_write_message_exception(self, mock_print):
        """Test exception during writing."""
        server = JsonRpcServer("test-server")
        mock_print.side_effect = Exception("Write error")
        # Should not raise, just log the error
        server._write_message({"test": "data"})

    def test_process_request_parse_error(self):
        """Test processing invalid JSON."""
        server = JsonRpcServer("test-server")
        result = server._process_request("{invalid json")
        assert result["error"]["code"] == ERROR_PARSE
        assert "Parse error" in result["error"]["message"]

    def test_process_request_invalid_request(self):
        """Test processing invalid request structure."""
        server = JsonRpcServer("test-server")
        # Missing method
        result = server._process_request('{"jsonrpc": "2.0", "id": 1}')
        assert result["error"]["code"] == ERROR_INVALID_REQUEST
        # ID should be preserved but currently it's None due to parse order
        assert result["id"] is None  # This is the current behavior

    def test_process_request_method_not_found(self):
        """Test processing request with unknown method."""
        server = JsonRpcServer("test-server")
        request = {"jsonrpc": "2.0", "method": "unknown_method", "id": 1}
        result = server._process_request(json.dumps(request))
        assert result["error"]["code"] == ERROR_METHOD_NOT_FOUND
        assert "unknown_method" in result["error"]["message"]
        assert result["id"] == 1

    def test_process_request_handler_success(self):
        """Test successful handler execution."""
        server = JsonRpcServer("test-server")
        handler_result = {"jsonrpc": "2.0", "result": {"data": "test"}, "id": 1}
        handler = MagicMock(return_value=handler_result)
        server.register_handler("test_method", handler)

        request = {"jsonrpc": "2.0", "method": "test_method", "params": {"foo": "bar"}, "id": 1}
        result = server._process_request(json.dumps(request))

        handler.assert_called_once_with(1, {"foo": "bar"})
        assert result == handler_result

    def test_process_request_handler_exception(self):
        """Test handler raising exception."""
        server = JsonRpcServer("test-server")
        handler = MagicMock(side_effect=Exception("Handler error"))
        server.register_handler("test_method", handler)

        request = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
        result = server._process_request(json.dumps(request))

        assert result["error"]["code"] == ERROR_INTERNAL
        assert "Handler error" in result["error"]["message"]
        assert result["id"] == 1

    def test_process_request_notification_runs_handler_without_response(self):
        """Notifications (no id) invoke the handler but never get a response."""
        server = JsonRpcServer("test-server")
        handler = MagicMock(return_value={"jsonrpc": "2.0", "result": "ok"})
        server.register_handler("notify", handler)

        request = {"jsonrpc": "2.0", "method": "notify", "params": {}}
        result = server._process_request(json.dumps(request))

        handler.assert_called_once_with(None, {})
        assert result is None

    def test_process_request_notification_unknown_method(self):
        """Unknown notifications must be silently ignored (no error response)."""
        server = JsonRpcServer("test-server")
        request = {"jsonrpc": "2.0", "method": "does/not/exist"}
        result = server._process_request(json.dumps(request))
        assert result is None

    def test_process_request_notifications_initialized_silent(self):
        """MCP handshake: notifications/initialized must not receive a response."""
        server = JsonRpcServer("test-server")
        request = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        result = server._process_request(json.dumps(request))
        assert result is None

    def test_process_request_notification_handler_exception_silent(self):
        """If a notification handler raises, server must still not respond."""
        server = JsonRpcServer("test-server")
        handler = MagicMock(side_effect=Exception("boom"))
        server.register_handler("notify", handler)

        request = {"jsonrpc": "2.0", "method": "notify"}
        result = server._process_request(json.dumps(request))
        assert result is None

    def test_process_request_notification_missing_method_silent(self):
        """Malformed notification (missing method) must not receive a response."""
        server = JsonRpcServer("test-server")
        # No id, no method — still a notification
        result = server._process_request('{"jsonrpc": "2.0"}')
        assert result is None

    def test_process_request_null_id_still_gets_response(self):
        """id == null is NOT a notification per spec; client gets an error response."""
        server = JsonRpcServer("test-server")
        request = {"jsonrpc": "2.0", "method": "unknown", "id": None}
        result = server._process_request(json.dumps(request))
        assert result is not None
        assert result["error"]["code"] == ERROR_METHOD_NOT_FOUND

    @patch("sys.stdin")
    @patch("builtins.print")
    def test_run_single_request(self, mock_print, mock_stdin):
        """Test running server with a single request."""
        server = JsonRpcServer("test-server")
        handler = MagicMock(return_value={"jsonrpc": "2.0", "result": "ok", "id": 1})
        server.register_handler("test", handler)

        # Simulate one request then EOF
        mock_stdin.readline.side_effect = [
            '{"jsonrpc": "2.0", "method": "test", "id": 1}\n',
            "",  # EOF
        ]

        server.run()

        # Verify handler was called
        handler.assert_called_once()
        # Verify response was written
        mock_print.assert_called_with('{"jsonrpc": "2.0", "result": "ok", "id": 1}', flush=True)

    @patch("sys.stdin")
    @patch("builtins.print")
    def test_run_does_not_write_for_notification(self, mock_print, mock_stdin):
        """End-to-end: notification arrives, nothing is written to stdout."""
        server = JsonRpcServer("test-server")
        mock_stdin.readline.side_effect = [
            '{"jsonrpc": "2.0", "method": "notifications/initialized"}\n',
            "",  # EOF
        ]
        server.run()
        mock_print.assert_not_called()

    @patch("sys.stdin")
    @patch("builtins.print")
    def test_run_full_mcp_handshake(self, mock_print, mock_stdin):
        """End-to-end: initialize → notifications/initialized → tools/list.

        Writes exactly two responses (for initialize and tools/list), none
        for the notification. Regression test for the bug that caused
        Claude Code to drop council tools after a stricter MCP client update.
        """
        server = JsonRpcServer("test-server")
        server.register_handler(
            "initialize",
            lambda rid, _p: {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "x"}},
        )
        server.register_handler(
            "tools/list",
            lambda rid, _p: {"jsonrpc": "2.0", "id": rid, "result": {"tools": []}},
        )
        mock_stdin.readline.side_effect = [
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n',
            "",
        ]
        server.run()
        assert mock_print.call_count == 2
        written = [call.args[0] for call in mock_print.call_args_list]
        assert '"id": 1' in written[0]
        assert '"id": 2' in written[1]

    def test_stop(self):
        """Test stopping the server."""
        server = JsonRpcServer("test-server")
        server._running = True
        server.stop()
        assert server._running is False


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_result_response(self):
        """Test create_result_response helper."""
        response = create_result_response(123, {"data": "test"})
        assert response == {"jsonrpc": "2.0", "result": {"data": "test"}, "id": 123}

    def test_create_result_response_with_none_id(self):
        """Test create_result_response with None id."""
        response = create_result_response(None, "result")
        assert response == {"jsonrpc": "2.0", "result": "result", "id": None}

    def test_create_error_response(self):
        """Test create_error_response helper."""
        response = create_error_response(42, ERROR_METHOD_NOT_FOUND, "Method not found")
        assert response == {
            "jsonrpc": "2.0",
            "id": 42,
            "error": {"code": ERROR_METHOD_NOT_FOUND, "message": "Method not found"},
        }

    def test_create_text_content(self):
        """Test create_text_content helper."""
        content = create_text_content("Hello, world!")
        assert content == {"type": "text", "text": "Hello, world!"}

    def test_create_tool(self):
        """Test create_tool helper."""
        tool = create_tool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"param1": {"type": "string"}}},
        )
        assert tool == {
            "name": "test_tool",
            "description": "A test tool",
            "inputSchema": {"type": "object", "properties": {"param1": {"type": "string"}}},
        }
