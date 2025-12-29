"""Tests for RefactorTool."""

from unittest.mock import Mock, patch

import pytest

from council.tools.refactor import RefactorTool


class TestRefactorTool:
    """Tests for RefactorTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return RefactorTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "refactor"

    def test_description(self, tool):
        """Test tool description."""
        desc = tool.description.lower()
        assert "refactor" in desc
        assert "before" in desc or "after" in desc
        assert "extract_method" in desc

    def test_input_schema_structure(self, tool):
        """Test input schema structure."""
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert "code" in schema["properties"]
        assert "goal" in schema["properties"]
        assert "language" in schema["properties"]
        assert "context" in schema["properties"]
        assert "model" in schema["properties"]

    def test_required_parameters(self, tool):
        """Test required parameters."""
        schema = tool.input_schema

        assert "code" in schema["required"]
        assert "goal" in schema["required"]

    def test_goal_enum_values(self, tool):
        """Test goal property has correct enum values."""
        schema = tool.input_schema
        goal_prop = schema["properties"]["goal"]

        assert goal_prop["type"] == "string"
        assert "enum" in goal_prop
        assert "extract_method" in goal_prop["enum"]
        assert "simplify_logic" in goal_prop["enum"]
        assert "improve_naming" in goal_prop["enum"]
        assert "reduce_complexity" in goal_prop["enum"]
        assert "modernize_syntax" in goal_prop["enum"]

    def test_refactoring_goals_constant(self, tool):
        """Test REFACTORING_GOALS constant."""
        assert "extract_method" in tool.REFACTORING_GOALS
        assert "simplify_logic" in tool.REFACTORING_GOALS
        assert "improve_naming" in tool.REFACTORING_GOALS
        assert "reduce_complexity" in tool.REFACTORING_GOALS
        assert "modernize_syntax" in tool.REFACTORING_GOALS
        assert "remove_duplication" in tool.REFACTORING_GOALS
        assert "improve_error_handling" in tool.REFACTORING_GOALS

    @pytest.mark.asyncio
    async def test_execute_without_code(self, tool):
        """Test execute fails without code."""
        result = await tool.execute(
            {
                "goal": "extract_method",
            }
        )

        assert result.success is False
        assert "code" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_without_goal(self, tool):
        """Test execute fails without goal."""
        result = await tool.execute(
            {
                "code": "def foo(): pass",
            }
        )

        assert result.success is False
        assert "goal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_invalid_goal(self, tool):
        """Test execute fails with invalid goal."""
        result = await tool.execute(
            {
                "code": "def foo(): pass",
                "goal": "invalid_goal",
            }
        )

        assert result.success is False
        assert "invalid" in result.error.lower() or "must be one of" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Test successful refactor execution."""
        mock_response = (
            "### Analysis\nThis code can be improved.\n\n"
            "### Before\n```python\ndef foo(): pass\n```\n\n"
            "### After\n```python\ndef foo() -> None: pass\n```",
            "google/gemini-3-pro-preview",
        )

        mock_manager = Mock()
        mock_manager.generate_content.return_value = mock_response

        with patch("council._server_instance") as mock_server:
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "code": "def foo(): pass",
                    "goal": "extract_method",
                }
            )

        assert result.success is True
        assert "Refactoring Plan" in result.result
        assert "Extract Method" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_context(self, tool):
        """Test execute with additional context."""
        mock_response = ("Refactoring plan with context", "test-model")

        with patch("council._server_instance") as mock_server:
            mock_manager = Mock()
            mock_manager.generate_content.return_value = mock_response
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "code": "def calc(): return a + b",
                    "goal": "improve_naming",
                    "context": "This is used for financial calculations",
                }
            )

        assert result.success is True
        # Verify context was included in the prompt
        call_args = mock_manager.generate_content.call_args
        assert "financial" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_execute_with_different_language(self, tool):
        """Test execute with non-Python language."""
        mock_response = ("JavaScript refactoring", "test-model")

        with patch("council._server_instance") as mock_server:
            mock_manager = Mock()
            mock_manager.generate_content.return_value = mock_response
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "code": "function foo() { return 42; }",
                    "goal": "modernize_syntax",
                    "language": "javascript",
                }
            )

        assert result.success is True
        # Verify language was used in prompt
        call_args = mock_manager.generate_content.call_args
        assert "javascript" in call_args[0][0].lower()

    def test_build_prompt_extract_method(self, tool):
        """Test prompt building for extract_method goal."""
        prompt = tool._build_prompt(
            code="def foo(): pass",
            goal="extract_method",
            language="python",
            context="",
        )

        assert "extract" in prompt.lower()
        assert "method" in prompt.lower() or "function" in prompt.lower()
        assert "def foo(): pass" in prompt
        assert "python" in prompt.lower()
        assert "Before" in prompt
        assert "After" in prompt

    def test_build_prompt_simplify_logic(self, tool):
        """Test prompt building for simplify_logic goal."""
        prompt = tool._build_prompt(
            code="if a: if b: if c: pass",
            goal="simplify_logic",
            language="python",
            context="",
        )

        assert "simplify" in prompt.lower()
        assert "logic" in prompt.lower() or "nesting" in prompt.lower()

    def test_build_prompt_with_context(self, tool):
        """Test prompt includes context when provided."""
        prompt = tool._build_prompt(
            code="def calc(): pass",
            goal="improve_naming",
            language="python",
            context="This handles user authentication",
        )

        assert "Additional Context" in prompt
        assert "user authentication" in prompt

    def test_build_prompt_all_goals(self, tool):
        """Test prompt building works for all goals."""
        for goal in tool.REFACTORING_GOALS:
            prompt = tool._build_prompt(
                code="def test(): pass",
                goal=goal,
                language="python",
                context="",
            )

            # Should contain structured output sections
            assert "Analysis" in prompt
            assert "Before" in prompt
            assert "After" in prompt
            assert "Verification" in prompt

    def test_format_response(self, tool):
        """Test response formatting."""
        formatted = tool._format_response(
            response_text="Analysis content here",
            model_used="test-model",
            goal="extract_method",
        )

        assert "Refactoring Plan" in formatted
        assert "Extract Method" in formatted
        assert "Analysis content here" in formatted
        assert "test-model" in formatted

    def test_format_response_all_goals(self, tool):
        """Test formatting works for all goal types."""
        for goal in tool.REFACTORING_GOALS:
            formatted = tool._format_response(
                response_text="Content",
                model_used="test-model",
                goal=goal,
            )

            # Goal should be title-cased in header
            expected_title = goal.replace("_", " ").title()
            assert expected_title in formatted

    def test_get_mcp_definition(self, tool):
        """Test MCP definition generation."""
        definition = tool.get_mcp_definition()

        assert definition["name"] == "refactor"
        assert "description" in definition
        assert "inputSchema" in definition


class TestRefactorToolIntegration:
    """Integration tests for RefactorTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return RefactorTool()

    @pytest.mark.asyncio
    async def test_execute_with_model_override(self, tool):
        """Test execute with model override."""
        mock_response = ("Refactored by opus", "anthropic/claude-3-opus")

        with patch("council._server_instance") as mock_server:
            mock_manager = Mock()
            mock_manager.generate_content.return_value = mock_response
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "code": "def foo(): pass",
                    "goal": "improve_naming",
                    "model": "anthropic/claude-3-opus",
                }
            )

        assert result.success is True
        # Verify model override was passed
        call_args = mock_manager.generate_content.call_args
        assert call_args[1]["model"] == "anthropic/claude-3-opus"

    @pytest.mark.asyncio
    async def test_execute_error_handling(self, tool):
        """Test error handling when model manager fails."""
        with patch("council._server_instance") as mock_server:
            mock_manager = Mock()
            mock_manager.generate_content.side_effect = Exception("API Error")
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "code": "def foo(): pass",
                    "goal": "extract_method",
                }
            )

        assert result.success is False
        assert "Error" in result.error
