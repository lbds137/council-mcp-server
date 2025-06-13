"""Unit tests for the cache service."""

import time
from unittest.mock import patch

import pytest

from gemini_mcp.services.cache import ResponseCache


class TestResponseCache:
    """Test suite for ResponseCache."""

    def test_init(self):
        """Test cache initialization."""
        cache = ResponseCache(max_size=50, ttl_seconds=600)
        assert cache.max_size == 50
        assert cache.ttl_seconds == 600
        assert len(cache.cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_create_key(self):
        """Test cache key creation."""
        cache = ResponseCache()

        # Same inputs should produce same key
        key1 = cache.create_key("test_tool", {"param": "value"})
        key2 = cache.create_key("test_tool", {"param": "value"})
        assert key1 == key2

        # Different inputs should produce different keys
        key3 = cache.create_key("test_tool", {"param": "different"})
        assert key1 != key3

        # Order shouldn't matter for parameters
        key4 = cache.create_key("test_tool", {"a": 1, "b": 2})
        key5 = cache.create_key("test_tool", {"b": 2, "a": 1})
        assert key4 == key5

    def test_set_and_get(self):
        """Test setting and getting values."""
        cache = ResponseCache()
        key = cache.create_key("test", {})

        # Set a value
        cache.set(key, "test_value")
        assert len(cache.cache) == 1

        # Get the value
        value = cache.get(key)
        assert value == "test_value"
        assert cache.hits == 1
        assert cache.misses == 0

    def test_cache_miss(self):
        """Test cache miss."""
        cache = ResponseCache()
        key = cache.create_key("test", {})

        value = cache.get(key)
        assert value is None
        assert cache.hits == 0
        assert cache.misses == 1

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = ResponseCache(max_size=3)

        # Fill cache
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert len(cache.cache) == 3

        # Access key1 to make it recently used
        cache.get("key1")

        # Add new key, should evict key2 (least recently used)
        cache.set("key4", "value4")
        assert len(cache.cache) == 3
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key1") == "value1"  # Still there
        assert cache.get("key3") == "value3"  # Still there
        assert cache.get("key4") == "value4"  # New entry

    @patch("time.time")
    def test_ttl_expiration(self, mock_time):
        """Test TTL expiration."""
        cache = ResponseCache(ttl_seconds=60)

        # Set current time
        mock_time.return_value = 1000

        # Set a value
        key = cache.create_key("test", {})
        cache.set(key, "test_value")

        # Value should be retrievable immediately
        assert cache.get(key) == "test_value"

        # Fast forward time past TTL
        mock_time.return_value = 1061  # 61 seconds later

        # Value should be expired
        value = cache.get(key)
        assert value is None
        assert len(cache.cache) == 0  # Expired entry removed

    def test_clear(self):
        """Test clearing the cache."""
        cache = ResponseCache()

        # Add some entries
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")  # Generate a hit
        cache.get("key3")  # Generate a miss

        # Clear cache
        cache.clear()

        assert len(cache.cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_get_stats(self):
        """Test getting cache statistics."""
        cache = ResponseCache(max_size=10, ttl_seconds=300)

        # Generate some activity
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")  # Hit
        cache.get("key2")  # Hit
        cache.get("key3")  # Miss

        stats = cache.get_stats()

        assert stats["size"] == 2
        assert stats["max_size"] == 10
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2 / 3
        assert stats["ttl_seconds"] == 300

    def test_move_to_end_on_access(self):
        """Test that accessing an item moves it to end (most recent)."""
        cache = ResponseCache(max_size=3)

        # Add three items
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to move it to end
        cache.get("key1")

        # Add a fourth item - should evict key2, not key1
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still present
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Still present
        assert cache.get("key4") == "value4"  # New item
