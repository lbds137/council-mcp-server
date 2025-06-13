"""Synthesis tool for combining multiple perspectives into cohesive insights."""

import logging
from typing import Any, Dict, List

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class SynthesizeTool(MCPTool):
    """Tool for Synthesize."""

    @property
    def name(self) -> str:
        return "synthesize_perspectives"

    @property
    def description(self) -> str:
        return "Synthesize multiple viewpoints or pieces of information into a coherent summary"

    @property
    def input_schema(self) -> Dict[str, Any]:
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

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            topic = parameters.get("topic")
            if not topic:
                return ToolOutput(success=False, error="Topic is required for synthesis")

            perspectives = parameters.get("perspectives", [])
            if not perspectives:
                return ToolOutput(success=False, error="At least one perspective is required")

            # Build the prompt
            prompt = self._build_prompt(topic, perspectives)

            # Get model manager from global context
            from .. import model_manager

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🔄 Synthesis:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

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
