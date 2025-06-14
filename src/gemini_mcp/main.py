"""
Main MCP server implementation that orchestrates all modular components.
"""

import logging
import os
import sys
from os import PathLike
from typing import IO, Any, Dict, Optional, Union

from .core.orchestrator import ConversationOrchestrator
from .core.registry import ToolRegistry
from .json_rpc import JsonRpcServer, create_result_response
from .models.manager import DualModelManager
from .services.cache import ResponseCache
from .services.memory import ConversationMemory

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

__version__ = "3.0.0"


class GeminiMCPServer:
    """Main MCP Server that integrates all modular components."""

    def __init__(self):
        """Initialize the server with modular components."""
        self.model_manager: Optional[DualModelManager] = None
        self.tool_registry = ToolRegistry()
        self.cache = ResponseCache(max_size=100, ttl_seconds=3600)
        self.memory = ConversationMemory(max_turns=50, max_entries=100)
        self.orchestrator: Optional[ConversationOrchestrator] = None

        # Create JSON-RPC server
        self.server = JsonRpcServer("gemini-mcp-server")
        self._setup_handlers()

        # Make server instance available globally for tools
        import gemini_mcp

        setattr(gemini_mcp, "_server_instance", self)

        # Also set as global for bundled mode
        globals()["_server_instance"] = self

    def _initialize_model_manager(self) -> bool:
        """Initialize the model manager with API key."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("No GEMINI_API_KEY found in environment. Please check your .env file.")
            # Log all env vars starting with GEMINI for debugging
            gemini_vars = {k: v for k, v in os.environ.items() if k.startswith("GEMINI")}
            if gemini_vars:
                logger.info(f"Found GEMINI env vars: {list(gemini_vars.keys())}")
            else:
                logger.warning("No GEMINI environment variables found at all")
            return False

        try:
            logger.info(f"Initializing DualModelManager with API key (length: {len(api_key)})")
            self.model_manager = DualModelManager(api_key)

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
        # Register handlers
        self.server.register_handler("initialize", self.handle_initialize)
        self.server.register_handler("tools/list", self.handle_tools_list)
        self.server.register_handler("tools/call", self.handle_tool_call)

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialization request."""
        # Load environment variables
        if HAS_DOTENV:
            # Try MCP directory first
            mcp_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            env_path = os.path.join(mcp_dir, ".env")

            if os.path.exists(env_path):
                logger.info(f"Loading .env from {env_path}")
                load_dotenv(env_path)
            else:
                # Try current directory as fallback
                load_dotenv()

        # Log the API key status
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            logger.info(f"GEMINI_API_KEY found (length: {len(api_key)})")
        else:
            logger.warning("GEMINI_API_KEY not found in environment")

        # Discover and register all tools FIRST
        self.tool_registry.discover_tools()
        logger.info(f"Registered {len(self.tool_registry.list_tools())} tools")

        # Initialize model manager AFTER tools are registered
        model_initialized = self._initialize_model_manager()

        return create_result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "gemini-mcp-server",
                    "version": __version__,
                    "modelsAvailable": model_initialized,
                },
                "capabilities": {"tools": {}},
            },
        )

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
        """Handle tool execution request."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        logger.info(f"Executing tool: {tool_name}")

        # Validate tool name
        if not tool_name:
            return create_result_response(
                request_id,
                {"content": [{"type": "text", "text": "❌ Error: Tool name is required"}]},
            )

        # Check if models are initialized
        if not self.orchestrator:
            result = (
                "❌ Gemini models not initialized. "
                "Please set GEMINI_API_KEY environment variable."
            )
            return create_result_response(
                request_id, {"content": [{"type": "text", "text": result}]}
            )

        # Execute tool through orchestrator
        try:
            # Use orchestrator to execute tool (async converted to sync)
            import asyncio

            # Create event loop if needed
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            try:
                output = loop.run_until_complete(
                    self.orchestrator.execute_tool(
                        tool_name=tool_name, parameters=arguments, request_id=request_id
                    )
                )

                if output.success:
                    result = output.result or ""
                else:
                    result = f"❌ Error: {output.error or 'Unknown error'}"

            finally:
                # Clean up loop if we created it
                if asyncio.get_event_loop() is loop:
                    loop.close()

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            result = f"❌ Error executing tool: {str(e)}"

        return create_result_response(request_id, {"content": [{"type": "text", "text": result}]})

    def run(self):
        """Run the MCP server."""
        logger.info(f"Starting Gemini MCP Server v{__version__} (Modular)")

        # Configure unbuffered output for proper MCP communication
        sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 1)
        sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 1)

        # Run the JSON-RPC server
        self.server.run()


def main():
    """Main entry point."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    try:
        server = GeminiMCPServer()
        server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
