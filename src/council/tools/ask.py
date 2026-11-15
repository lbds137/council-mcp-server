"""Tool for asking general questions via Council."""

import logging
from typing import Any

from .base import MCPTool, ToolOutput, get_model_manager

logger = logging.getLogger(__name__)


class AskTool(MCPTool):
    """Tool for asking general questions."""

    @property
    def name(self) -> str:
        return "ask"

    @property
    def description(self) -> str:
        return "Ask a general question or for help with a problem"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question or problem to ask",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context to help understand better",
                    "default": "",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Optional model override (e.g., '~moonshotai/kimi-latest'). "
                        "Use list_models to see available options."
                    ),
                },
                "private_only": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, refuse non-private model vendors (such as Z.ai, "
                        "DeepSeek, Moonshot, Qwen, MiniMax)"
                    ),
                },
            },
            "required": ["question"],
        }

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """The answer depends only on the input and the model."""
        return True

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            # Get parameters
            question = parameters.get("question", "")
            context = parameters.get("context", "")
            model_override = parameters.get("model")
            private_only = parameters.get("private_only", False)

            if not isinstance(private_only, bool):
                return ToolOutput(success=False, error="private_only must be a boolean")

            if not question:
                return ToolOutput(success=False, error="Question is required")

            # Build prompt
            prompt = f"Context: {context}\n\n" if context else ""
            prompt += f"Question: {question}"

            model_manager = get_model_manager()
            if not model_manager:
                return ToolOutput(success=False, error="Model manager not available")

            call_kwargs: dict[str, Any] = {"model": model_override}
            if private_only:
                call_kwargs["private_only"] = True
            response_text, model_used = model_manager.generate_content(prompt, **call_kwargs)
            formatted_response = f"🤖 Response:\n\n{response_text}"
            formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
