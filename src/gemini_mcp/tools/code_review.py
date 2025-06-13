"""Code review tool for analyzing code quality and suggesting improvements."""

from typing import Dict, Any

from .base import BaseTool
from ..models.base import ToolInput, ToolMetadata


class CodeReviewTool(BaseTool):
    """Tool for getting code reviews from Gemini."""
    
    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="gemini_code_review",
            description="Ask Gemini to review code for issues, improvements, or best practices",
            tags=["code", "review", "quality"],
            version="1.0.0"
        )
    
    def _get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code to review"
                },
                "language": {
                    "type": "string", 
                    "description": "Programming language (e.g., python, javascript)",
                    "default": "javascript"
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on (e.g., security, performance, readability)",
                    "default": "general"
                }
            },
            "required": ["code"]
        }
    
    async def _execute(self, input_data: ToolInput) -> str:
        """Execute the code review."""
        code = input_data.parameters.get("code")
        if not code:
            raise ValueError("Code is required for review")
            
        language = input_data.parameters.get("language", "javascript")
        focus = input_data.parameters.get("focus", "general")
        
        # Get model manager from context
        model_manager = input_data.context.get("model_manager")
        if not model_manager:
            raise RuntimeError("Model manager not available in context")
        
        # Build the prompt
        prompt = self._build_prompt(code, language, focus)
        
        # Generate review
        response_text, model_used = model_manager.generate_content(prompt)
        
        return self._format_response(response_text, model_used, model_manager.primary_model_name)
    
    def _build_prompt(self, code: str, language: str, focus: str) -> str:
        """Build the code review prompt."""
        focus_instructions = {
            "security": "Pay special attention to security vulnerabilities, input validation, and potential exploits.",
            "performance": "Focus on performance optimizations, algorithmic complexity, and resource usage.",
            "readability": "Emphasize code clarity, naming conventions, and maintainability.",
            "best_practices": f"Review against {language} best practices and idiomatic patterns.",
            "general": "Provide a comprehensive review covering all aspects."
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
    
    def _format_response(self, response_text: str, model_used: str, primary_model: str) -> str:
        """Format the response with model indicator if needed."""
        model_indicator = f" [Model: {model_used}]" if model_used != primary_model else ""
        return f"🔍 Code Review{model_indicator}:\n\n{response_text}"