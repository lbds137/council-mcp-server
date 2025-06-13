"""Caching service for expensive operations."""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ResponseCache:
    """Simple LRU cache for tool responses."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def create_key(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Create a cache key from tool name and parameters."""
        # Sort parameters for consistent hashing
        params_str = json.dumps(parameters, sort_keys=True)
        key_data = f"{tool_name}:{params_str}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if it exists and isn't expired."""
        if key not in self.cache:
            self.misses += 1
            return None

        entry = self.cache[key]

        # Check if expired
        if time.time() - entry["timestamp"] > self.ttl_seconds:
            del self.cache[key]
            self.misses += 1
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        self.hits += 1
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """Set a value in cache."""
        # Remove oldest if at capacity
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)

        self.cache[key] = {"value": value, "timestamp": time.time()}

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.hits + self.misses
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total_requests if total_requests > 0 else 0,
            "ttl_seconds": self.ttl_seconds,
        }
