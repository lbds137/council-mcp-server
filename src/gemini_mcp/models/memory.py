"""Memory-related data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ConversationTurn:
    """Represents a single turn in a conversation."""
    
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEntry:
    """Represents an entry in conversation memory."""
    
    key: str
    value: Any
    category: str = "general"
    timestamp: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0