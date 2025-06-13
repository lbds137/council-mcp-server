"""Test case generation tool for suggesting comprehensive test scenarios."""

from typing import Dict, Any

from .base import BaseTool
from ..models.base import ToolInput, ToolMetadata


class TestCasesTool(BaseTool):
    """Tool for generating test cases with Gemini."""
    
    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="gemini_test_cases",
            description="Ask Gemini to suggest test cases for code or features",
            tags=["testing", "quality", "test-cases"],
            version="1.0.0"
        )
    
    def _get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code_or_feature": {
                    "type": "string",
                    "description": "Code snippet or feature description"
                },
                "test_type": {
                    "type": "string",
                    "description": "Type of tests (unit, integration, edge cases)",
                    "default": "all"
                }
            },
            "required": ["code_or_feature"]
        }
    
    async def _execute(self, input_data: ToolInput) -> str:
        """Execute test case generation."""
        code_or_feature = input_data.parameters.get("code_or_feature")
        if not code_or_feature:
            raise ValueError("Code or feature description is required")
            
        test_type = input_data.parameters.get("test_type", "all")
        
        # Get model manager from context
        model_manager = input_data.context.get("model_manager")
        if not model_manager:
            raise RuntimeError("Model manager not available in context")
        
        # Build the prompt
        prompt = self._build_prompt(code_or_feature, test_type)
        
        # Generate test cases
        response_text, model_used = model_manager.generate_content(prompt)
        
        return self._format_response(response_text, model_used, model_manager.primary_model_name)
    
    def _build_prompt(self, code_or_feature: str, test_type: str) -> str:
        """Build the test case generation prompt."""
        test_type_instructions = {
            "unit": "Focus on unit tests that test individual functions or methods in isolation.",
            "integration": "Focus on integration tests that verify components work together correctly.",
            "edge": "Focus on edge cases, boundary conditions, and error scenarios.",
            "performance": "Include performance and load testing scenarios.",
            "all": "Provide comprehensive test cases covering all aspects."
        }
        
        test_focus = test_type_instructions.get(test_type, test_type_instructions["all"])
        
        # Detect if input is code or feature description
        is_code = any(indicator in code_or_feature for indicator in ["def ", "function", "class", "{", "=>", "()"])
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
    
    def _format_response(self, response_text: str, model_used: str, primary_model: str) -> str:
        """Format the response with model indicator if needed."""
        model_indicator = f" [Model: {model_used}]" if model_used != primary_model else ""
        return f"🧪 Test Cases{model_indicator}:\n\n{response_text}"