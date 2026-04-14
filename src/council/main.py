"""
Main MCP server implementation that orchestrates all modular components.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from os import PathLike
from typing import IO, Any, Dict, Optional, Union

from .core.orchestrator import ConversationOrchestrator
from .core.registry import ToolRegistry
from .json_rpc import JsonRpcServer, create_result_response
from .manager import ModelManager
from .services.cache import ResponseCache
from .services.memory import ConversationMemory

# Protocol versions this server implements. The first entry is the default
# returned when the client requests an unknown version (spec-compliant fallback).
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05",)

# Try to import dotenv if available
try:
    from dotenv import load_dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

    def load_dotenv(
        dotenv_path: Optional[Union[str, PathLike[str]]] = None,
        stream: Optional[IO[str]] = None,
        verbose: bool = False,
        override: bool = False,
        interpolate: bool = True,
        encoding: Optional[str] = None,
    ) -> bool:
        """Dummy function when dotenv is not available."""
        return False


logger = logging.getLogger(__name__)

__version__ = "4.0.0"


def _tool_error(request_id: Any, message: str) -> Dict[str, Any]:
    """Build a tools/call result that signals a tool-level failure.

    MCP spec: a tool failure is conveyed inside ``result`` with ``isError: true``
    and the error text as content. It is NOT a JSON-RPC error — those are
    reserved for protocol-level failures.
    """
    return create_result_response(
        request_id,
        {"content": [{"type": "text", "text": f"Error: {message}"}], "isError": True},
    )


class CouncilMCPServer:
    """Main MCP Server that integrates all modular components."""

    def __init__(self):
        """Initialize the server with modular components."""
        # Load environment variables at startup
        self._load_env_file()

        self.model_manager: Optional[ModelManager] = None
        self.tool_registry = ToolRegistry()
        self.cache = ResponseCache(max_size=100, ttl_seconds=3600)
        self.memory = ConversationMemory(max_turns=50, max_entries=100)
        self.orchestrator: Optional[ConversationOrchestrator] = None

        # Create JSON-RPC server
        self.server = JsonRpcServer("council-mcp-server")
        self._setup_handlers()

        # Make server instance available globally for tools
        import council

        setattr(council, "_server_instance", self)

        # Also set as global for bundled mode
        globals()["_server_instance"] = self

    def _load_env_file(self) -> None:
        """Load .env file from multiple possible locations."""
        # Try multiple locations for .env file
        # 1. Directory of the main entry point (works with launcher.py)
        main_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        # 2. Parent directory of main (in case we're in a subdirectory)
        parent_dir = os.path.dirname(main_dir)
        # 3. Current working directory
        cwd = os.getcwd()
        # 4. Script directory (where this file is)
        script_dir = os.path.dirname(os.path.abspath(__file__))

        env_locations = [
            os.path.join(main_dir, ".env"),
            os.path.join(parent_dir, ".env"),
            os.path.join(cwd, ".env"),
            os.path.join(script_dir, ".env"),
        ]

        # If python-dotenv is available, try to use it first
        if HAS_DOTENV:
            env_loaded = False
            for env_path in env_locations:
                if os.path.exists(env_path):
                    logger.info(f"Loading .env from {env_path}")
                    load_dotenv(env_path)
                    env_loaded = True
                    break

            if not env_loaded:
                # Try current directory as last fallback
                logger.info("No .env file found in expected locations, trying current directory")
                load_dotenv()
        else:
            # Manual .env loading if python-dotenv is not available
            for env_path in env_locations:
                if os.path.exists(env_path):
                    logger.info(f"Loading .env from {env_path} (manual mode)")
                    try:
                        with open(env_path, "r") as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#") and "=" in line:
                                    key, value = line.split("=", 1)
                                    # Strip whitespace from key and value
                                    key = key.strip()
                                    value = value.strip()
                                    # Remove quotes if present
                                    if (value.startswith('"') and value.endswith('"')) or (
                                        value.startswith("'") and value.endswith("'")
                                    ):
                                        value = value[1:-1]
                                    os.environ[key] = value
                                    if key == "OPENROUTER_API_KEY":
                                        logger.info(
                                            f"Set OPENROUTER_API_KEY from .env file "
                                            f"(length: {len(value)})"
                                        )
                        break
                    except Exception as e:
                        logger.error(f"Failed to load .env file: {e}")

    def _initialize_model_manager(self) -> bool:
        """Initialize the model manager with API key."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("No OPENROUTER_API_KEY found in environment. Please check your .env file.")
            # Log all env vars starting with OPENROUTER or COUNCIL for debugging
            relevant_vars = {
                k: v
                for k, v in os.environ.items()
                if k.startswith("OPENROUTER") or k.startswith("COUNCIL")
            }
            if relevant_vars:
                logger.info(f"Found relevant env vars: {list(relevant_vars.keys())}")
            else:
                logger.warning("No OPENROUTER or COUNCIL environment variables found at all")
            return False

        try:
            logger.info(f"Initializing ModelManager with API key (length: {len(api_key)})")
            self.model_manager = ModelManager(api_key)

            # Create orchestrator with all components
            logger.info("Creating conversation orchestrator...")
            self.orchestrator = ConversationOrchestrator(
                tool_registry=self.tool_registry,
                model_manager=self.model_manager,
                memory=self.memory,
                cache=self.cache,
            )

            logger.info("Model manager initialization complete")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize model manager: {e}", exc_info=True)
            return False

    def _setup_handlers(self):
        """Set up JSON-RPC handlers."""
        self.server.register_handler("initialize", self.handle_initialize)
        self.server.register_handler("tools/list", self.handle_tools_list)
        self.server.register_handler("tools/call", self.handle_tool_call)
        self.server.register_handler("ping", self.handle_ping)

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialization request."""
        self._load_env_file()

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            logger.info(f"OPENROUTER_API_KEY found (length: {len(api_key)})")
        else:
            logger.warning("OPENROUTER_API_KEY not found in environment")

        self.tool_registry.discover_tools()
        logger.info(f"Registered {len(self.tool_registry.list_tools())} tools")

        model_initialized = self._initialize_model_manager()
        if not model_initialized:
            logger.warning("Model manager not initialized; tool calls will return errors")

        # Negotiate protocol version: echo the client's version if we support
        # it, otherwise fall back to our latest supported version.
        client_version = params.get("protocolVersion", "")
        if client_version in SUPPORTED_PROTOCOL_VERSIONS:
            protocol_version = client_version
        else:
            protocol_version = SUPPORTED_PROTOCOL_VERSIONS[0]
            if client_version:
                logger.info(
                    f"Client requested protocolVersion={client_version!r}; "
                    f"responding with supported version {protocol_version!r}"
                )

        return create_result_response(
            request_id,
            {
                "protocolVersion": protocol_version,
                "serverInfo": {
                    "name": "council-mcp-server",
                    "version": __version__,
                },
                "capabilities": {"tools": {}},
            },
        )

    def handle_ping(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle liveness ping (MCP spec: empty-object result)."""
        return create_result_response(request_id, {})

    def handle_tools_list(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool list request."""
        # Get tool definitions from registry
        tool_defs = self.tool_registry.get_mcp_tool_definitions()

        # Convert to tool list format
        tools = []
        for tool_def in tool_defs:
            tools.append(
                {
                    "name": tool_def["name"],
                    "description": tool_def["description"],
                    "inputSchema": tool_def["inputSchema"],
                }
            )

        return create_result_response(request_id, {"tools": tools})

    def handle_tool_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution request.

        Returns a result with ``isError: true`` on any failure, per MCP spec.
        Without that flag, clients treat failed tool runs as successful.
        """
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        logger.info(f"Executing tool: {tool_name}")

        if not tool_name:
            return _tool_error(request_id, "Tool name is required")

        if not self.orchestrator:
            return _tool_error(
                request_id,
                "Models not initialized. Please set OPENROUTER_API_KEY environment variable.",
            )

        import asyncio

        # Always create a fresh event loop for the sync bridge. Relying on
        # asyncio.get_event_loop() is unsafe on Python 3.12+ where it may
        # raise DeprecationWarning or return an unrelated loop.
        loop = asyncio.new_event_loop()
        try:
            output = loop.run_until_complete(
                self.orchestrator.execute_tool(
                    tool_name=tool_name, parameters=arguments, request_id=request_id
                )
            )
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return _tool_error(request_id, f"Error executing tool: {e}")
        finally:
            loop.close()

        if output.success:
            return create_result_response(
                request_id,
                {"content": [{"type": "text", "text": output.result or ""}], "isError": False},
            )
        return _tool_error(request_id, output.error or "Unknown error")

    def run(self):
        """Run the MCP server."""
        logger.info(f"Starting Council MCP Server v{__version__} (Modular)")

        # Configure unbuffered output for proper MCP communication
        sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 1)
        sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 1)

        # Run the JSON-RPC server
        self.server.run()


# Keep GeminiMCPServer as alias for backwards compatibility
GeminiMCPServer = CouncilMCPServer


def main():
    """Main entry point."""
    # Create logs directory if it doesn't exist
    log_dir = os.path.expanduser("~/.claude-mcp-servers/council/logs")
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging with both stderr and file output
    log_file = os.path.join(log_dir, "council-mcp-server.log")

    # Create handlers
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        RotatingFileHandler(
            log_file,
            mode="a",
            encoding="utf-8",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,  # Keep 5 backup files
        ),
    ]

    # Configure logging
    # Use DEBUG level if COUNCIL_DEBUG env var is set, otherwise INFO
    log_level = logging.DEBUG if os.getenv("COUNCIL_DEBUG") else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,  # Ensure logging is configured even if already configured elsewhere
    )

    logger.info(f"Logging to file: {log_file}")

    try:
        server = CouncilMCPServer()
        server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
