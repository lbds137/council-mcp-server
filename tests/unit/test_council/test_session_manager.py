"""Tests for SessionManager."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from council.services.session_manager import (
    ConversationSession,
    ConversationTurn,
    SessionManager,
)


class TestConversationTurn:
    """Tests for ConversationTurn dataclass."""

    def test_create_user_turn(self):
        """Test creating a user turn."""
        turn = ConversationTurn(role="user", content="Hello")

        assert turn.role == "user"
        assert turn.content == "Hello"
        assert isinstance(turn.timestamp, datetime)

    def test_create_assistant_turn(self):
        """Test creating an assistant turn."""
        turn = ConversationTurn(role="assistant", content="Hi there!")

        assert turn.role == "assistant"
        assert turn.content == "Hi there!"


class TestConversationSession:
    """Tests for ConversationSession dataclass."""

    def test_create_session(self):
        """Test creating a session."""
        session = ConversationSession(
            session_id="sess_test123",
            model="google/gemini-3-pro-preview",
            system_prompt="You are helpful.",
        )

        assert session.session_id == "sess_test123"
        assert session.model == "google/gemini-3-pro-preview"
        assert session.system_prompt == "You are helpful."
        assert session.turns == []
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_activity, datetime)

    def test_add_turn(self):
        """Test adding turns to a session."""
        session = ConversationSession(
            session_id="sess_test",
            model="test-model",
            system_prompt="",
        )

        session.add_turn("user", "Hello")
        session.add_turn("assistant", "Hi!")

        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].content == "Hello"
        assert session.turns[1].role == "assistant"
        assert session.turns[1].content == "Hi!"

    def test_add_turn_updates_last_activity(self):
        """Test that add_turn updates last_activity."""
        session = ConversationSession(
            session_id="sess_test",
            model="test-model",
            system_prompt="",
        )
        original_activity = session.last_activity

        session.add_turn("user", "Test")

        assert session.last_activity >= original_activity

    def test_get_message_history_empty(self):
        """Test message history with no turns."""
        session = ConversationSession(
            session_id="sess_test",
            model="test-model",
            system_prompt="",
        )

        history = session.get_message_history()

        assert history == []

    def test_get_message_history_with_system_prompt(self):
        """Test message history includes system prompt."""
        session = ConversationSession(
            session_id="sess_test",
            model="test-model",
            system_prompt="You are a Python expert.",
        )
        session.add_turn("user", "Hello")

        history = session.get_message_history()

        assert len(history) == 2
        assert history[0] == {"role": "system", "content": "You are a Python expert."}
        assert history[1] == {"role": "user", "content": "Hello"}

    def test_get_message_history_multiple_turns(self):
        """Test message history with multiple turns."""
        session = ConversationSession(
            session_id="sess_test",
            model="test-model",
            system_prompt="",
        )
        session.add_turn("user", "Question 1")
        session.add_turn("assistant", "Answer 1")
        session.add_turn("user", "Question 2")
        session.add_turn("assistant", "Answer 2")

        history = session.get_message_history()

        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[3]["role"] == "assistant"

    def test_get_summary(self):
        """Test session summary."""
        session = ConversationSession(
            session_id="sess_test",
            model="google/gemini-3-pro-preview",
            system_prompt="",
        )
        session.add_turn("user", "This is my first message to the AI")
        session.add_turn("assistant", "This is the response")

        summary = session.get_summary()

        assert "google/gemini-3-pro-preview" in summary
        assert "2 turns" in summary
        assert "This is my first message" in summary

    def test_get_summary_empty_session(self):
        """Test summary for empty session."""
        session = ConversationSession(
            session_id="sess_test",
            model="test-model",
            system_prompt="",
        )

        summary = session.get_summary()

        assert "No messages" in summary


class TestSessionManager:
    """Tests for SessionManager."""

    def test_init_defaults(self):
        """Test default initialization."""
        manager = SessionManager()

        assert manager.max_sessions == 20
        assert manager.max_turns_per_session == 50
        assert len(manager.sessions) == 0

    def test_init_custom_limits(self):
        """Test custom limits."""
        manager = SessionManager(max_sessions=5, max_turns_per_session=10)

        assert manager.max_sessions == 5
        assert manager.max_turns_per_session == 10

    def test_create_session(self):
        """Test creating a session."""
        manager = SessionManager()

        session_id = manager.create_session(
            model="google/gemini-3-pro-preview",
            system_prompt="You are helpful.",
        )

        assert session_id.startswith("sess_")
        assert len(session_id) == 17  # "sess_" + 12 hex chars
        assert session_id in manager.sessions
        assert manager.sessions[session_id].model == "google/gemini-3-pro-preview"
        assert manager.sessions[session_id].system_prompt == "You are helpful."

    def test_create_session_with_metadata(self):
        """Test creating session with metadata."""
        manager = SessionManager()

        session_id = manager.create_session(
            model="test-model",
            metadata={"purpose": "testing"},
        )

        assert manager.sessions[session_id].metadata == {"purpose": "testing"}

    def test_create_session_cleanup_oldest(self):
        """Test that oldest session is removed when at capacity."""
        manager = SessionManager(max_sessions=2)

        # Create first session
        id1 = manager.create_session(model="model-1")
        # Create second session
        id2 = manager.create_session(model="model-2")

        # Verify both exist
        assert len(manager.sessions) == 2

        # Create third session - should remove oldest
        id3 = manager.create_session(model="model-3")

        assert len(manager.sessions) == 2
        assert id1 not in manager.sessions  # Oldest removed
        assert id2 in manager.sessions
        assert id3 in manager.sessions

    def test_get_session_exists(self):
        """Test getting existing session."""
        manager = SessionManager()
        session_id = manager.create_session(model="test-model")

        session = manager.get_session(session_id)

        assert session is not None
        assert session.session_id == session_id

    def test_get_session_not_exists(self):
        """Test getting non-existent session."""
        manager = SessionManager()

        session = manager.get_session("sess_nonexistent")

        assert session is None

    def test_send_message_success(self):
        """Test sending a message in session."""
        manager = SessionManager()
        session_id = manager.create_session(model="test-model")

        mock_manager = Mock()
        mock_manager.generate_content.return_value = ("Test response", "test-model")

        response, model = manager.send_message(session_id, "Hello", mock_manager)

        assert response == "Test response"
        assert model == "test-model"
        assert len(manager.sessions[session_id].turns) == 2
        assert manager.sessions[session_id].turns[0].role == "user"
        assert manager.sessions[session_id].turns[1].role == "assistant"

    def test_send_message_session_not_found(self):
        """Test sending message to non-existent session."""
        manager = SessionManager()
        mock_manager = Mock()

        with pytest.raises(ValueError, match="not found"):
            manager.send_message("sess_invalid", "Hello", mock_manager)

    def test_send_message_turn_limit_exceeded(self):
        """Test that turn limit is enforced."""
        manager = SessionManager(max_turns_per_session=2)
        session_id = manager.create_session(model="test-model")

        mock_manager = Mock()
        mock_manager.generate_content.return_value = ("Response", "test-model")

        # Send first message (creates 2 turns: user + assistant)
        manager.send_message(session_id, "Message 1", mock_manager)

        # Second message should fail (already at 2 turns)
        with pytest.raises(ValueError, match="maximum"):
            manager.send_message(session_id, "Message 2", mock_manager)

    def test_list_sessions_empty(self):
        """Test listing sessions when empty."""
        manager = SessionManager()

        sessions = manager.list_sessions()

        assert sessions == []

    def test_list_sessions_multiple(self):
        """Test listing multiple sessions."""
        manager = SessionManager()
        manager.create_session(model="model-1")
        manager.create_session(model="model-2")

        sessions = manager.list_sessions()

        assert len(sessions) == 2
        # Sessions should be sorted by last_activity (most recent first)
        assert all("session_id" in s for s in sessions)
        assert all("model" in s for s in sessions)
        assert all("turns" in s for s in sessions)

    def test_get_history_success(self):
        """Test getting conversation history."""
        manager = SessionManager()
        session_id = manager.create_session(model="test-model")

        mock_manager = Mock()
        mock_manager.generate_content.return_value = ("Response", "test-model")
        manager.send_message(session_id, "Hello", mock_manager)

        history = manager.get_history(session_id)

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"

    def test_get_history_with_limit(self):
        """Test getting limited history."""
        manager = SessionManager()
        session_id = manager.create_session(model="test-model")

        mock_manager = Mock()
        mock_manager.generate_content.return_value = ("Response", "test-model")
        manager.send_message(session_id, "Message 1", mock_manager)
        manager.send_message(session_id, "Message 2", mock_manager)

        history = manager.get_history(session_id, limit=2)

        assert len(history) == 2  # Last 2 turns only

    def test_get_history_session_not_found(self):
        """Test getting history for non-existent session."""
        manager = SessionManager()

        with pytest.raises(ValueError, match="not found"):
            manager.get_history("sess_invalid")

    def test_end_session_simple(self):
        """Test ending session without summary."""
        manager = SessionManager()
        session_id = manager.create_session(model="test-model")

        result = manager.end_session(session_id, summarize=False)

        assert session_id not in manager.sessions
        assert "ended" in result.lower()

    def test_end_session_with_summary(self):
        """Test ending session with summary."""
        manager = SessionManager()
        session_id = manager.create_session(model="test-model")
        manager.sessions[session_id].add_turn("user", "Hello")
        manager.sessions[session_id].add_turn("assistant", "Hi!")

        result = manager.end_session(session_id, summarize=True)

        assert session_id not in manager.sessions
        assert "test-model" in result
        assert "2 turns" in result

    def test_end_session_not_found(self):
        """Test ending non-existent session."""
        manager = SessionManager()

        with pytest.raises(ValueError, match="not found"):
            manager.end_session("sess_invalid")

    def test_get_stats(self):
        """Test getting manager stats."""
        manager = SessionManager(max_sessions=10, max_turns_per_session=25)
        manager.create_session(model="model-1")
        manager.sessions[list(manager.sessions.keys())[0]].add_turn("user", "Hello")

        stats = manager.get_stats()

        assert stats["active_sessions"] == 1
        assert stats["max_sessions"] == 10
        assert stats["total_turns"] == 1
        assert stats["max_turns_per_session"] == 25
