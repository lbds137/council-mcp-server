"""Synthesis tool for combining multiple perspectives into cohesive insights."""

from typing import Any, Dict, List

from ..models.base import ToolInput, ToolMetadata
from .base import BaseTool


class SynthesizeTool(BaseTool):
    """Tool for synthesizing multiple perspectives with Gemini."""

    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="synthesize_perspectives",
            description="Synthesize multiple viewpoints or pieces of information into a coherent summary",
            tags=["synthesis", "summary", "analysis"],
            version="1.0.0",
        )

    def _get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic or question being addressed"},
                "perspectives": {
                    "type": "array",
                    "description": "List of different perspectives or pieces of information",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Source or viewpoint identifier",
                            },
                            "content": {
                                "type": "string",
                                "description": "The perspective or information",
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["topic", "perspectives"],
        }

    async def _execute(self, input_data: ToolInput) -> str:
        """Execute the synthesis."""
        topic = input_data.parameters.get("topic")
        if not topic:
            raise ValueError("Topic is required for synthesis")

        perspectives = input_data.parameters.get("perspectives", [])
        if not perspectives:
            raise ValueError("At least one perspective is required")

        # Get model manager from context
        model_manager = input_data.context.get("model_manager")
        if not model_manager:
            raise RuntimeError("Model manager not available in context")

        # Build the prompt
        prompt = self._build_prompt(topic, perspectives)

        # Generate synthesis
        response_text, model_used = model_manager.generate_content(prompt)

        return self._format_response(response_text, model_used, model_manager.primary_model_name)

    def _build_prompt(self, topic: str, perspectives: List[Dict[str, str]]) -> str:
        """Build the synthesis prompt."""
        perspectives_text = "\n\n".join(
            [
                f"**{p.get('source', f'Perspective {i+1}')}:**\n{p['content']}"
                for i, p in enumerate(perspectives)
            ]
        )

        return f"""Please synthesize the following perspectives on: {topic}

{perspectives_text}

Provide a balanced synthesis that:
1. Identifies common themes and agreements
2. Highlights key differences and tensions
3. Evaluates the strengths and weaknesses of each perspective
4. Proposes a unified understanding or framework
5. Suggests actionable insights or next steps

Be objective and fair to all viewpoints while providing critical analysis."""

    def _format_response(self, response_text: str, model_used: str, primary_model: str) -> str:
        """Format the response with model indicator if needed."""
        model_indicator = f" [Model: {model_used}]" if model_used != primary_model else ""
        return f"🔄 Synthesis{model_indicator}:\n\n{response_text}"
