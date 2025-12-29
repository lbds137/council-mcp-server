"""Unit tests for the ask tool."""

import sys
from unittest.mock import Mock, patch

import pytest

from council.tools.ask import AskTool


class TestAskTool:
    """Test suite for AskTool."""

    @pytest.fixture
    def tool(self):
        """Create an AskTool instance."""
        return AskTool()

    @pytest.fixture
    def mock_model_manager(self):
        """Create a mock model manager."""
        manager = Mock()
        manager.primary_model_name = "primary-model"
        manager.generate_content.return_value = ("Test response", "primary-model")
        return manager

    def test_metadata(self, tool):
        """Test tool metadata."""
        assert tool.name == "ask"
        assert "general question" in tool.description

    def test_input_schema(self, tool):
        """Test input schema definition."""
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert "question" in schema["properties"]
        assert "context" in schema["properties"]
        assert "question" in schema["required"]
        assert "context" not in schema["required"]  # Optional

    @pytest.mark.asyncio
    async def test_execute_with_question_only(self, tool, mock_model_manager, monkeypatch):
        """Test execution with just a question."""
        # Create a mock module with _server_instance instead of model_manager
        mock_council = Mock()
        mock_server_instance = Mock()
        mock_server_instance.model_manager = mock_model_manager
        mock_council._server_instance = mock_server_instance

        # Patch sys.modules to make the import work
        with patch.dict(sys.modules, {"council": mock_council}):
            parameters = {"question": "What is AI?"}
            result = await tool.execute(parameters)

            assert result.success is True
            assert "🤖 Response:" in result.result
            assert "Test response" in result.result

            # Verify model was called correctly
            mock_model_manager.generate_content.assert_called_once()
            call_args = mock_model_manager.generate_content.call_args[0][0]
            assert "Question: What is AI?" in call_args
            assert "Context:" not in call_args  # No context provided

    @pytest.mark.asyncio
    async def test_execute_with_context(self, tool, mock_model_manager):
        """Test execution with question and context."""
        mock_council = Mock()
        mock_server_instance = Mock()
        mock_server_instance.model_manager = mock_model_manager
        mock_council._server_instance = mock_server_instance

        with patch.dict(sys.modules, {"council": mock_council}):
            parameters = {"question": "What is AI?", "context": "We're discussing machine learning"}
            result = await tool.execute(parameters)

            assert result.success is True
            assert "🤖 Response:" in result.result

            # Verify prompt includes context
            call_args = mock_model_manager.generate_content.call_args[0][0]
            assert "Context: We're discussing machine learning" in call_args
            assert "Question: What is AI?" in call_args

    @pytest.mark.asyncio
    async def test_execute_without_question(self, tool, mock_model_manager):
        """Test that execution fails without a question."""
        mock_council = Mock()
        mock_server_instance = Mock()
        mock_server_instance.model_manager = mock_model_manager
        mock_council._server_instance = mock_server_instance

        with patch.dict(sys.modules, {"council": mock_council}):
            parameters = {}  # No question
            result = await tool.execute(parameters)

            assert result.success is False
            assert "Question is required" in result.error

    @pytest.mark.asyncio
    async def test_execute_without_model_manager(self, tool):
        """Test that execution fails without model manager."""
        # Create mock module without _server_instance
        mock_council = Mock()
        mock_council._server_instance = None  # No server instance

        with patch.dict(sys.modules, {"council": mock_council}):
            parameters = {"question": "Test question"}
            result = await tool.execute(parameters)

            assert result.success is False
            assert "Model manager not available" in result.error  # Updated expected error

    @pytest.mark.asyncio
    async def test_format_response_includes_model(self, tool, mock_model_manager):
        """Test response formatting includes model name."""
        mock_model_manager.generate_content.return_value = ("Response text", "test-model")

        mock_council = Mock()
        mock_server_instance = Mock()
        mock_server_instance.model_manager = mock_model_manager
        mock_council._server_instance = mock_server_instance

        with patch.dict(sys.modules, {"council": mock_council}):
            parameters = {"question": "Test"}
            result = await tool.execute(parameters)

            assert result.success is True
            # Council tools always show the model used
            assert "[Model: test-model]" in result.result
            assert "Response text" in result.result

    @pytest.mark.asyncio
    async def test_empty_context_parameter(self, tool, mock_model_manager):
        """Test that empty context parameter is handled correctly."""
        mock_council = Mock()
        mock_server_instance = Mock()
        mock_server_instance.model_manager = mock_model_manager
        mock_council._server_instance = mock_server_instance

        with patch.dict(sys.modules, {"council": mock_council}):
            parameters = {"question": "Test", "context": ""}  # Empty context
            result = await tool.execute(parameters)

            assert result.success is True
            assert "🤖 Response:" in result.result

            call_args = mock_model_manager.generate_content.call_args[0][0]
            assert call_args == "Question: Test"  # No context prefix
