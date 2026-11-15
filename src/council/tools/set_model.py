"""Tool for setting the active LLM model."""

import logging
from typing import Any

from ..providers.cli_sub import is_excluded_model
from .base import MCPTool, ToolOutput, get_model_manager

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
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": (
                        "The model ID to use (e.g., '~openai/gpt-sol-latest', "
                        "'~moonshotai/kimi-latest')"
                    ),
                },
            },
            "required": ["model"],
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            model_id = (parameters.get("model") or "").strip()

            if not model_id:
                return ToolOutput(success=False, error="Model ID is required")
            if is_excluded_model(model_id):
                return ToolOutput(
                    success=False,
                    error=f"Model '{model_id}' is excluded by policy",
                )

            manager = get_model_manager()
            if not manager:
                return ToolOutput(success=False, error="Model manager not available")

            if hasattr(manager, "get_model_info"):
                model_info = manager.get_model_info(model_id)
                if model_info:
                    logger.info(f"Setting model to {model_id} ({model_info.name})")
                else:
                    logger.warning(f"Model {model_id} not found in cache, setting anyway")

            if hasattr(manager, "set_model"):
                success = manager.set_model(model_id)
                if success:
                    active = getattr(manager, "active_model", model_id)
                    return ToolOutput(
                        success=True,
                        result=f"✓ Active model changed to: {active}",
                    )
                return ToolOutput(
                    success=False,
                    error=f"Failed to set model to {model_id}",
                )
            return ToolOutput(
                success=False,
                error="Manager does not support setting models",
            )

        except Exception as e:
            logger.error(f"Error setting model: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
