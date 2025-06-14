"""
Tests for the BrainstormTool class.
"""

import logging
import sys
from unittest.mock import MagicMock

import pytest

from gemini_mcp.tools.brainstorm import BrainstormTool


@pytest.fixture
def mock_model_manager():
    """Fixture to mock the model manager."""
    # Create a mock model_manager module
    mock_mm = MagicMock()
    mock_mm.primary_model_name = "primary-model"
    mock_mm.generate_content.return_value = ("Default response", "primary-model")

    # Inject it into sys.modules
    sys.modules["gemini_mcp.model_manager"] = mock_mm

    yield mock_mm

    # Clean up after test
    if "gemini_mcp.model_manager" in sys.modules:
        del sys.modules["gemini_mcp.model_manager"]


class TestBrainstormTool:
    """Test the BrainstormTool class."""

    def test_name(self):
        """Test tool name property."""
        tool = BrainstormTool()
        assert tool.name == "gemini_brainstorm"

    def test_description(self):
        """Test tool description property."""
        tool = BrainstormTool()
        assert tool.description == "Brainstorm ideas or solutions with Gemini"

    def test_input_schema(self):
        """Test input schema property."""
        tool = BrainstormTool()
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert "topic" in schema["properties"]
        assert schema["properties"]["topic"]["type"] == "string"
        assert "constraints" in schema["properties"]
        assert schema["properties"]["constraints"]["type"] == "string"
        assert schema["properties"]["constraints"]["default"] == ""
        assert schema["required"] == ["topic"]

    @pytest.mark.asyncio
    async def test_execute_without_topic(self):
        """Test execution without required topic parameter."""
        tool = BrainstormTool()
        result = await tool.execute({})

        assert result.success is False
        assert result.error == "Topic is required for brainstorming"

    @pytest.mark.asyncio
    async def test_execute_with_topic_only(self, mock_model_manager):
        """Test successful execution with topic only."""
        tool = BrainstormTool()

        mock_model_manager.generate_content.return_value = (
            "Here are some brainstorming ideas...",
            "primary-model",
        )

        result = await tool.execute({"topic": "AI applications in healthcare"})

        assert result.success is True
        assert "💡 Brainstorming Results:" in result.result
        assert "Here are some brainstorming ideas..." in result.result
        assert "[Model:" not in result.result  # Primary model, no model note

        # Verify prompt was built correctly
        mock_model_manager.generate_content.assert_called_once()
        prompt = mock_model_manager.generate_content.call_args[0][0]
        assert "AI applications in healthcare" in prompt
        assert "Creative and innovative ideas" in prompt
        assert "Constraints to consider:" not in prompt  # No constraints provided

    @pytest.mark.asyncio
    async def test_execute_with_topic_and_constraints(self, mock_model_manager):
        """Test successful execution with topic and constraints."""
        tool = BrainstormTool()

        mock_model_manager.generate_content.return_value = (
            "Constrained brainstorming results...",
            "primary-model",
        )

        result = await tool.execute(
            {
                "topic": "Mobile app ideas",
                "constraints": "Must work offline and be privacy-focused",
            }
        )

        assert result.success is True
        assert "💡 Brainstorming Results:" in result.result
        assert "Constrained brainstorming results..." in result.result

        # Verify prompt includes constraints
        prompt = mock_model_manager.generate_content.call_args[0][0]
        assert "Mobile app ideas" in prompt
        assert "Constraints to consider:" in prompt
        assert "Must work offline and be privacy-focused" in prompt

    @pytest.mark.asyncio
    async def test_execute_with_fallback_model(self, mock_model_manager):
        """Test execution when fallback model is used."""
        tool = BrainstormTool()

        mock_model_manager.generate_content.return_value = (
            "Fallback model response",
            "fallback-model",
        )

        result = await tool.execute({"topic": "Test topic"})

        assert result.success is True
        assert "💡 Brainstorming Results:" in result.result
        assert "Fallback model response" in result.result
        assert "[Model: fallback-model]" in result.result  # Fallback model note

    @pytest.mark.asyncio
    async def test_execute_with_exception(self, mock_model_manager):
        """Test execution when model manager raises exception."""
        tool = BrainstormTool()

        mock_model_manager.generate_content.side_effect = Exception("API Error")

        result = await tool.execute({"topic": "Test topic"})

        assert result.success is False
        assert result.error == "Error: API Error"

    @pytest.mark.asyncio
    async def test_execute_logs_error(self, mock_model_manager, caplog):
        """Test that errors are logged."""
        tool = BrainstormTool()

        mock_model_manager.generate_content.side_effect = Exception("Test error")

        with caplog.at_level(logging.ERROR):
            await tool.execute({"topic": "Test topic"})

        assert "Gemini API error: Test error" in caplog.text

    def test_build_prompt_with_topic_only(self):
        """Test prompt building with topic only."""
        tool = BrainstormTool()
        prompt = tool._build_prompt("Climate change solutions", "")

        assert "Let's brainstorm ideas about: Climate change solutions" in prompt
        assert "Creative and innovative ideas" in prompt
        assert "Different perspectives and approaches" in prompt
        assert "Potential challenges and solutions" in prompt
        assert "Actionable next steps" in prompt
        assert "Constraints to consider:" not in prompt

    def test_build_prompt_with_constraints(self):
        """Test prompt building with constraints."""
        tool = BrainstormTool()
        prompt = tool._build_prompt("New product ideas", "Budget under $10k, target millennials")

        assert "Let's brainstorm ideas about: New product ideas" in prompt
        assert "Constraints to consider:" in prompt
        assert "Budget under $10k, target millennials" in prompt

    @pytest.mark.asyncio
    async def test_execute_with_empty_constraints(self, mock_model_manager):
        """Test that empty constraints are handled same as no constraints."""
        tool = BrainstormTool()

        mock_model_manager.generate_content.return_value = ("Response", "primary-model")

        # Reset the mock to track calls separately
        mock_model_manager.reset_mock()

        # Test with empty string
        await tool.execute({"topic": "Test", "constraints": ""})
        prompt1 = mock_model_manager.generate_content.call_args[0][0]

        # Reset between tests
        mock_model_manager.reset_mock()

        # Test with no constraints key
        await tool.execute({"topic": "Test"})
        prompt2 = mock_model_manager.generate_content.call_args[0][0]

        # Both should produce the same prompt
        assert prompt1 == prompt2
        assert "Constraints to consider:" not in prompt1
