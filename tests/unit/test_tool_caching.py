"""Tests for which tools allow their results to be cached."""

import pytest

from council.core.registry import ToolRegistry

# Answers that depend only on the input and the model
CACHEABLE = {
    "ask",
    "brainstorm",
    "code_review",
    "debug",
    "explain",
    "refactor",
    "synthesize_perspectives",
    "test_cases",
}


@pytest.fixture(scope="module")
def tools():
    """Every tool, as discovery registers them."""
    registry = ToolRegistry()
    registry.discover_tools()
    return registry.get_all_tools()


def test_only_input_only_tools_are_cacheable(tools):
    """Test tools that read or change server state never opt in to caching."""
    cacheable = {name for name, tool in tools.items() if tool.is_cacheable({})}
    assert cacheable == CACHEABLE


def test_debug_with_a_session_is_not_cacheable(tools):
    """Test debug stops caching once it reads a conversation, which keeps changing."""
    assert tools["debug"].is_cacheable({"error_message": "boom"})
    assert not tools["debug"].is_cacheable({"error_message": "boom", "session_id": "sess_1"})
