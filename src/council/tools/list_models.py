"""Tool for listing available LLM models."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class ListModelsTool(MCPTool):
    """Tool for listing available models from OpenRouter."""

    @property
    def name(self) -> str:
        return "list_models"

    @property
    def description(self) -> str:
        return (
            "List available LLM models with optional filtering by provider, "
            "capability, or free tier. Returns model names, context lengths, and pricing."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": (
                        "Filter by provider (e.g., 'google', 'anthropic', 'openai', "
                        "'meta', 'mistral')"
                    ),
                },
                "capability": {
                    "type": "string",
                    "description": (
                        "Filter by capability (e.g., 'vision', 'code', 'function_calling')"
                    ),
                },
                "free_only": {
                    "type": "boolean",
                    "description": "Only show free tier models",
                    "default": False,
                },
                "search": {
                    "type": "string",
                    "description": "Search models by name or ID",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of models to return",
                    "default": 20,
                },
            },
            "required": [],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            # Get parameters
            provider = parameters.get("provider")
            capability = parameters.get("capability")
            free_only = parameters.get("free_only", False)
            search = parameters.get("search")
            limit = parameters.get("limit", 20)

            # Get manager from server instance
            try:
                from .. import _server_instance

                if _server_instance and hasattr(_server_instance, "council_manager"):
                    manager = _server_instance.council_manager
                elif _server_instance and hasattr(_server_instance, "model_manager"):
                    # Fallback to old model_manager for compatibility
                    manager = _server_instance.model_manager
                else:
                    raise AttributeError("Manager not available")
            except (ImportError, AttributeError):
                # Fallback for bundled mode
                manager = globals().get("council_manager") or globals().get("model_manager")
                if not manager:
                    return ToolOutput(success=False, error="Model manager not available")

            # Get models from manager
            if hasattr(manager, "list_models"):
                models = manager.list_models()
            else:
                return ToolOutput(
                    success=False,
                    error="Manager does not support listing models",
                )

            # Apply filters
            from ..discovery.model_filter import ModelFilter

            filtered = ModelFilter.apply_filters(
                models,
                provider=provider,
                capability=capability,
                free_only=free_only,
                search=search,
                limit=limit,
            )

            # Format output
            if not filtered:
                return ToolOutput(
                    success=True,
                    result="No models found matching the criteria.",
                )

            result_lines = [f"📋 Found {len(filtered)} models:\n"]

            for model in filtered:
                # Format context length nicely
                ctx = model.context_length
                if ctx >= 1_000_000:
                    ctx_str = f"{ctx // 1_000_000}M"
                elif ctx >= 1_000:
                    ctx_str = f"{ctx // 1_000}K"
                else:
                    ctx_str = str(ctx)

                # Build model line
                line = f"• {model.id}"
                if model.is_free:
                    line += " [FREE]"
                line += f" - {ctx_str} context"

                if model.capabilities:
                    caps = ", ".join(model.capabilities)
                    line += f" ({caps})"

                result_lines.append(line)

            return ToolOutput(success=True, result="\n".join(result_lines))

        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
