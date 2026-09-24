"""Tool for recommending models based on task type."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class RecommendModelTool(MCPTool):
    """Tool for recommending the best model for a specific task."""

    @property
    def name(self) -> str:
        return "recommend_model"

    @property
    def description(self) -> str:
        return (
            "Recommend the best AI model for a specific task. "
            "Provides curated recommendations based on published benchmarks where they exist. "
            "Task types: coding, code_review, reasoning, creative, vision, long_context, general."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Type of task: 'coding', 'code_review', 'reasoning', "
                        "'creative', 'vision', 'long_context', or 'general'"
                    ),
                    "enum": [
                        "coding",
                        "code_review",
                        "reasoning",
                        "creative",
                        "vision",
                        "long_context",
                        "general",
                    ],
                },
                "prefer_free": {
                    "type": "boolean",
                    "description": "Prefer free tier models if available",
                    "default": False,
                },
                "prefer_fast": {
                    "type": "boolean",
                    "description": "Prefer faster (flash-class) models over quality",
                    "default": False,
                },
                "min_context": {
                    "type": "integer",
                    "description": "Minimum context length needed (in tokens)",
                },
            },
            "required": ["task"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            from ..discovery.model_registry import (
                FREE_TIER_MODELS,
                ModelClass,
                TaskType,
                get_model_class_description,
                get_model_metadata,
                get_recommendations_for_task,
            )

            task_str = parameters.get("task", "general")
            prefer_free = parameters.get("prefer_free", False)
            # TODO: Implement prefer_fast and min_context filtering
            _ = parameters.get("prefer_fast", False)
            _ = parameters.get("min_context")

            # Parse task type
            try:
                task = TaskType(task_str)
            except ValueError:
                task = TaskType.GENERAL

            # Get recommendations
            recommendations = get_recommendations_for_task(task, limit=5)

            # Build response
            result_lines = [
                f"🎯 **Model Recommendations for {task.value.replace('_', ' ').title()}**",
                "",
            ]

            # If prefer_free, show free options first
            if prefer_free:
                result_lines.append("### Free Tier Options")
                for model_id in FREE_TIER_MODELS:
                    result_lines.append(f"• {model_id}")
                result_lines.append("")

            # Main recommendations
            result_lines.append("### Top Recommendations")

            for i, model_id in enumerate(recommendations, 1):
                metadata = get_model_metadata(model_id)
                if metadata:
                    # Get strength for this task
                    strength = metadata.strengths.get(task, "B")

                    # Build model line with the full ID, which is what `model` accepts
                    class_badge = f"[{metadata.model_class.value.upper()}]"

                    line = f"{i}. **{model_id}** {class_badge} (Rating: {strength})"
                    if metadata.description:
                        line += f"\n   _{metadata.description}_"
                    result_lines.append(line)
                else:
                    # Fallback for models not in registry
                    result_lines.append(f"{i}. {model_id}")

            # Add class guide
            result_lines.extend(
                [
                    "",
                    "### Model Classes",
                    f"• **Flash**: {get_model_class_description(ModelClass.FLASH)}",
                    f"• **Pro**: {get_model_class_description(ModelClass.PRO)}",
                    f"• **Deep**: {get_model_class_description(ModelClass.DEEP)}",
                    "",
                    "### Rating Scale",
                    "S = Best in class | A = Excellent | B = Good | C = Adequate",
                ]
            )

            # Add notes for specific tasks
            task_notes = {
                TaskType.CODING: (
                    "\n💡 **Tip**: DeepSeek V4 Pro leads open-weight models on "
                    "SWE-bench Verified (80.6%, Sept 2026)."
                ),
                TaskType.CODE_REVIEW: (
                    "\n💡 **Tip**: No ranked code-review benchmark exists; these follow "
                    "the coding results at a price suited to frequent reviews."
                ),
                TaskType.REASONING: (
                    "\n💡 **Tip**: GPT-6 Astra reports 96.1% on GPQA Diamond (vendor figure); "
                    "Gemini 3.1 Pro scores 95.5%."
                ),
                TaskType.CREATIVE: (
                    "\n💡 **Tip**: Kimi K3 ranks #2 on EQ-Bench creative writing, "
                    "the highest of any non-Anthropic model (Sept 2026)."
                ),
                TaskType.VISION: (
                    "\n💡 **Tip**: Gemini also takes audio and video; Qwen3.8 Max and "
                    "Kimi K3 take video. No vision leaderboard covers these models yet."
                ),
                TaskType.LONG_CONTEXT: (
                    "\n💡 **Tip**: No long-context benchmark covers these models yet; "
                    "all four serve about 1M tokens."
                ),
            }

            if task in task_notes:
                result_lines.append(task_notes[task])

            return ToolOutput(success=True, result="\n".join(result_lines))

        except Exception as e:
            logger.error(f"Error recommending model: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
