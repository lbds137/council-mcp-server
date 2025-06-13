"""Test case generation tool for suggesting comprehensive test scenarios."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class TestCasesTool(MCPTool):
    """Tool for Test Cases."""

    @property
    def name(self) -> str:
        return "gemini_test_cases"

    @property
    def description(self) -> str:
        return "Ask Gemini to suggest test cases for code or features"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code_or_feature": {
                    "type": "string",
                    "description": "Code snippet or feature description",
                },
                "test_type": {
                    "type": "string",
                    "description": "Type of tests (unit, integration, edge cases)",
                    "default": "all",
                },
            },
            "required": ["code_or_feature"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            code_or_feature = parameters.get("code_or_feature")
            if not code_or_feature:
                return ToolOutput(success=False, error="Code or feature description is required")

            test_type = parameters.get("test_type", "all")

            # Build the prompt
            prompt = self._build_prompt(code_or_feature, test_type)

            # Get model manager from global context
            from .. import model_manager

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🧪 Test Cases:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, code_or_feature: str, test_type: str) -> str:
        """Build the test case generation prompt."""
        test_type_instructions = {
            "unit": "Focus on unit tests that test individual functions or methods in isolation.",
            "integration": "Focus on integration tests that verify "
            "components work together correctly.",
            "edge": "Focus on edge cases, boundary conditions, and error scenarios.",
            "performance": "Include performance and load testing scenarios.",
            "all": "Provide comprehensive test cases covering all aspects.",
        }

        test_focus = test_type_instructions.get(test_type, test_type_instructions["all"])

        # Detect if input is code or feature description
        is_code = any(
            indicator in code_or_feature
            for indicator in ["def ", "function", "class", "{", "=>", "()"]
        )
        input_type = "code" if is_code else "feature"

        return f"""Please suggest test cases for the following {input_type}:

{code_or_feature}

{test_focus}

For each test case, provide:
1. Test name/description
2. Input/setup required
3. Expected behavior/output
4. Why this test is important

Include both positive (happy path) and negative (error) test cases."""
