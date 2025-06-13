"""Server information tool for checking status and configuration."""

import json
from typing import Any, Dict

from ..tools.base import MCPTool, ToolOutput

__version__ = "3.0.0"


class ServerInfoTool(MCPTool):
    """Tool for getting server information and status."""

    @property
    def name(self) -> str:
        return "server_info"

    @property
    def description(self) -> str:
        return "Get server version and status"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            # Access the server components through global context
            # In modular mode, get from gemini_mcp module
            # In bundled mode, will be set as global _server_instance
            server = None

            # Try modular approach first
            try:
                import gemini_mcp

                server = getattr(gemini_mcp, "_server_instance", None)
            except ImportError:
                pass

            # Fall back to global _server_instance (for bundled mode)
            if not server:
                server = globals().get("_server_instance", None)
            if not server:
                # Fallback to basic info if server instance not available
                info = {
                    "version": __version__,
                    "architecture": "modular",
                    "status": "running",
                    "note": "Full stats unavailable - server instance not accessible",
                }
            else:
                # Get list of available tools from registry
                registered_tools = server.tool_registry.list_tools()
                all_tools = registered_tools  # server_info is now just another tool

                info = {
                    "version": __version__,
                    "architecture": "modular",
                    "available_tools": all_tools,
                    "components": {
                        "tools_registered": len(registered_tools),
                        "total_tools_available": len(all_tools),
                        "cache_stats": server.cache.get_stats() if server.cache else None,
                        "memory_stats": server.memory.get_stats() if server.memory else None,
                    },
                    "models": {
                        "initialized": server.model_manager is not None,
                        "primary": getattr(server.model_manager, "primary_model_name", None),
                        "fallback": getattr(server.model_manager, "fallback_model_name", None),
                    },
                }

                if server.orchestrator:
                    info["execution_stats"] = server.orchestrator.get_execution_stats()

            result = f"🤖 Gemini MCP Server v{__version__}\n\n{json.dumps(info, indent=2)}"
            return ToolOutput(success=True, result=result)

        except Exception as e:
            return ToolOutput(success=False, error=f"Error getting server info: {str(e)}")
