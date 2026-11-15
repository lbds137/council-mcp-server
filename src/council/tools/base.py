"""Base class for all tools."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, float | None, str | None], None]

PRIVATE_ONLY_DESCRIPTION = (
    "When true, allow only privacy-cleared subscription CLIs (`claude`, `agy`) and the "
    "pinned OpenRouter allowlist (`anthropic`, `openai` non-oss, `google` Gemini on Vertex, "
    "`mistralai`, and Mistral-hosted `z-ai/glm-5.3`, `glm-5.3-flash`, `glm-5.2`, `glm-latest`, "
    "`glm-flash-latest`) with `allow_fallbacks=false` and `data_collection=deny`"
)

PRIVATE_ONLY_PROPERTY: dict[str, Any] = {
    "type": "boolean",
    "default": False,
    "description": PRIVATE_ONLY_DESCRIPTION,
}

# Set by the server for a call whose client asked for progress. A ContextVar,
# so it reaches the tool's asyncio tasks and worker threads without plumbing.
_progress_callback: ContextVar[ProgressCallback | None] = ContextVar(
    "progress_callback", default=None
)


@contextmanager
def progress_reporter(callback: ProgressCallback) -> Iterator[None]:
    """Route report_progress calls made inside this block to callback."""
    token = _progress_callback.set(callback)
    try:
        yield
    finally:
        _progress_callback.reset(token)


def report_progress(progress: float, total: float | None = None, message: str | None = None):
    """Tell the client how far a long tool has got; does nothing if it didn't ask.

    progress must increase from one report to the next within a call.
    """
    callback = _progress_callback.get()
    if callback is None:
        return
    try:
        callback(progress, total, message)
    except Exception as e:
        # Progress is a courtesy: losing a report must not lose the tool's work
        logger.warning(f"Progress report not sent: {e}")


def get_server() -> Any:
    """The running CouncilMCPServer, or None before it starts."""
    # Looked up at call time: main.py (and the tests) set council._server_instance
    import council

    return council._server_instance


def get_model_manager() -> Any:
    """The running server's model manager, or None before it is ready."""
    server = get_server()
    return server.model_manager if server else None


def parse_private_only(parameters: dict[str, Any]) -> tuple[bool, str | None]:
    """Extract and validate optional `private_only` boolean parameter."""
    raw = parameters.get("private_only", False)
    if not isinstance(raw, bool):
        return False, "private_only must be a boolean"
    return raw, None


def build_generation_kwargs(
    model_override: str | None, *, private_only: bool = False
) -> dict[str, Any]:
    """Build keyword arguments for `model_manager.generate_content(...)`."""
    kwargs: dict[str, Any] = {"model": model_override}
    if private_only:
        kwargs["private_only"] = True
    return kwargs


class ToolOutput:
    """Standard output format for tool execution."""

    def __init__(self, success: bool, result: str | None = None, error: str | None = None):
        self.success = success
        self.result = result
        self.error = error
        self.metadata: dict[str, Any] = {}
        # Add missing attributes for compatibility with orchestrator
        self.tool_name: str = ""
        self.execution_time_ms: float | None = None
        self.model_used: str | None = None
        self.timestamp = None


class MCPTool(ABC):
    """Abstract base class for all tools using simplified property-based approach."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the tool description."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool inputs."""
        pass

    @abstractmethod
    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        pass

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """Whether a successful result may be served again for the same input.

        Only tools whose answer depends on nothing but their input and the
        model opt in. A tool that reads or changes server state must not.
        """
        return False

    def get_mcp_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
