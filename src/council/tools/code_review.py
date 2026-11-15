"""Code review tool for analyzing code quality and suggesting improvements."""

import logging
from typing import Any

from .base import (
    PRIVATE_ONLY_PROPERTY,
    MCPTool,
    ToolOutput,
    build_generation_kwargs,
    get_model_manager,
    parse_private_only,
)

logger = logging.getLogger(__name__)


class CodeReviewTool(MCPTool):
    """Tool for Code Review."""

    @property
    def name(self) -> str:
        return "code_review"

    @property
    def description(self) -> str:
        return "Review code for issues, improvements, or best practices"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The code to review"},
                "language": {
                    "type": "string",
                    "description": "Programming language (e.g., python, javascript)",
                    "default": "javascript",
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on "
                    "(e.g., security, performance, readability)",
                    "default": "general",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Optional model override (e.g., '~moonshotai/kimi-latest'). "
                        "Use list_models to see available options."
                    ),
                },
                "private_only": dict(PRIVATE_ONLY_PROPERTY),
            },
            "required": ["code"],
        }

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """The answer depends only on the input and the model."""
        return True

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            private_only, priv_err = parse_private_only(parameters)
            if priv_err:
                return ToolOutput(success=False, error=priv_err)

            code = parameters.get("code")
            if not code:
                return ToolOutput(success=False, error="Code is required for review")

            language = parameters.get("language", "javascript")
            focus = parameters.get("focus", "general")
            model_override = parameters.get("model")

            prompt = self._build_prompt(code, language, focus)

            model_manager = get_model_manager()
            if not model_manager:
                return ToolOutput(success=False, error="Model manager not available")

            call_kwargs = build_generation_kwargs(model_override, private_only=private_only)
            response_text, model_used = model_manager.generate_content(prompt, **call_kwargs)
            formatted_response = f"🔍 Code Review:\n\n{response_text}\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, code: str, language: str, focus: str) -> str:
        """Build the code review prompt."""
        focus_instructions = {
            "security": "Pay special attention to security vulnerabilities, "
            "input validation, and potential exploits.",
            "performance": "Focus on performance optimizations, "
            "algorithmic complexity, and resource usage.",
            "readability": "Emphasize code clarity, naming conventions, and maintainability.",
            "best_practices": f"Review against {language} best practices and idiomatic patterns.",
            "general": "Provide a comprehensive review covering all aspects.",
        }

        focus_text = focus_instructions.get(focus, focus_instructions["general"])

        return f"""Please review the following {language} code:

```{language}
{code}
```

{focus_text}

Provide:
1. Overall assessment
2. Specific issues found (if any)
3. Suggestions for improvement
4. Examples of better implementations where applicable

Be constructive and specific in your feedback."""
