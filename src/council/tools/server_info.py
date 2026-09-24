"""Server information tool for checking status and configuration."""

import json
from typing import Any, Dict

from ..tools.base import MCPTool, ToolOutput
from .conversation import get_session_manager

__version__ = "4.0.0"


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
            # In modular mode, get from council module
            # In bundled mode, will be set as global _server_instance
            server = None

            # Try modular approach first
            try:
                import council

                server = getattr(council, "_server_instance", None)
            except ImportError:
                pass

            # Fall back to global _server_instance (for bundled mode)
            if not server:
                server = globals().get("_server_instance", None)

            # Declare info variable
            info: Dict[str, Any]

            if not server:
                # Fallback to basic info if server instance not available
                info = {
                    "version": __version__,
                    "architecture": "modular",
                    "backend": "OpenRouter",
                    "status": "running",
                    "note": "Full stats unavailable - server instance not accessible",
                }
            else:
                # Get list of available tools from registry
                registered_tools = server.tool_registry.list_tools()

                info = {
                    "version": __version__,
                    "architecture": "modular",
                    "backend": "OpenRouter",
                    "available_tools": registered_tools,
                    "components": {
                        "tools_registered": len(registered_tools),
                        "cache_stats": server.cache.get_stats() if server.cache else None,
                        "conversations": self._conversation_stats(),
                    },
                    "models": self._get_model_info(server.model_manager),
                }

                if server.orchestrator:
                    info["execution_stats"] = server.orchestrator.get_execution_stats()

            # Add quick reference guide
            quick_guide = self._get_quick_guide()

            json_info = json.dumps(info, indent=2)
            result = f"Council MCP Server v{__version__}\n\n{json_info}\n\n{quick_guide}"
            return ToolOutput(success=True, result=result)

        except Exception as e:
            return ToolOutput(success=False, error=f"Error getting server info: {str(e)}")

    @staticmethod
    def _conversation_stats() -> Dict[str, Any]:
        """How many conversation sessions are open."""
        return {"active": len(get_session_manager().sessions)}

    def _get_model_info(self, model_manager) -> Dict[str, Any]:
        """Get model manager information."""
        if not model_manager:
            return {"initialized": False}

        info: Dict[str, Any] = {
            "initialized": True,
            "default_model": getattr(model_manager, "default_model", None),
            "active_model": getattr(model_manager, "active_model", None),
        }

        # Get stats if available
        try:
            stats = model_manager.get_stats()
            if stats:
                info["stats"] = stats
        except Exception:
            pass

        # Get model cache info if available
        try:
            cache = getattr(model_manager, "model_cache", None)
            if cache:
                info["model_cache"] = cache.get_stats()
        except Exception:
            pass

        return info

    def _get_quick_guide(self) -> str:
        """Generate a quick model selection guide from the curated registry."""
        from ..discovery.model_registry import (
            FREE_TIER_MODELS,
            ModelClass,
            TaskType,
            get_model_class_description,
            get_recommendations_for_task,
        )

        lines = ["## Quick Model Selection Guide", "", "**By Task Type:**"]
        for task in TaskType:
            models = ", ".join(get_recommendations_for_task(task, limit=3))
            lines.append(f"• {task.value.replace('_', ' ').title()} → {models}")

        lines.extend(["", "**Model Classes:**"])
        for model_class in ModelClass:
            description = get_model_class_description(model_class)
            lines.append(f"• {model_class.value.upper()}: {description}")

        lines.extend(["", "**Free Tier Options:**"])
        lines.extend(f"• {model}" for model in FREE_TIER_MODELS)

        lines.extend(
            ["", "💡 Use `recommend_model` tool for detailed task-specific recommendations."]
        )
        return "\n".join(lines)
