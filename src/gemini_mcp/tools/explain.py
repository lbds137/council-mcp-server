"""Explanation tool for understanding complex code or concepts."""

from typing import Any, Dict

from ..models.base import ToolInput, ToolMetadata
from .base import BaseTool


class ExplainTool(BaseTool):
    """Tool for getting explanations from Gemini."""

    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="gemini_explain",
            description="Ask Gemini to explain complex code or concepts",
            tags=["explain", "education", "understanding"],
            version="1.0.0",
        )

    def _get_input_schema(self) -> Dict[str, Any]:
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

    async def _execute(self, input_data: ToolInput) -> str:
        """Execute the explanation request."""
        topic = input_data.parameters.get("topic")
        if not topic:
            raise ValueError("Topic is required for explanation")

        level = input_data.parameters.get("level", "intermediate")

        # Get model manager from context
        model_manager = input_data.context.get("model_manager")
        if not model_manager:
            raise RuntimeError("Model manager not available in context")

        # Build the prompt
        prompt = self._build_prompt(topic, level)

        # Generate explanation
        response_text, model_used = model_manager.generate_content(prompt)

        return self._format_response(response_text, model_used, model_manager.primary_model_name)

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

    def _format_response(self, response_text: str, model_used: str, primary_model: str) -> str:
        """Format the response with model indicator if needed."""
        model_indicator = f" [Model: {model_used}]" if model_used != primary_model else ""
        return f"📚 Explanation{model_indicator}:\n\n{response_text}"
