"""
Standalone JSON-RPC 2.0 implementation for MCP servers.
Based on Gemini's recommendations for replacing the mcp library.
"""

import json
import logging
import sys
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# JSON-RPC 2.0 constants
JSONRPC_VERSION = "2.0"
ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603


class JsonRpcRequest:
    """JSON-RPC 2.0 Request"""

    def __init__(self, data: dict):
        self.jsonrpc = data.get("jsonrpc", JSONRPC_VERSION)
        self.method = data.get("method")
        self.params = data.get("params", {})
        self.id = data.get("id")

        # Validate
        if self.jsonrpc != JSONRPC_VERSION:
            raise ValueError(f"Invalid JSON-RPC version: {self.jsonrpc}")
        if not self.method:
            raise ValueError("Missing method")


class JsonRpcResponse:
    """JSON-RPC 2.0 Response"""

    def __init__(self, result: Any = None, error: Optional[Dict[str, Any]] = None, id: Any = None):
        self.jsonrpc = JSONRPC_VERSION
        self.id = id
        if error is not None:
            self.error = error
        else:
            self.result = result

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "id": self.id}
        if hasattr(self, "error"):
            d["error"] = self.error
        else:
            d["result"] = self.result if hasattr(self, "result") else None
        return d


class JsonRpcError:
    """JSON-RPC 2.0 Error"""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


class JsonRpcServer:
    """
    A synchronous JSON-RPC 2.0 server over stdio.
    Compatible with MCP protocol expectations.
    """

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._handlers: Dict[str, Callable] = {}
        self._running = False

    def register_handler(self, method: str, handler: Callable):
        """Register a handler for a JSON-RPC method."""
        logger.info(f"Registering handler for method: {method}")
        self._handlers[method] = handler

    def _read_message(self) -> Optional[str]:
        """Read a single line from stdin."""
        try:
            line = sys.stdin.readline()
            if not line:
                return None
            return line.strip()
        except Exception as e:
            logger.error(f"Error reading from stdin: {e}")
            return None

    def _write_message(self, message: dict):
        """Write a JSON message to stdout."""
        try:
            print(json.dumps(message), flush=True)
        except Exception as e:
            logger.error(f"Error writing to stdout: {e}")

    def _process_request(self, request_str: str) -> Optional[dict]:
        """Process a single JSON-RPC request."""
        request_id = None

        try:
            # Parse JSON
            try:
                request_data = json.loads(request_str)
            except json.JSONDecodeError as e:
                return JsonRpcResponse(
                    error=JsonRpcError(ERROR_PARSE, f"Parse error: {e}").to_dict()
                ).to_dict()

            # Parse request
            try:
                request = JsonRpcRequest(request_data)
                request_id = request.id
            except ValueError as e:
                return JsonRpcResponse(
                    error=JsonRpcError(ERROR_INVALID_REQUEST, str(e)).to_dict(), id=request_id
                ).to_dict()

            # Find handler
            handler = self._handlers.get(request.method) if request.method else None
            if not handler:
                return JsonRpcResponse(
                    error=JsonRpcError(
                        ERROR_METHOD_NOT_FOUND, f"Method not found: {request.method}"
                    ).to_dict(),
                    id=request_id,
                ).to_dict()

            # Execute handler
            try:
                result = handler(request_id, request.params)
                # Handler returns a complete response dict
                return result
            except Exception as e:
                logger.error(f"Handler error for {request.method}: {e}", exc_info=True)
                return JsonRpcResponse(
                    error=JsonRpcError(ERROR_INTERNAL, f"Internal error: {str(e)}").to_dict(),
                    id=request_id,
                ).to_dict()

        except Exception as e:
            logger.error(f"Unexpected error processing request: {e}", exc_info=True)
            return JsonRpcResponse(
                error=JsonRpcError(ERROR_INTERNAL, f"Internal error: {str(e)}").to_dict(),
                id=request_id,
            ).to_dict()

    def run(self):
        """Run the JSON-RPC server (synchronous)."""
        logger.info(f"Starting JSON-RPC server '{self.server_name}'...")
        self._running = True

        while self._running:
            try:
                # Read a line
                line = self._read_message()
                if line is None:
                    logger.info("EOF reached, shutting down")
                    break

                if not line:
                    continue

                # Process the request
                response = self._process_request(line)

                # Send response if any
                if response:
                    self._write_message(response)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt, shutting down")
                break
            except Exception as e:
                logger.error(f"Server error: {e}", exc_info=True)
                continue

        logger.info("Server stopped")

    def stop(self):
        """Stop the server."""
        self._running = False


# MCP-compatible type definitions (simple dicts instead of Pydantic)
def create_text_content(text: str) -> dict:
    """Create a text content object."""
    return {"type": "text", "text": text}


def create_tool(name: str, description: str, input_schema: dict) -> dict:
    """Create a tool definition."""
    return {"name": name, "description": description, "inputSchema": input_schema}


def create_error_response(request_id: Any, code: int, message: str) -> dict:
    """Create an error response."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def create_result_response(request_id: Any, result: Any) -> dict:
    """Create a result response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}
