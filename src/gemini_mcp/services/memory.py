"""Memory service for conversation context."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import deque
import logging

from ..models.memory import ConversationTurn, MemoryEntry

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Enhanced conversation memory with TTL and structured storage."""
    
    def __init__(self, max_turns: int = 50, max_entries: int = 100):
        self.max_turns = max_turns
        self.max_entries = max_entries
        self.turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self.entries: Dict[str, MemoryEntry] = {}
        self.created_at = datetime.now()
        self.access_count = 0
    
    def add_turn(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add a conversation turn."""
        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.turns.append(turn)
        self.access_count += 1
    
    def set(self, key: str, value: Any, category: str = "general") -> None:
        """Store a value with a key."""
        # Remove oldest entries if at capacity
        if len(self.entries) >= self.max_entries:
            oldest_key = min(self.entries.keys(), 
                           key=lambda k: self.entries[k].timestamp)
            del self.entries[oldest_key]
        
        self.entries[key] = MemoryEntry(
            key=key,
            value=value,
            category=category,
            access_count=0
        )
        self.access_count += 1
    
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key."""
        if key in self.entries:
            entry = self.entries[key]
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            self.access_count += 1
            return entry.value
        return default
    
    def get_turns(self, limit: Optional[int] = None) -> List[ConversationTurn]:
        """Get recent conversation turns."""
        if limit:
            return list(self.turns)[-limit:]
        return list(self.turns)
    
    def search_entries(self, category: Optional[str] = None) -> List[MemoryEntry]:
        """Search entries by category."""
        if category:
            return [e for e in self.entries.values() if e.category == category]
        return list(self.entries.values())
    
    def clear(self) -> None:
        """Clear all memory."""
        self.turns.clear()
        self.entries.clear()
        self.access_count = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        return {
            "turns_count": len(self.turns),
            "entries_count": len(self.entries),
            "max_turns": self.max_turns,
            "max_entries": self.max_entries,
            "total_accesses": self.access_count,
            "created_at": self.created_at.isoformat(),
            "categories": list(set(e.category for e in self.entries.values()))
        }