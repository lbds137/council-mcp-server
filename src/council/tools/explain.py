"""Explanation tool for understanding complex code or concepts."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class ExplainTool(MCPTool):
    """Tool for Explain."""

    @property
    def name(self) -> str:
        return "gemini_explain"

    @property
    def description(self) -> str:
        return "Ask Gemini to explain complex code or concepts"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Code or concept to explain"},
                "level": {
                    "type": "string",
                    "description": "Explanation level (beginner, intermediate, expert)",
                    "default": "intermediate",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            topic = parameters.get("topic")
            if not topic:
                return ToolOutput(success=False, error="Topic is required for explanation")

            level = parameters.get("level", "intermediate")

            # Build the prompt
            prompt = self._build_prompt(topic, level)

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
            formatted_response = f"📚 Explanation:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, topic: str, level: str) -> str:
        """Build the explanation prompt."""
        level_instructions = {
            "beginner": """Explain this as if to someone new to programming:
- Use simple language and avoid jargon
- Provide analogies to everyday concepts
- Break down complex ideas into simple steps
- Include examples that build understanding gradually""",
            "intermediate": """Explain this to someone with programming experience:
- Assume familiarity with basic programming concepts
- Focus on the key insights and patterns
- Include practical examples and use cases
- Mention common pitfalls and best practices""",
            "expert": """Provide an in-depth technical explanation:
- Include implementation details and edge cases
- Discuss performance implications and trade-offs
- Reference relevant algorithms, data structures, or design patterns
- Compare with alternative approaches""",
        }

        level_text = level_instructions.get(level, level_instructions["intermediate"])

        return f"""Please explain the following:

{topic}

{level_text}

Structure your explanation with:
1. Overview/Summary
2. Detailed explanation
3. Examples (if applicable)
4. Key takeaways"""
