"""Base models for tools and responses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ToolMetadata:
    """Metadata for a tool."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = "gemini-mcp"
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolInput:
    """Base class for tool inputs."""

    tool_name: str
    parameters: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolOutput:
    """Base class for tool outputs."""

    tool_name: str
    result: Any
    success: bool = True
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[float] = None
    model_used: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
