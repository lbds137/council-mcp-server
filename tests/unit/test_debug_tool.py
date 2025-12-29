"""Tests for DebugTool."""

from unittest.mock import Mock, patch

import pytest

from council.tools.debug import DebugTool


class TestDebugTool:
    """Tests for DebugTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return DebugTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "debug"

    def test_description(self, tool):
        """Test tool description."""
        assert "debug" in tool.description.lower() or "error" in tool.description.lower()
        assert "hypothesis" in tool.description.lower()

    def test_input_schema_structure(self, tool):
        """Test input schema structure."""
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert "error_message" in schema["properties"]
        assert "code_context" in schema["properties"]
        assert "stack_trace" in schema["properties"]
        assert "previous_attempts" in schema["properties"]
        assert "environment" in schema["properties"]
        assert "session_id" in schema["properties"]
        assert "model" in schema["properties"]

    def test_required_parameters(self, tool):
        """Test required parameters."""
        schema = tool.input_schema

        assert "error_message" in schema["required"]
        assert "code_context" in schema["required"]

    def test_previous_attempts_is_array(self, tool):
        """Test previous_attempts is an array type."""
        schema = tool.input_schema

        assert schema["properties"]["previous_attempts"]["type"] == "array"
        assert schema["properties"]["previous_attempts"]["items"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_execute_without_error_message(self, tool):
        """Test execute fails without error_message."""
        result = await tool.execute(
            {
                "code_context": "def foo(): pass",
            }
        )

        assert result.success is False
        assert "error_message" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_without_code_context(self, tool):
        """Test execute fails without code_context."""
        result = await tool.execute(
            {
                "error_message": "NameError: name 'x' is not defined",
            }
        )

        assert result.success is False
        assert "code_context" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Test successful debug execution."""
        mock_response = (
            "### Root Cause Analysis\nVariable x is not defined.\n\n"
            "### Hypotheses\n1. **Missing import** (Confidence: High)",
            "google/gemini-3-pro-preview",
        )

        mock_manager = Mock()
        mock_manager.generate_content.return_value = mock_response

        with patch("council._server_instance") as mock_server:
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "error_message": "NameError: name 'x' is not defined",
                    "code_context": "print(x)",
                }
            )

        assert result.success is True
        assert "Debugging Analysis" in result.result
        assert "Root Cause" in result.result or "gemini" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_previous_attempts(self, tool):
        """Test debug with previous attempts."""
        mock_response = ("Analysis result", "test-model")

        with patch("council._server_instance") as mock_server:
            mock_manager = Mock()
            mock_manager.generate_content.return_value = mock_response
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "error_message": "TypeError",
                    "code_context": "a + b",
                    "previous_attempts": [
                        "Tried converting a to string",
                        "Tried converting b to string",
                    ],
                }
            )

        assert result.success is True
        assert "Attempt #3" in result.result  # previous_attempts count + 1

    @pytest.mark.asyncio
    async def test_execute_with_stack_trace(self, tool):
        """Test debug with stack trace."""
        mock_response = ("Analysis with trace", "test-model")

        with patch("council._server_instance") as mock_server:
            mock_manager = Mock()
            mock_manager.generate_content.return_value = mock_response
            mock_server.model_manager = mock_manager

            result = await tool.execute(
                {
                    "error_message": "ImportError",
                    "code_context": "import nonexistent",
                    "stack_trace": "Traceback:\n  File test.py line 1\n    import nonexistent",
                }
            )

        assert result.success is True

    def test_build_prompt_basic(self, tool):
        """Test prompt building with basic inputs."""
        prompt = tool._build_prompt(
            error_message="NameError",
            code_context="print(x)",
            stack_trace="",
            previous_attempts=[],
            environment="Python 3.13",
            session_context="",
        )

        assert "NameError" in prompt
        assert "print(x)" in prompt
        assert "Python 3.13" in prompt
        assert "Root Cause Analysis" in prompt
        assert "Hypotheses" in prompt

    def test_build_prompt_with_stack_trace(self, tool):
        """Test prompt includes stack trace when provided."""
        prompt = tool._build_prompt(
            error_message="Error",
            code_context="code",
            stack_trace="Traceback: line 42",
            previous_attempts=[],
            environment="Python 3.x",
            session_context="",
        )

        assert "Stack Trace" in prompt
        assert "Traceback: line 42" in prompt

    def test_build_prompt_with_previous_attempts(self, tool):
        """Test prompt includes previous attempts warning."""
        prompt = tool._build_prompt(
            error_message="Error",
            code_context="code",
            stack_trace="",
            previous_attempts=["Tried A", "Tried B"],
            environment="Python 3.x",
            session_context="",
        )

        assert "Previous Attempts" in prompt
        assert "Tried A" in prompt
        assert "Tried B" in prompt
        assert "NOT suggest these approaches" in prompt

    def test_build_prompt_with_session_context(self, tool):
        """Test prompt includes session context."""
        prompt = tool._build_prompt(
            error_message="Error",
            code_context="code",
            stack_trace="",
            previous_attempts=[],
            environment="Python 3.x",
            session_context="## Previous Debugging Context\nPrevious analysis...",
        )

        assert "Previous Debugging Context" in prompt
        assert "Previous analysis" in prompt

    def test_format_response_basic(self, tool):
        """Test response formatting."""
        formatted = tool._format_response(
            response_text="Analysis result",
            model_used="test-model",
            session_id=None,
            attempt_count=0,
        )

        assert "Debugging Analysis" in formatted
        assert "Analysis result" in formatted
        assert "test-model" in formatted

    def test_format_response_with_session(self, tool):
        """Test response formatting with session ID."""
        formatted = tool._format_response(
            response_text="Analysis",
            model_used="test-model",
            session_id="sess_abc123",
            attempt_count=0,
        )

        assert "sess_abc123" in formatted

    def test_format_response_with_attempts(self, tool):
        """Test response formatting shows attempt number."""
        formatted = tool._format_response(
            response_text="Analysis",
            model_used="test-model",
            session_id=None,
            attempt_count=2,
        )

        assert "Attempt #3" in formatted  # 2 previous + this one = 3

    def test_get_mcp_definition(self, tool):
        """Test MCP definition generation."""
        definition = tool.get_mcp_definition()

        assert definition["name"] == "debug"
        assert "description" in definition
        assert "inputSchema" in definition


class TestDebugToolSessionIntegration:
    """Tests for debug tool session integration."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return DebugTool()

    def test_get_session_context_no_session(self, tool):
        """Test _get_session_context with no session."""
        # Reset session manager
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = tool._get_session_context("sess_nonexistent")

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_session_context_with_session(self, tool):
        """Test _get_session_context with existing session."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        # Create a session with some turns
        from council.tools.conversation import StartConversationTool, get_session_manager

        start_tool = StartConversationTool()
        await start_tool.execute({"model": "test-model"})

        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()
        session_id = sessions[0]["session_id"]

        # Add some turns manually
        session = session_manager.get_session(session_id)
        session.add_turn("user", "Debug question 1")
        session.add_turn("assistant", "Analysis response 1")

        # Get context
        result = tool._get_session_context(session_id)

        assert "Previous Debugging Context" in result
        assert "Debug question 1" in result
