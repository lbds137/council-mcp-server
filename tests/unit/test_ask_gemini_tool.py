"""Unit tests for the ask_gemini tool."""

from unittest.mock import Mock

import pytest

from gemini_mcp.models.base import ToolInput
from gemini_mcp.tools.ask_gemini import AskGeminiTool
from tests.fixtures import create_mock_model_manager


class TestAskGeminiTool:
    """Test suite for AskGeminiTool."""

    @pytest.fixture
    def tool(self):
        """Create an AskGeminiTool instance."""
        return AskGeminiTool()

    def test_metadata(self, tool):
        """Test tool metadata."""
        metadata = tool.metadata
        assert metadata.name == "ask_gemini"
        assert "general question" in metadata.description
        assert "general" in metadata.tags

    def test_input_schema(self, tool):
        """Test input schema definition."""
        schema = tool._get_input_schema()

        assert schema["type"] == "object"
        assert "question" in schema["properties"]
        assert "context" in schema["properties"]
        assert "question" in schema["required"]
        assert "context" not in schema["required"]  # Optional

    @pytest.mark.asyncio
    async def test_execute_with_question_only(self, tool):
        """Test execution with just a question."""
        model_manager = create_mock_model_manager()

        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={"question": "What is AI?"},
            context={"model_manager": model_manager},
        )

        result = await tool._execute(input_data)

        assert "🤖 Gemini's Response:" in result
        assert "Test response" in result

        # Verify model was called correctly
        model_manager.generate_content.assert_called_once()
        call_args = model_manager.generate_content.call_args[0][0]
        assert "Question: What is AI?" in call_args
        assert "Context:" not in call_args  # No context provided

    @pytest.mark.asyncio
    async def test_execute_with_context(self, tool):
        """Test execution with question and context."""
        model_manager = create_mock_model_manager()

        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={"question": "What is AI?", "context": "We're discussing machine learning"},
            context={"model_manager": model_manager},
        )

        result = await tool._execute(input_data)

        assert "🤖 Gemini's Response:" in result
        assert "Test response" in result

        # Verify prompt includes context
        call_args = model_manager.generate_content.call_args[0][0]
        assert "Context: We're discussing machine learning" in call_args
        assert "Question: What is AI?" in call_args

    @pytest.mark.asyncio
    async def test_execute_without_question(self, tool):
        """Test that execution fails without a question."""
        model_manager = create_mock_model_manager()

        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={},  # No question
            context={"model_manager": model_manager},
        )

        with pytest.raises(ValueError, match="Question is required"):
            await tool._execute(input_data)

    @pytest.mark.asyncio
    async def test_execute_without_model_manager(self, tool):
        """Test that execution fails without model manager in context."""
        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={"question": "Test question"},
            context={},  # No model manager
        )

        with pytest.raises(RuntimeError, match="Model manager not available"):
            await tool._execute(input_data)

    @pytest.mark.asyncio
    async def test_format_response_with_primary_model(self, tool):
        """Test response formatting when primary model is used."""
        model_manager = create_mock_model_manager()
        model_manager.primary_model_name = "primary-model"
        model_manager.generate_content.return_value = ("Response text", "primary-model")

        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={"question": "Test"},
            context={"model_manager": model_manager},
        )

        result = await tool._execute(input_data)

        # Should not include model indicator for primary model
        assert "[Model:" not in result
        assert "Response text" in result

    @pytest.mark.asyncio
    async def test_format_response_with_fallback_model(self, tool):
        """Test response formatting when fallback model is used."""
        model_manager = create_mock_model_manager()
        model_manager.primary_model_name = "primary-model"
        model_manager.generate_content.return_value = ("Response text", "fallback-model")

        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={"question": "Test"},
            context={"model_manager": model_manager},
        )

        result = await tool._execute(input_data)

        # Should include model indicator for fallback model
        assert "[Model: fallback-model]" in result
        assert "Response text" in result

    @pytest.mark.asyncio
    async def test_empty_context_parameter(self, tool):
        """Test that empty context parameter is handled correctly."""
        model_manager = create_mock_model_manager()

        input_data = ToolInput(
            tool_name="ask_gemini",
            parameters={"question": "Test", "context": ""},  # Empty context
            context={"model_manager": model_manager},
        )

        result = await tool._execute(input_data)

        # Should work fine, just no context in prompt
        assert "🤖 Gemini's Response:" in result

        call_args = model_manager.generate_content.call_args[0][0]
        assert call_args == "Question: Test"  # No context prefix
