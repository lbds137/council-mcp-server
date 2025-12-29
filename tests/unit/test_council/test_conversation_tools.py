"""Tests for conversation tools."""

import pytest

from council.tools.conversation import (
    ContinueConversationTool,
    EndConversationTool,
    GetConversationHistoryTool,
    ListConversationsTool,
    StartConversationTool,
    get_session_manager,
)


class TestGetSessionManager:
    """Tests for get_session_manager function."""

    def test_get_session_manager_creates_instance(self):
        """Test that get_session_manager creates a singleton."""
        # Reset the global
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        manager = get_session_manager()

        assert manager is not None
        # Calling again should return same instance
        manager2 = get_session_manager()
        assert manager is manager2


class TestStartConversationTool:
    """Tests for StartConversationTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return StartConversationTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "start_conversation"

    def test_description(self, tool):
        """Test tool description."""
        assert "multi-turn" in tool.description.lower()
        assert "session" in tool.description.lower()

    def test_input_schema_structure(self, tool):
        """Test input schema structure."""
        schema = tool.input_schema

        assert schema["type"] == "object"
        assert "model" in schema["properties"]
        assert "system_prompt" in schema["properties"]
        assert "initial_message" in schema["properties"]
        assert schema["required"] == ["model"]

    @pytest.mark.asyncio
    async def test_execute_creates_session(self, tool):
        """Test execute creates a new session."""
        # Reset session manager
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = await tool.execute({"model": "google/gemini-3-pro-preview"})

        assert result.success is True
        assert "Session ID" in result.result
        assert "sess_" in result.result
        assert "google/gemini-3-pro-preview" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_system_prompt(self, tool):
        """Test execute with system prompt."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = await tool.execute(
            {
                "model": "test-model",
                "system_prompt": "You are a Python expert",
            }
        )

        assert result.success is True
        assert "System Prompt" in result.result

    @pytest.mark.asyncio
    async def test_execute_without_model(self, tool):
        """Test execute fails without model."""
        result = await tool.execute({})

        assert result.success is False
        assert "required" in result.error.lower()


class TestContinueConversationTool:
    """Tests for ContinueConversationTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return ContinueConversationTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "continue_conversation"

    def test_description(self, tool):
        """Test tool description."""
        assert "existing" in tool.description.lower()
        assert "context" in tool.description.lower()

    def test_input_schema(self, tool):
        """Test input schema."""
        schema = tool.input_schema

        assert "session_id" in schema["properties"]
        assert "message" in schema["properties"]
        assert "session_id" in schema["required"]
        assert "message" in schema["required"]

    @pytest.mark.asyncio
    async def test_execute_without_session_id(self, tool):
        """Test execute fails without session_id."""
        result = await tool.execute({"message": "Hello"})

        assert result.success is False
        assert "session_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_without_message(self, tool):
        """Test execute fails without message."""
        result = await tool.execute({"session_id": "sess_test123"})

        assert result.success is False
        assert "message" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_session_not_found(self, tool):
        """Test execute with non-existent session."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = await tool.execute(
            {
                "session_id": "sess_nonexistent",
                "message": "Hello",
            }
        )

        assert result.success is False
        assert "not found" in result.error.lower()


class TestListConversationsTool:
    """Tests for ListConversationsTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return ListConversationsTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "list_conversations"

    def test_description(self, tool):
        """Test tool description."""
        assert "list" in tool.description.lower()
        assert "active" in tool.description.lower()

    def test_input_schema(self, tool):
        """Test input schema has no required params."""
        schema = tool.input_schema

        assert schema["required"] == []

    @pytest.mark.asyncio
    async def test_execute_empty(self, tool):
        """Test execute with no sessions."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = await tool.execute({})

        assert result.success is True
        assert "No active conversations" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_sessions(self, tool):
        """Test execute with existing sessions."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        # Create a session first
        start_tool = StartConversationTool()
        await start_tool.execute({"model": "test-model"})

        result = await tool.execute({})

        assert result.success is True
        assert "Active Conversations" in result.result
        assert "test-model" in result.result


class TestEndConversationTool:
    """Tests for EndConversationTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return EndConversationTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "end_conversation"

    def test_description(self, tool):
        """Test tool description."""
        assert "end" in tool.description.lower()

    def test_input_schema(self, tool):
        """Test input schema."""
        schema = tool.input_schema

        assert "session_id" in schema["properties"]
        assert "summarize" in schema["properties"]
        assert schema["properties"]["summarize"]["default"] is True
        assert schema["required"] == ["session_id"]

    @pytest.mark.asyncio
    async def test_execute_without_session_id(self, tool):
        """Test execute fails without session_id."""
        result = await tool.execute({})

        assert result.success is False
        assert "session_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_session_not_found(self, tool):
        """Test execute with non-existent session."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = await tool.execute({"session_id": "sess_nonexistent"})

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Test successfully ending a session."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        # Create session first
        start_tool = StartConversationTool()
        start_result = await start_tool.execute({"model": "test-model"})

        # Extract session ID from result
        import re

        match = re.search(r"sess_[a-f0-9]+", start_result.result)
        session_id = match.group(0)

        # End the session
        result = await tool.execute(
            {
                "session_id": session_id,
                "summarize": False,
            }
        )

        assert result.success is True
        assert "Ended" in result.result


class TestGetConversationHistoryTool:
    """Tests for GetConversationHistoryTool."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GetConversationHistoryTool()

    def test_name(self, tool):
        """Test tool name."""
        assert tool.name == "get_conversation_history"

    def test_description(self, tool):
        """Test tool description."""
        assert "history" in tool.description.lower()

    def test_input_schema(self, tool):
        """Test input schema."""
        schema = tool.input_schema

        assert "session_id" in schema["properties"]
        assert "limit" in schema["properties"]
        assert schema["required"] == ["session_id"]

    @pytest.mark.asyncio
    async def test_execute_without_session_id(self, tool):
        """Test execute fails without session_id."""
        result = await tool.execute({})

        assert result.success is False
        assert "session_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_session_not_found(self, tool):
        """Test execute with non-existent session."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        result = await tool.execute({"session_id": "sess_nonexistent"})

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Test getting history for existing session."""
        import council.tools.conversation as conv_module

        conv_module._session_manager = None

        # Create session with system prompt
        start_tool = StartConversationTool()
        start_result = await start_tool.execute(
            {
                "model": "test-model",
                "system_prompt": "You are helpful",
            }
        )

        # Extract session ID
        import re

        match = re.search(r"sess_[a-f0-9]+", start_result.result)
        session_id = match.group(0)

        result = await tool.execute({"session_id": session_id})

        assert result.success is True
        assert "History" in result.result
        assert "test-model" in result.result
