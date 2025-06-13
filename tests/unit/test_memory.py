"""Unit tests for the memory service."""

from datetime import datetime
from unittest.mock import patch

from gemini_mcp.services.memory import ConversationMemory


class TestConversationMemory:
    """Test suite for ConversationMemory."""

    def test_init(self):
        """Test memory initialization."""
        memory = ConversationMemory(max_turns=30, max_entries=50)
        assert memory.max_turns == 30
        assert memory.max_entries == 50
        assert len(memory.turns) == 0
        assert len(memory.entries) == 0
        assert memory.access_count == 0
        assert isinstance(memory.created_at, datetime)

    def test_add_turn(self):
        """Test adding conversation turns."""
        memory = ConversationMemory()

        # Add a turn
        memory.add_turn("user", "Hello", {"intent": "greeting"})
        assert len(memory.turns) == 1
        assert memory.access_count == 1

        turn = memory.turns[0]
        assert turn.role == "user"
        assert turn.content == "Hello"
        assert turn.metadata["intent"] == "greeting"

    def test_max_turns_limit(self):
        """Test that turns are limited by max_turns."""
        memory = ConversationMemory(max_turns=3)

        # Add more than max turns
        for i in range(5):
            memory.add_turn("user", f"Message {i}")

        # Should only keep last 3
        assert len(memory.turns) == 3
        turns = list(memory.turns)
        assert turns[0].content == "Message 2"
        assert turns[1].content == "Message 3"
        assert turns[2].content == "Message 4"

    def test_set_and_get_entry(self):
        """Test setting and getting memory entries."""
        memory = ConversationMemory()

        # Set an entry
        memory.set("user_name", "Alice", category="user_info")
        assert len(memory.entries) == 1

        # Get the entry
        value = memory.get("user_name")
        assert value == "Alice"
        assert memory.access_count == 2  # One for set, one for get

        # Get with default
        assert memory.get("non_existent", "default") == "default"

    def test_max_entries_limit(self):
        """Test that entries are limited by max_entries."""
        memory = ConversationMemory(max_entries=3)

        # Add entries with controlled timestamps
        with patch("gemini_mcp.models.memory.datetime") as mock_dt:
            base_time = datetime(2024, 1, 1, 12, 0, 0)

            # Add 4 entries with different timestamps
            for i in range(4):
                mock_dt.now.return_value = base_time.replace(minute=i)
                memory.set(f"key{i}", f"value{i}")

        # Should only keep 3 entries, oldest removed
        assert len(memory.entries) == 3
        assert memory.get("key0") is None  # Oldest, removed
        assert memory.get("key1") == "value1"
        assert memory.get("key2") == "value2"
        assert memory.get("key3") == "value3"

    def test_get_turns(self):
        """Test getting conversation turns."""
        memory = ConversationMemory()

        # Add some turns
        memory.add_turn("user", "First")
        memory.add_turn("assistant", "Second")
        memory.add_turn("user", "Third")

        # Get all turns
        turns = memory.get_turns()
        assert len(turns) == 3
        assert turns[0].content == "First"

        # Get limited turns
        recent = memory.get_turns(limit=2)
        assert len(recent) == 2
        assert recent[0].content == "Second"
        assert recent[1].content == "Third"

    def test_search_entries_by_category(self):
        """Test searching entries by category."""
        memory = ConversationMemory()

        # Add entries with different categories
        memory.set("name", "Alice", category="user")
        memory.set("age", 30, category="user")
        memory.set("topic", "AI", category="context")
        memory.set("model", "GPT-4", category="system")

        # Search by category
        user_entries = memory.search_entries(category="user")
        assert len(user_entries) == 2
        assert all(e.category == "user" for e in user_entries)

        # Search all
        all_entries = memory.search_entries()
        assert len(all_entries) == 4

    def test_entry_access_tracking(self):
        """Test that entry access is tracked."""
        memory = ConversationMemory()

        # Set an entry
        memory.set("test_key", "test_value")
        entry = memory.entries["test_key"]
        initial_time = entry.last_accessed
        assert entry.access_count == 0

        # Access it
        with patch("gemini_mcp.models.memory.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 13, 0, 0)
            memory.get("test_key")

        # Check access was tracked
        assert entry.access_count == 1
        assert entry.last_accessed > initial_time

    def test_clear(self):
        """Test clearing memory."""
        memory = ConversationMemory()

        # Add data
        memory.add_turn("user", "Hello")
        memory.set("key", "value")
        memory.access_count = 10

        # Clear
        memory.clear()

        assert len(memory.turns) == 0
        assert len(memory.entries) == 0
        assert memory.access_count == 0

    def test_get_stats(self):
        """Test getting memory statistics."""
        memory = ConversationMemory(max_turns=10, max_entries=20)

        # Add some data
        memory.add_turn("user", "Hello")
        memory.add_turn("assistant", "Hi")
        memory.set("name", "Alice", category="user")
        memory.set("topic", "AI", category="context")

        stats = memory.get_stats()

        assert stats["turns_count"] == 2
        assert stats["entries_count"] == 2
        assert stats["max_turns"] == 10
        assert stats["max_entries"] == 20
        assert stats["total_accesses"] == 4  # 2 turns + 2 entries
        assert set(stats["categories"]) == {"user", "context"}
        assert "created_at" in stats
