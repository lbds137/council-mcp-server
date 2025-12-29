"""Brainstorming tool for generating ideas and solutions."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class BrainstormTool(MCPTool):
    """Tool for Brainstorm."""

    @property
    def name(self) -> str:
        return "brainstorm"

    @property
    def description(self) -> str:
        return "Brainstorm ideas or solutions"

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
                "model": {
                    "type": "string",
                    "description": (
                        "Optional model override (e.g., 'anthropic/claude-3-opus'). "
                        "Use list_models to see available options."
                    ),
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
            model_override = parameters.get("model")

            # Build the prompt
            prompt = self._build_prompt(topic, constraints)

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

            response_text, model_used = model_manager.generate_content(prompt, model=model_override)
            formatted_response = f"💡 Brainstorming Results:\n\n{response_text}"
            formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"API error: {e}")
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
