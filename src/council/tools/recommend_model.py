"""Tool for recommending models based on task type."""

import logging
from typing import Any

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)

RATING_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3}


def _tokens(count: int) -> str:
    """A token count as a short label: 1.049M, 1.05M, 500K, 262K.

    Three decimals keep 1,048,576 and 1,050,000 apart.
    """
    if count >= 1_000_000:
        return f"{count / 1_000_000:.3f}".rstrip("0").rstrip(".") + "M"
    if count >= 1_000:
        return f"{count // 1_000}K"
    return str(count)


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
    def input_schema(self) -> dict[str, Any]:
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
                    "description": (
                        "Minimum context window needed, in tokens. Compared with the window "
                        "most providers serve, not the largest any one host offers"
                    ),
                },
            },
            "required": ["task"],
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            from ..discovery.model_registry import (
                FREE_TIER_MODELS,
                ModelClass,
                TaskType,
                get_model_class_description,
                get_model_metadata,
            )

            task_str = parameters.get("task", "general")
            prefer_free = parameters.get("prefer_free", False)
            prefer_fast = bool(parameters.get("prefer_fast", False))
            min_context = parameters.get("min_context")
            if min_context is not None and (
                isinstance(min_context, bool) or not isinstance(min_context, int) or min_context < 1
            ):
                return ToolOutput(
                    success=False, error="min_context must be a positive number of tokens"
                )

            # Parse task type
            try:
                task = TaskType(task_str)
            except ValueError:
                task = TaskType.GENERAL

            recommendations, dropped = self._select(task, prefer_fast, min_context)

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
            if prefer_fast:
                result_lines.append("_Fast (flash-class) models first._")
            if min_context:
                result_lines.append(f"_Only models serving at least {_tokens(min_context)}._")
            if not recommendations:
                result_lines.append(
                    f"No recommended model serves {_tokens(min_context or 0)} tokens. "
                    "Use `list_models` to search the full catalog."
                )

            for i, model_id in enumerate(recommendations, 1):
                metadata = get_model_metadata(model_id)
                if metadata:
                    # Get strength for this task
                    strength = metadata.strengths.get(task, "B")

                    # Build model line with the full ID, which is what `model` accepts
                    class_badge = f"[{metadata.model_class.value.upper()}]"

                    line = f"{i}. **{model_id}** {class_badge} (Rating: {strength})"
                    if metadata.context_window:
                        line += f" · {_tokens(metadata.context_window)} context"
                    if metadata.description:
                        line += f"\n   _{metadata.description}_"
                    result_lines.append(line)
                else:
                    # Fallback for models not in registry
                    result_lines.append(f"{i}. {model_id}")

            if dropped:
                result_lines.append("")
                result_lines.append(
                    "Left out for a smaller window: "
                    + ", ".join(f"{m} ({_tokens(w)})" for m, w in dropped)
                )

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

    @staticmethod
    def _select(
        task: Any, prefer_fast: bool, min_context: int | None
    ) -> tuple[list[str], list[tuple[str, int]]]:
        """Pick up to five models for the task.

        Returns:
            The models to recommend, and the (model, window) pairs left out
            because their context window is below min_context.
        """
        from ..discovery.model_registry import (
            MODEL_REGISTRY,
            TASK_RECOMMENDATIONS,
            ModelClass,
            TaskType,
            get_model_metadata,
        )

        candidates = list(TASK_RECOMMENDATIONS.get(task, TASK_RECOMMENDATIONS[TaskType.GENERAL]))

        if prefer_fast:
            # Every fast model rated for this task, best rating first, ahead of the rest
            fast = [
                model_id
                for model_id, metadata in MODEL_REGISTRY.items()
                if metadata.model_class == ModelClass.FLASH and task in metadata.strengths
            ]
            fast.sort(key=lambda m: RATING_ORDER.get(MODEL_REGISTRY[m].strengths[task], 9))
            candidates = fast + [m for m in candidates if m not in fast]

        dropped: list[tuple[str, int]] = []
        if min_context:
            kept = []
            for model_id in candidates:
                metadata = get_model_metadata(model_id)
                window = metadata.context_window if metadata else 0
                if window >= min_context:
                    kept.append(model_id)
                else:
                    dropped.append((model_id, window))
            candidates = kept

        return candidates[:5], dropped
