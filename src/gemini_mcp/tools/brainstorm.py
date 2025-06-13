"""Brainstorming tool for generating ideas and solutions."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class BrainstormTool(MCPTool):
    """Tool for Brainstorm."""

    @property
    def name(self) -> str:
        return "gemini_brainstorm"

    @property
    def description(self) -> str:
        return "Brainstorm ideas or solutions with Gemini"

    @property
    def input_schema(self) -> Dict[str, Any]:
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

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            topic = parameters.get("topic")
            if not topic:
                return ToolOutput(success=False, error="Topic is required for brainstorming")

            constraints = parameters.get("constraints", "")

            # Build the prompt
            prompt = self._build_prompt(topic, constraints)

            # Get model manager from global context
            from .. import model_manager

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"💡 Brainstorming Results:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

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
