"""Tool for asking Gemini general questions."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class AskGeminiTool(MCPTool):
    """Tool for Ask Gemini."""

    @property
    def name(self) -> str:
        return "ask_gemini"

    @property
    def description(self) -> str:
        return "Ask Gemini a general question or for help with a problem"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question or problem to ask Gemini",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context to help Gemini understand better",
                    "default": "",
                },
            },
            "required": ["question"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            # Get parameters
            question = parameters.get("question", "")
            context = parameters.get("context", "")

            if not question:
                return ToolOutput(success=False, error="Question is required")

            # Build prompt
            prompt = f"Context: {context}\n\n" if context else ""
            prompt += f"Question: {question}"

            # Get model manager from server instance
            try:
                # Try to get server instance from parent module
                from .. import _server_instance

                if _server_instance and _server_instance.model_manager:
                    model_manager = _server_instance.model_manager
                else:
                    raise AttributeError("Server instance not available")
            except (ImportError, AttributeError):
                # Fallback for bundled mode - model_manager should be global
                model_manager = globals().get("model_manager")
                if not model_manager:
                    return ToolOutput(success=False, error="Model manager not available")

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🤖 Gemini's Response:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
