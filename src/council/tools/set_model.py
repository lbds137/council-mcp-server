"""Tool for setting the active LLM model."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class SetModelTool(MCPTool):
    """Tool for changing the active model for subsequent requests."""

    @property
    def name(self) -> str:
        return "set_model"

    @property
    def description(self) -> str:
        return (
            "Change the active LLM model for subsequent requests. "
            "Use list_models to see available options."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": (
                        "The model ID to use (e.g., 'google/gemini-2.5-pro', "
                        "'anthropic/claude-3-opus')"
                    ),
                },
            },
            "required": ["model"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            model_id = parameters.get("model", "").strip()

            if not model_id:
                return ToolOutput(success=False, error="Model ID is required")

            # Get manager from server instance
            try:
                from .. import _server_instance

                if _server_instance and hasattr(_server_instance, "council_manager"):
                    manager = _server_instance.council_manager
                elif _server_instance and hasattr(_server_instance, "model_manager"):
                    manager = _server_instance.model_manager
                else:
                    raise AttributeError("Manager not available")
            except (ImportError, AttributeError):
                manager = globals().get("council_manager") or globals().get("model_manager")
                if not manager:
                    return ToolOutput(success=False, error="Model manager not available")

            # Check if the model exists (optional validation)
            if hasattr(manager, "get_model_info"):
                model_info = manager.get_model_info(model_id)
                if model_info:
                    logger.info(f"Setting model to {model_id} ({model_info.name})")
                else:
                    logger.warning(f"Model {model_id} not found in cache, setting anyway")

            # Set the model
            if hasattr(manager, "set_model"):
                success = manager.set_model(model_id)
                if success:
                    # Get model info for response
                    active = getattr(manager, "active_model", model_id)
                    return ToolOutput(
                        success=True,
                        result=f"✓ Active model changed to: {active}",
                    )
                else:
                    return ToolOutput(
                        success=False,
                        error=f"Failed to set model to {model_id}",
                    )
            else:
                return ToolOutput(
                    success=False,
                    error="Manager does not support setting models",
                )

        except Exception as e:
            logger.error(f"Error setting model: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
