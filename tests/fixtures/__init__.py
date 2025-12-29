"""Test fixtures for the Council MCP server tests."""

from dataclasses import dataclass, field
from typing import List
from unittest.mock import Mock


@dataclass
class ToolMetadata:
    """Test-only tool metadata."""

    name: str
    description: str
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)


def create_mock_model_manager():
    """Create a mock model manager for testing."""
    mock_manager = Mock()
    mock_manager.primary_model_name = "test-primary-model"
    mock_manager.fallback_model_name = "test-fallback-model"
    mock_manager.generate_content = Mock(return_value=("Test response", "test-primary-model"))
    mock_manager.get_status = Mock(
        return_value={
            "primary": {"name": "test-primary-model", "available": True},
            "fallback": {"name": "test-fallback-model", "available": True},
            "timeout": 10.0,
        }
    )
    mock_manager.get_stats = Mock(
        return_value={
            "total_calls": 10,
            "primary_success_rate": 0.9,
            "fallback_success_rate": 0.8,
            "fallback_usage_rate": 0.1,
            "raw_stats": {},
        }
    )
    return mock_manager


def create_test_tool_metadata(name: str = "test_tool") -> ToolMetadata:
    """Create test tool metadata."""
    return ToolMetadata(name=name, description=f"Test tool {name}", version="1.0.0", tags=["test"])


class MockTool:
    """Mock tool for testing."""

    def __init__(self, name: str = "mock_tool", should_fail: bool = False):
        self.metadata = create_test_tool_metadata(name)
        self.should_fail = should_fail
        self.execute_count = 0

    async def _execute(self, input_data):
        self.execute_count += 1
        if self.should_fail:
            raise Exception("Mock tool failed")
        return f"Mock result for {input_data.parameters}"

    def get_mcp_definition(self):
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "inputSchema": {"type": "object", "properties": {}},
        }
