"""Tool for asking Gemini general questions."""

from typing import Any, Dict

from ..models.base import ToolInput, ToolMetadata
from .base import BaseTool


class AskGeminiTool(BaseTool):
    """Tool for asking Gemini general questions."""

    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ask_gemini",
            description="Ask Gemini a general question or for help with a problem",
            tags=["general", "question", "help"],
        )

    def _get_input_schema(self) -> Dict[str, Any]:
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

    async def _execute(self, input_data: ToolInput) -> str:
        """Execute the ask_gemini tool."""
        # Get parameters
        question = input_data.parameters.get("question", "")
        context = input_data.parameters.get("context", "")

        if not question:
            raise ValueError("Question is required")

        # Build prompt
        prompt = f"Context: {context}\n\n" if context else ""
        prompt += f"Question: {question}"

        # Get model manager from context (will be injected by orchestrator)
        model_manager = input_data.context.get("model_manager")
        if not model_manager:
            raise RuntimeError("Model manager not available in context")

        # Generate response
        response_text, model_used = model_manager.generate_content(prompt)

        # Format response
        formatted_response = self._format_response(response_text, model_used, model_manager)
        return f"🤖 Gemini's Response:\n\n{formatted_response}"

    def _format_response(self, response_text: str, model_used: str, model_manager) -> str:
        """Format response with model information."""
        model_indicator = ""
        if model_used != model_manager.primary_model_name:
            model_indicator = f"\n\n[Model: {model_used}]"
        return response_text + model_indicator
