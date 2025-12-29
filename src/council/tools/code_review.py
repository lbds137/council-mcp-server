"""Code review tool for analyzing code quality and suggesting improvements."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

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
    def input_schema(self) -> Dict[str, Any]:
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
                        "Optional model override (e.g., 'anthropic/claude-3-opus'). "
                        "Use list_models to see available options."
                    ),
                },
            },
            "required": ["code"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            code = parameters.get("code")
            if not code:
                return ToolOutput(success=False, error="Code is required for review")

            language = parameters.get("language", "javascript")
            focus = parameters.get("focus", "general")
            model_override = parameters.get("model")

            # Build the prompt
            prompt = self._build_prompt(code, language, focus)

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
            formatted_response = f"🔍 Code Review:\n\n{response_text}"
            formatted_response += f"\n\n[Model: {model_used}]"
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
