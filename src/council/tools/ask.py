"""Tool for asking general questions via Council."""

import logging
from typing import Any

from .base import (
    PRIVATE_ONLY_PROPERTY,
    MCPTool,
    ToolOutput,
    build_generation_kwargs,
    get_model_manager,
    parse_private_only,
)

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
                "private_only": dict(PRIVATE_ONLY_PROPERTY),
            },
            "required": ["question"],
        }

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """The answer depends only on the input and the model."""
        return True

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            private_only, priv_err = parse_private_only(parameters)
            if priv_err:
                return ToolOutput(success=False, error=priv_err)

            question = parameters.get("question", "")
            context = parameters.get("context", "")
            model_override = parameters.get("model")

            if not question:
                return ToolOutput(success=False, error="Question is required")

            prompt = f"Context: {context}\n\n" if context else ""
            prompt += f"Question: {question}"

            model_manager = get_model_manager()
            if not model_manager:
                return ToolOutput(success=False, error="Model manager not available")

            call_kwargs = build_generation_kwargs(model_override, private_only=private_only)
            response_text, model_used = model_manager.generate_content(prompt, **call_kwargs)
            formatted_response = f"🤖 Response:\n\n{response_text}\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
