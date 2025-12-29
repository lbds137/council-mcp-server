"""Refactor tool for atomic refactoring plans with before/after examples."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class RefactorTool(MCPTool):
    """Tool for generating safe, atomic refactoring plans with before/after code examples."""

    REFACTORING_GOALS = [
        "extract_method",
        "simplify_logic",
        "improve_naming",
        "reduce_complexity",
        "modernize_syntax",
        "remove_duplication",
        "improve_error_handling",
    ]

    @property
    def name(self) -> str:
        return "refactor"

    @property
    def description(self) -> str:
        return (
            "Generate a safe, step-by-step refactoring plan with before/after code examples. "
            "Provides atomic refactoring steps that preserve behavior while improving "
            "code quality. Supports: extract_method, simplify_logic, improve_naming, "
            "reduce_complexity, modernize_syntax, remove_duplication, improve_error_handling."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code to refactor",
                },
                "goal": {
                    "type": "string",
                    "enum": self.REFACTORING_GOALS,
                    "description": (
                        "The refactoring goal: extract_method, simplify_logic, "
                        "improve_naming, reduce_complexity, modernize_syntax, "
                        "remove_duplication, or improve_error_handling"
                    ),
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (e.g., python, javascript, typescript)",
                    "default": "python",
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional context about how the code is used, "
                        "constraints, or additional requirements"
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Optional model override (e.g., 'anthropic/claude-3-opus'). "
                        "Use list_models to see available options."
                    ),
                },
            },
            "required": ["code", "goal"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the refactoring analysis."""
        try:
            code = parameters.get("code")
            goal = parameters.get("goal")

            if not code:
                return ToolOutput(success=False, error="code is required")
            if not goal:
                return ToolOutput(success=False, error="goal is required")
            if goal not in self.REFACTORING_GOALS:
                return ToolOutput(
                    success=False,
                    error=f"Invalid goal. Must be one of: {', '.join(self.REFACTORING_GOALS)}",
                )

            language = parameters.get("language", "python")
            context = parameters.get("context", "")
            model_override = parameters.get("model")

            # Build the prompt
            prompt = self._build_prompt(code, goal, language, context)

            # Get model manager
            try:
                from .. import _server_instance

                if _server_instance and _server_instance.model_manager:
                    model_manager = _server_instance.model_manager
                else:
                    raise AttributeError("Server instance not available")
            except (ImportError, AttributeError):
                model_manager = globals().get("model_manager")
                if not model_manager:
                    return ToolOutput(success=False, error="Model manager not available")

            response_text, model_used = model_manager.generate_content(prompt, model=model_override)

            # Format response
            formatted_response = self._format_response(response_text, model_used, goal)

            return ToolOutput(success=True, result=formatted_response)

        except Exception as e:
            logger.error(f"Refactor tool error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    def _build_prompt(
        self,
        code: str,
        goal: str,
        language: str,
        context: str,
    ) -> str:
        """Build the refactoring prompt."""
        goal_descriptions = {
            "extract_method": (
                "Extract cohesive code blocks into well-named methods/functions. "
                "Identify logical groupings, determine parameters and return values, "
                "and create clear function signatures."
            ),
            "simplify_logic": (
                "Simplify complex conditional logic, reduce nesting, "
                "apply early returns, and make the control flow clearer."
            ),
            "improve_naming": (
                "Improve variable, function, and class names to better express intent. "
                "Apply consistent naming conventions appropriate for the language."
            ),
            "reduce_complexity": (
                "Reduce cyclomatic complexity by breaking down large functions, "
                "simplifying conditions, and improving code structure."
            ),
            "modernize_syntax": (
                f"Update the code to use modern {language} syntax and idioms. "
                "Apply current best practices and language features."
            ),
            "remove_duplication": (
                "Identify and remove duplicate code by extracting common patterns "
                "into reusable functions, classes, or utilities."
            ),
            "improve_error_handling": (
                "Improve error handling with proper exception types, "
                "meaningful error messages, and appropriate recovery strategies."
            ),
        }

        goal_description = goal_descriptions.get(goal, "Improve the code quality.")

        parts = [
            "You are an expert software engineer specializing in code refactoring.",
            f"Your task is to provide a **{goal.replace('_', ' ')}** refactoring plan.",
            "",
            f"## Goal: {goal.replace('_', ' ').title()}",
            goal_description,
            "",
            f"## Language: {language}",
            "",
            "## Code to Refactor",
            f"```{language}",
            code,
            "```",
        ]

        if context:
            parts.extend(
                [
                    "",
                    "## Additional Context",
                    context,
                ]
            )

        parts.extend(
            [
                "",
                "## Required Output Format",
                "",
                "Provide your refactoring plan in this exact structure:",
                "",
                "### Analysis",
                "[Explain what's problematic about the current code and why refactoring helps]",
                "",
                "### Refactoring Plan",
                "",
                "**Step 1: [Action Name]**",
                "- What: [Specific change to make]",
                "- Why: [Benefit of this change]",
                "- Risk: Low/Medium/High",
                "",
                "[Add more steps as needed...]",
                "",
                "### Before",
                f"```{language}",
                "[Original code - copy the exact code provided]",
                "```",
                "",
                "### After",
                f"```{language}",
                "[Fully refactored code - complete, runnable implementation]",
                "```",
                "",
                "### Verification Steps",
                "1. [How to verify the refactor didn't break functionality]",
                "2. [Tests to run or behavior to check]",
                "",
                "### Notes",
                "[Any caveats, edge cases to watch, or follow-up improvements to consider]",
                "",
                "**Important Guidelines:**",
                "- The refactored code MUST be functionally equivalent to the original",
                "- Each step should be atomic and independently verifiable",
                "- Provide complete, copy-pasteable code in the After section",
                "- Highlight any behavioral changes (even if improvements)",
            ]
        )

        return "\n".join(parts)

    def _format_response(
        self,
        response_text: str,
        model_used: str,
        goal: str,
    ) -> str:
        """Format the refactoring response."""
        goal_title = goal.replace("_", " ").title()
        header = f"# Refactoring Plan: {goal_title}"

        return f"{header}\n\n{response_text}\n\n[Model: {model_used}]"
