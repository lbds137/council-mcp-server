"""Brainstorming tool for generating ideas and solutions."""

from typing import Any, Dict

from ..models.base import ToolInput, ToolMetadata
from .base import BaseTool


class BrainstormTool(BaseTool):
    """Tool for brainstorming ideas with Gemini."""

    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="gemini_brainstorm",
            description="Brainstorm ideas or solutions with Gemini",
            tags=["creative", "ideas", "brainstorm"],
            version="1.0.0",
        )

    def _get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic or problem to brainstorm about",
                },
                "constraints": {
                    "type": "string",
                    "description": "Any constraints or requirements to consider",
                    "default": "",
                },
            },
            "required": ["topic"],
        }

    async def _execute(self, input_data: ToolInput) -> str:
        """Execute the brainstorming session."""
        topic = input_data.parameters.get("topic")
        if not topic:
            raise ValueError("Topic is required for brainstorming")

        constraints = input_data.parameters.get("constraints", "")

        # Get model manager from context
        model_manager = input_data.context.get("model_manager")
        if not model_manager:
            raise RuntimeError("Model manager not available in context")

        # Build the prompt
        prompt = self._build_prompt(topic, constraints)

        # Generate ideas
        response_text, model_used = model_manager.generate_content(prompt)

        return self._format_response(response_text, model_used, model_manager.primary_model_name)

    def _build_prompt(self, topic: str, constraints: str) -> str:
        """Build the brainstorming prompt."""
        constraints_text = f"\nConstraints to consider:\n{constraints}" if constraints else ""

        return f"""Let's brainstorm ideas about: {topic}{constraints_text}

Please provide:
1. Creative and innovative ideas
2. Different perspectives and approaches
3. Potential challenges and solutions
4. Actionable next steps

Be creative but practical. Think outside the box while considering feasibility."""

    def _format_response(self, response_text: str, model_used: str, primary_model: str) -> str:
        """Format the response with model indicator if needed."""
        model_indicator = f" [Model: {model_used}]" if model_used != primary_model else ""
        return f"💡 Brainstorming Results{model_indicator}:\n\n{response_text}"
