#!/usr/bin/env python3
"""
Gemini MCP Server v3.0.0 - Single File Bundle
A Model Context Protocol server that enables Claude to collaborate with Google's Gemini AI models.
This version combines all modular components into a single deployable file.
"""

# import asyncio  # Not used in bundled version
# import collections  # Not used in bundled version
import hashlib
import importlib
import inspect
import json
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("gemini-mcp-v3")

__version__ = "3.0.0"

# Global model manager instance (will be set by server)
model_manager = None


# ========== JSON-RPC 2.0 server implementation ==========


# JSON-RPC 2.0 constants
JSONRPC_VERSION = "2.0"
ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603


class JsonRpcRequest:
    """JSON-RPC 2.0 Request"""

    def __init__(self, data: dict):
        self.jsonrpc = data.get("jsonrpc", JSONRPC_VERSION)
        self.method = data.get("method")
        self.params = data.get("params", {})
        self.id = data.get("id")

        # Validate
        if self.jsonrpc != JSONRPC_VERSION:
            raise ValueError(f"Invalid JSON-RPC version: {self.jsonrpc}")
        if not self.method:
            raise ValueError("Missing method")


class JsonRpcResponse:
    """JSON-RPC 2.0 Response"""

    def __init__(self, result: Any = None, error: Dict[str, Any] = None, id: Any = None):
        self.jsonrpc = JSONRPC_VERSION
        self.id = id
        if error is not None:
            self.error = error
        else:
            self.result = result

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "id": self.id}
        if hasattr(self, "error"):
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


class JsonRpcError:
    """JSON-RPC 2.0 Error"""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


class JsonRpcServer:
    """
    A synchronous JSON-RPC 2.0 server over stdio.
    Compatible with MCP protocol expectations.
    """

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._handlers: Dict[str, Callable] = {}
        self._running = False

    def register_handler(self, method: str, handler: Callable):
        """Register a handler for a JSON-RPC method."""
        logger.info(f"Registering handler for method: {method}")
        self._handlers[method] = handler

    def _read_message(self) -> Optional[str]:
        """Read a single line from stdin."""
        try:
            line = sys.stdin.readline()
            if not line:
                return None
            return line.strip()
        except Exception as e:
            logger.error(f"Error reading from stdin: {e}")
            return None

    def _write_message(self, message: dict):
        """Write a JSON message to stdout."""
        try:
            print(json.dumps(message), flush=True)
        except Exception as e:
            logger.error(f"Error writing to stdout: {e}")

    def _process_request(self, request_str: str) -> Optional[dict]:
        """Process a single JSON-RPC request."""
        request_id = None

        try:
            # Parse JSON
            try:
                request_data = json.loads(request_str)
            except json.JSONDecodeError as e:
                return JsonRpcResponse(
                    error=JsonRpcError(ERROR_PARSE, f"Parse error: {e}").to_dict()
                ).to_dict()

            # Parse request
            try:
                request = JsonRpcRequest(request_data)
                request_id = request.id
            except ValueError as e:
                return JsonRpcResponse(
                    error=JsonRpcError(ERROR_INVALID_REQUEST, str(e)).to_dict(), id=request_id
                ).to_dict()

            # Find handler
            handler = self._handlers.get(request.method)
            if not handler:
                return JsonRpcResponse(
                    error=JsonRpcError(
                        ERROR_METHOD_NOT_FOUND, f"Method not found: {request.method}"
                    ).to_dict(),
                    id=request_id,
                ).to_dict()

            # Execute handler
            try:
                result = handler(request_id, request.params)
                # Handler returns a complete response dict
                return result
            except Exception as e:
                logger.error(f"Handler error for {request.method}: {e}", exc_info=True)
                return JsonRpcResponse(
                    error=JsonRpcError(ERROR_INTERNAL, f"Internal error: {str(e)}").to_dict(),
                    id=request_id,
                ).to_dict()

        except Exception as e:
            logger.error(f"Unexpected error processing request: {e}", exc_info=True)
            return JsonRpcResponse(
                error=JsonRpcError(ERROR_INTERNAL, f"Internal error: {str(e)}").to_dict(),
                id=request_id,
            ).to_dict()

    def run(self):
        """Run the JSON-RPC server (synchronous)."""
        logger.info(f"Starting JSON-RPC server '{self.server_name}'...")
        self._running = True

        while self._running:
            try:
                # Read a line
                line = self._read_message()
                if line is None:
                    logger.info("EOF reached, shutting down")
                    break

                if not line:
                    continue

                # Process the request
                response = self._process_request(line)

                # Send response if any
                if response:
                    self._write_message(response)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt, shutting down")
                break
            except Exception as e:
                logger.error(f"Server error: {e}", exc_info=True)
                continue

        logger.info("Server stopped")

    def stop(self):
        """Stop the server."""
        self._running = False


# MCP-compatible type definitions (simple dicts instead of Pydantic)
def create_text_content(text: str) -> dict:
    """Create a text content object."""
    return {"type": "text", "text": text}


def create_tool(name: str, description: str, input_schema: dict) -> dict:
    """Create a tool definition."""
    return {"name": name, "description": description, "inputSchema": input_schema}


def create_error_response(request_id: Any, code: int, message: str) -> dict:
    """Create an error response."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def create_result_response(request_id: Any, result: Any) -> dict:
    """Create a result response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


# ========== Base models and data structures ==========


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


# ========== Dual model manager with fallback ==========


class DualModelManager:
    """Manages primary and fallback Gemini models with automatic failover."""

    def __init__(self, api_key: str):
        """Initialize the model manager with API key and model configuration."""
        genai.configure(api_key=api_key)

        # Get model names from environment or use defaults
        self.primary_model_name = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.0-flash-exp")
        self.fallback_model_name = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-pro")

        # Timeout configuration (in seconds)
        self.timeout = float(os.getenv("GEMINI_MODEL_TIMEOUT", "10000")) / 1000

        # Initialize models
        self._primary_model = self._initialize_model(self.primary_model_name, "Primary")
        self._fallback_model = self._initialize_model(self.fallback_model_name, "Fallback")

        # Track model usage
        self.primary_calls = 0
        self.fallback_calls = 0
        self.primary_failures = 0

    def _initialize_model(self, model_name: str, model_type: str):
        """Initialize a single model with error handling."""
        try:
            model = genai.GenerativeModel(model_name)
            logger.info(f"{model_type} model initialized: {model_name}")
            return model
        except Exception as e:
            logger.error(f"Failed to initialize {model_type} model {model_name}: {e}")
            return None

    def _generate_with_timeout(self, model, model_name: str, prompt: str, timeout: float) -> str:
        """Execute model generation with timeout using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, prompt)
            try:
                response = future.result(timeout=timeout)
                return response.text
            except FutureTimeoutError:
                logger.warning(f"{model_name} timed out after {timeout}s")
                future.cancel()
                raise TimeoutError(f"{model_name} generation timed out")

    def generate_content(self, prompt: str) -> Tuple[str, str]:
        """
        Generate content using primary model with automatic fallback.

        Returns:
            Tuple of (response_text, model_used)
        """
        # Try primary model first
        if self._primary_model:
            try:
                self.primary_calls += 1
                response_text = self._generate_with_timeout(
                    self._primary_model, self.primary_model_name, prompt, self.timeout
                )
                logger.debug("Primary model responded successfully")
                return response_text, self.primary_model_name
            except (google_exceptions.GoogleAPICallError, ValueError, TimeoutError) as e:
                self.primary_failures += 1
                logger.warning(f"Primary model failed (attempt {self.primary_failures}): {e}")

        # Fallback to secondary model
        if self._fallback_model:
            try:
                self.fallback_calls += 1
                response_text = self._generate_with_timeout(
                    self._fallback_model,
                    self.fallback_model_name,
                    prompt,
                    self.timeout * 1.5,  # Give fallback more time
                )
                logger.info("Fallback model responded successfully")
                return response_text, self.fallback_model_name
            except Exception as e:
                logger.error(f"Fallback model also failed: {e}")
                raise RuntimeError(f"Both models failed. Last error: {e}")

        raise RuntimeError("No models available for content generation")

    def get_stats(self) -> dict:
        """Get usage statistics for the model manager."""
        total_calls = self.primary_calls + self.fallback_calls
        primary_success_rate = (
            (self.primary_calls - self.primary_failures) / self.primary_calls
            if self.primary_calls > 0
            else 0
        )

        return {
            "primary_model": self.primary_model_name,
            "fallback_model": self.fallback_model_name,
            "total_calls": total_calls,
            "primary_calls": self.primary_calls,
            "fallback_calls": self.fallback_calls,
            "primary_failures": self.primary_failures,
            "primary_success_rate": primary_success_rate,
            "timeout_seconds": self.timeout,
        }


# ========== Memory models ==========


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


# ========== Response cache service ==========


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


# ========== Conversation memory service ==========


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
        turn = ConversationTurn(role=role, content=content, metadata=metadata or {})
        self.turns.append(turn)
        self.access_count += 1

    def set(self, key: str, value: Any, category: str = "general") -> None:
        """Store a value with a key."""
        # Remove oldest entries if at capacity
        if len(self.entries) >= self.max_entries:
            oldest_key = min(self.entries.keys(), key=lambda k: self.entries[k].timestamp)
            del self.entries[oldest_key]

        self.entries[key] = MemoryEntry(key=key, value=value, category=category, access_count=0)
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
            "categories": list(set(e.category for e in self.entries.values())),
        }


# ========== Tool base classes ==========


# Simplified ToolOutputBase for bundled tools
class ToolOutputBase:
    """Standard output format for tool execution."""

    def __init__(self, success: bool, result: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.result = result
        self.error = error
        self.metadata: Dict[str, Any] = {}


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
    def input_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for tool inputs."""
        pass

    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        pass

    def get_mcp_definition(self) -> Dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


# Keep the original BaseTool for backwards compatibility during migration
class BaseTool(MCPTool):
    """Legacy base class that wraps MCPTool for backwards compatibility."""

    def __init__(self):
        # No-op for legacy compatibility
        pass

    @property
    def name(self) -> str:
        """Default to empty string for legacy tools."""
        return ""

    @property
    def description(self) -> str:
        """Default to empty string for legacy tools."""
        return ""

    @property
    def input_schema(self) -> Dict[str, Any]:
        """Default to empty schema for legacy tools."""
        return {"type": "object", "properties": {}, "required": []}


# ========== Tool registry ==========


class ToolRegistry:
    """Registry for discovering and managing tools.
    Modified for bundled version to register tools directly."""

    @classmethod
    def _get_bundled_tools(cls):
        """Get all tool classes defined in this bundled file."""
        # This will be populated later
        return []

    """Registry for discovering and managing tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._tool_classes: Dict[str, Type[BaseTool]] = {}

    def discover_tools(self, tools_path: Optional[Path] = None) -> None:
        """Discover and register all tools - bundled version."""
        # In bundled version, register tools directly
        logger.info("Discovering tools in bundled server")

        # Get all tool classes from the global scope
        for tool_class in self._get_bundled_tools():
            try:
                self._register_tool_class(tool_class)
            except Exception as e:
                logger.error(f"Failed to register {tool_class.__name__}: {e}")

        logger.info(f"Registered {len(self._tools)} tools in bundled mode")
        return  # Skip the rest of the original method

    def discover_tools_original(self, tools_path: Optional[Path] = None) -> None:
        """Discover and register all tools in the tools directory."""
        if tools_path is None:
            # Default to the tools package
            tools_path = Path(__file__).parent.parent / "tools"

        logger.info(f"Discovering tools in {tools_path}")

        # Get all Python files in the tools directory
        tool_files = list(tools_path.glob("*.py"))
        logger.debug(f"Found {len(tool_files)} Python files in {tools_path}")

        for tool_file in tool_files:
            if tool_file.name.startswith("_") or tool_file.name == "base.py":
                continue

            # Try both import paths
            module_names = [
                f"gemini_mcp.tools.{tool_file.stem}",
                f"src.gemini_mcp.tools.{tool_file.stem}",
            ]

            module = None
            for module_name in module_names:
                try:
                    logger.debug(f"Attempting to import {module_name}")
                    module = importlib.import_module(module_name)
                    break
                except ImportError:
                    continue

            if module is None:
                logger.error(f"Failed to import tool from {tool_file}")
                continue

            try:

                # Find all classes that inherit from BaseTool
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseTool) and obj != BaseTool:
                        logger.debug(f"Found tool class: {name}")
                        self._register_tool_class(obj)

            except Exception as e:
                logger.error(f"Failed to import tool from {tool_file}: {e}")

    def _register_tool_class(self, tool_class: Type[BaseTool]) -> None:
        """Register a tool class."""
        try:
            # Instantiate the tool to get its metadata
            tool_instance = tool_class()
            # In bundled version, use property-based access
            tool_name = tool_instance.name

            if tool_name in self._tools:
                logger.warning(f"Tool {tool_name} already registered, skipping")
                return

            self._tools[tool_name] = tool_instance
            self._tool_classes[tool_name] = tool_class
            logger.info(f"Registered tool: {tool_name}")

        except Exception as e:
            logger.error(f"Failed to register tool {tool_class.__name__}: {e}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool instance by name."""
        return self._tools.get(name)

    def get_tool_class(self, name: str) -> Optional[Type[BaseTool]]:
        """Get a tool class by name."""
        return self._tool_classes.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Get all registered tools."""
        return self._tools.copy()

    def get_mcp_tool_definitions(self) -> List[Dict]:
        """Get MCP tool definitions for all registered tools."""
        definitions = []
        for tool in self._tools.values():
            try:
                definitions.append(tool.get_mcp_definition())
            except Exception as e:
                logger.error(f"Failed to get MCP definition for {tool.metadata.name}: {e}")
        return definitions


# ========== Conversation orchestrator ==========


class ConversationOrchestrator:
    """Orchestrates tool execution and manages conversation flow."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        model_manager: Any,  # DualModelManager
        memory: Optional[ConversationMemory] = None,
        cache: Optional[ResponseCache] = None,
    ):
        self.tool_registry = tool_registry
        self.model_manager = model_manager
        self.memory = memory or ConversationMemory()
        self.cache = cache or ResponseCache()
        self.execution_history: List[ToolOutput] = []

    async def execute_tool(
        self, tool_name: str, parameters: Dict[str, Any], request_id: Optional[str] = None
    ) -> ToolOutput:
        """Execute a single tool with proper context injection."""

        # Check cache first
        cache_key = self.cache.create_key(tool_name, parameters)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {tool_name}")
            return cached_result

        # Get the tool
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return ToolOutput(
                tool_name=tool_name, result=None, success=False, error=f"Unknown tool: {tool_name}"
            )

        # Create tool input with context
        tool_input = ToolInput(
            tool_name=tool_name,
            parameters=parameters,
            context={
                "model_manager": self.model_manager,
                "memory": self.memory,
                "orchestrator": self,
            },
            request_id=request_id,
        )

        # Execute the tool
        output = await tool.run(tool_input)

        # Cache successful results
        if output.success:
            self.cache.set(cache_key, output)

        # Store in execution history
        self.execution_history.append(output)

        # Update memory if needed
        if output.success and hasattr(tool, "update_memory"):
            tool.update_memory(self.memory, output)

        return output

    async def execute_protocol(
        self, protocol_name: str, initial_input: Dict[str, Any]
    ) -> List[ToolOutput]:
        """Execute a multi-step protocol (e.g., debate, synthesis)."""
        logger.info(f"Executing protocol: {protocol_name}")

        # Example: Simple sequential execution
        if protocol_name == "simple":
            return [
                await self.execute_tool(
                    initial_input.get("tool_name"), initial_input.get("parameters")
                )
            ]

        # Debate protocol
        elif protocol_name == "debate":
            topic = initial_input.get("topic", "")
            positions = initial_input.get("positions", [])

            if not topic or not positions:
                return [
                    ToolOutput(
                        tool_name="debate_protocol",
                        result=None,
                        success=False,
                        error="Debate protocol requires 'topic' and 'positions' parameters",
                    )
                ]

            debate = DebateProtocol(self, topic, positions)
            try:
                result = await debate.run()
                return [
                    ToolOutput(
                        tool_name="debate_protocol",
                        result=result,
                        success=True,
                        metadata={"protocol": "debate", "rounds": len(result.get("rounds", []))},
                    )
                ]
            except Exception as e:
                logger.error(f"Debate protocol error: {e}")
                return [
                    ToolOutput(
                        tool_name="debate_protocol", result=None, success=False, error=str(e)
                    )
                ]

        # Synthesis protocol (simple wrapper around synthesize tool)
        elif protocol_name == "synthesis":
            return [
                await self.execute_tool(
                    "synthesize_perspectives", initial_input.get("parameters", {})
                )
            ]

        # Protocol not implemented
        raise NotImplementedError(f"Protocol {protocol_name} not implemented")

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics about tool executions."""
        total = len(self.execution_history)
        successful = sum(1 for output in self.execution_history if output.success)
        failed = total - successful

        avg_time = 0
        if total > 0:
            times = [o.execution_time_ms for o in self.execution_history if o.execution_time_ms]
            avg_time = sum(times) / len(times) if times else 0

        return {
            "total_executions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "average_execution_time_ms": avg_time,
            "cache_stats": self.cache.get_stats(),
        }


# ========== Ask Gemini tool ==========


class AskGeminiTool(MCPTool):
    """Tool for Ask Gemini."""

    @property
    def name(self) -> str:
        return "ask_gemini"

    @property
    def description(self) -> str:
        return "Ask Gemini a general question or for help with a problem"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question or problem to ask Gemini",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context to help Gemini understand better",
                    "default": "",
                },
            },
            "required": ["question"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        try:
            # Get parameters
            question = parameters.get("question", "")
            context = parameters.get("context", "")

            if not question:
                return ToolOutputBase(success=False, error="Question is required")

            # Build prompt
            prompt = f"Context: {context}\n\n" if context else ""
            prompt += f"Question: {question}"

            # Get model manager from global context (will be injected during bundling)
            # In modular mode, this would come from the orchestrator context

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🤖 Gemini's Response:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutputBase(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutputBase(success=False, error=f"Error: {str(e)}")


# ========== Code review tool ==========


class CodeReviewTool(MCPTool):
    """Tool for Code Review."""

    @property
    def name(self) -> str:
        return "gemini_code_review"

    @property
    def description(self) -> str:
        return "Ask Gemini to review code for issues, improvements, or best practices"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The code to review"},
                "language": {
                    "type": "string",
                    "description": "Programming language (e.g., python, javascript)",
                    "default": "javascript",
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on "
                    "(e.g., security, performance, readability)",
                    "default": "general",
                },
            },
            "required": ["code"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        try:
            code = parameters.get("code")
            if not code:
                return ToolOutputBase(success=False, error="Code is required for review")

            language = parameters.get("language", "javascript")
            focus = parameters.get("focus", "general")

            # Build the prompt
            prompt = self._build_prompt(code, language, focus)

            # Get model manager from global context

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🔍 Code Review:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutputBase(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutputBase(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, code: str, language: str, focus: str) -> str:
        """Build the code review prompt."""
        focus_instructions = {
            "security": "Pay special attention to security vulnerabilities, "
            "input validation, and potential exploits.",
            "performance": "Focus on performance optimizations, "
            "algorithmic complexity, and resource usage.",
            "readability": "Emphasize code clarity, naming conventions, and maintainability.",
            "best_practices": f"Review against {language} best practices and idiomatic patterns.",
            "general": "Provide a comprehensive review covering all aspects.",
        }

        focus_text = focus_instructions.get(focus, focus_instructions["general"])

        return f"""Please review the following {language} code:

```{language}
{code}
```

{focus_text}

Provide:
1. Overall assessment
2. Specific issues found (if any)
3. Suggestions for improvement
4. Examples of better implementations where applicable

Be constructive and specific in your feedback."""


# ========== Brainstorm tool ==========


class BrainstormTool(MCPTool):
    """Tool for Brainstorm."""

    @property
    def name(self) -> str:
        return "gemini_brainstorm"

    @property
    def description(self) -> str:
        return "Brainstorm ideas or solutions with Gemini"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic or problem to brainstorm about",
                },
                "constraints": {
                    "type": "string",
                    "description": "Any constraints or requirements to consider",
                    "default": "",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        try:
            topic = parameters.get("topic")
            if not topic:
                return ToolOutputBase(success=False, error="Topic is required for brainstorming")

            constraints = parameters.get("constraints", "")

            # Build the prompt
            prompt = self._build_prompt(topic, constraints)

            # Get model manager from global context

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"💡 Brainstorming Results:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutputBase(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutputBase(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, topic: str, constraints: str) -> str:
        """Build the brainstorming prompt."""
        constraints_text = f"\nConstraints to consider:\n{constraints}" if constraints else ""

        return f"""Let's brainstorm ideas about: {topic}{constraints_text}

Please provide:
1. Creative and innovative ideas
2. Different perspectives and approaches
3. Potential challenges and solutions
4. Actionable next steps

Be creative but practical. Think outside the box while considering feasibility."""


# ========== Test cases tool ==========


class TestCasesTool(MCPTool):
    """Tool for Test Cases."""

    @property
    def name(self) -> str:
        return "gemini_test_cases"

    @property
    def description(self) -> str:
        return "Ask Gemini to suggest test cases for code or features"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code_or_feature": {
                    "type": "string",
                    "description": "Code snippet or feature description",
                },
                "test_type": {
                    "type": "string",
                    "description": "Type of tests (unit, integration, edge cases)",
                    "default": "all",
                },
            },
            "required": ["code_or_feature"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        try:
            code_or_feature = parameters.get("code_or_feature")
            if not code_or_feature:
                return ToolOutputBase(success=False, error="Code or feature description is required")

            test_type = parameters.get("test_type", "all")

            # Build the prompt
            prompt = self._build_prompt(code_or_feature, test_type)

            # Get model manager from global context

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🧪 Test Cases:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutputBase(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutputBase(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, code_or_feature: str, test_type: str) -> str:
        """Build the test case generation prompt."""
        test_type_instructions = {
            "unit": "Focus on unit tests that test individual functions or methods in isolation.",
            "integration": "Focus on integration tests that verify "
            "components work together correctly.",
            "edge": "Focus on edge cases, boundary conditions, and error scenarios.",
            "performance": "Include performance and load testing scenarios.",
            "all": "Provide comprehensive test cases covering all aspects.",
        }

        test_focus = test_type_instructions.get(test_type, test_type_instructions["all"])

        # Detect if input is code or feature description
        is_code = any(
            indicator in code_or_feature
            for indicator in ["def ", "function", "class", "{", "=>", "()"]
        )
        input_type = "code" if is_code else "feature"

        return f"""Please suggest test cases for the following {input_type}:

{code_or_feature}

{test_focus}

For each test case, provide:
1. Test name/description
2. Input/setup required
3. Expected behavior/output
4. Why this test is important

Include both positive (happy path) and negative (error) test cases."""


# ========== Explain tool ==========


class ExplainTool(MCPTool):
    """Tool for Explain."""

    @property
    def name(self) -> str:
        return "gemini_explain"

    @property
    def description(self) -> str:
        return "Ask Gemini to explain complex code or concepts"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Code or concept to explain"},
                "level": {
                    "type": "string",
                    "description": "Explanation level (beginner, intermediate, expert)",
                    "default": "intermediate",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        try:
            topic = parameters.get("topic")
            if not topic:
                return ToolOutputBase(success=False, error="Topic is required for explanation")

            level = parameters.get("level", "intermediate")

            # Build the prompt
            prompt = self._build_prompt(topic, level)

            # Get model manager from global context

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"📚 Explanation:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutputBase(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutputBase(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, topic: str, level: str) -> str:
        """Build the explanation prompt."""
        level_instructions = {
            "beginner": """Explain this as if to someone new to programming:
- Use simple language and avoid jargon
- Provide analogies to everyday concepts
- Break down complex ideas into simple steps
- Include examples that build understanding gradually""",
            "intermediate": """Explain this to someone with programming experience:
- Assume familiarity with basic programming concepts
- Focus on the key insights and patterns
- Include practical examples and use cases
- Mention common pitfalls and best practices""",
            "expert": """Provide an in-depth technical explanation:
- Include implementation details and edge cases
- Discuss performance implications and trade-offs
- Reference relevant algorithms, data structures, or design patterns
- Compare with alternative approaches""",
        }

        level_text = level_instructions.get(level, level_instructions["intermediate"])

        return f"""Please explain the following:

{topic}

{level_text}

Structure your explanation with:
1. Overview/Summary
2. Detailed explanation
3. Examples (if applicable)
4. Key takeaways"""


# ========== Synthesize tool ==========


class SynthesizeTool(MCPTool):
    """Tool for Synthesize."""

    @property
    def name(self) -> str:
        return "synthesize_perspectives"

    @property
    def description(self) -> str:
        return "Synthesize multiple viewpoints or pieces of information into a coherent summary"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic or question being addressed"},
                "perspectives": {
                    "type": "array",
                    "description": "List of different perspectives or pieces of information",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Source or viewpoint identifier",
                            },
                            "content": {
                                "type": "string",
                                "description": "The perspective or information",
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["topic", "perspectives"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutputBase:
        """Execute the tool."""
        try:
            topic = parameters.get("topic")
            if not topic:
                return ToolOutputBase(success=False, error="Topic is required for synthesis")

            perspectives = parameters.get("perspectives", [])
            if not perspectives:
                return ToolOutputBase(success=False, error="At least one perspective is required")

            # Build the prompt
            prompt = self._build_prompt(topic, perspectives)

            # Get model manager from global context

            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🔄 Synthesis:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutputBase(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutputBase(success=False, error=f"Error: {str(e)}")

    def _build_prompt(self, topic: str, perspectives: List[Dict[str, str]]) -> str:
        """Build the synthesis prompt."""
        perspectives_text = "\n\n".join(
            [
                f"**{p.get('source', f'Perspective {i+1}')}:**\n{p['content']}"
                for i, p in enumerate(perspectives)
            ]
        )

        return f"""Please synthesize the following perspectives on: {topic}

{perspectives_text}

Provide a balanced synthesis that:
1. Identifies common themes and agreements
2. Highlights key differences and tensions
3. Evaluates the strengths and weaknesses of each perspective
4. Proposes a unified understanding or framework
5. Suggests actionable insights or next steps

Be objective and fair to all viewpoints while providing critical analysis."""


# ========== Debate protocol ==========


@dataclass
class DebatePosition:
    """Represents a position in a debate."""

    agent_name: str
    stance: str
    arguments: List[str] = field(default_factory=list)
    rebuttals: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class DebateRound:
    """Represents a round of debate."""

    round_number: int
    positions: List[DebatePosition]
    synthesis: Optional[str] = None


class DebateProtocol:
    """Orchestrates structured debates between multiple agents."""

    def __init__(self, orchestrator, topic: str, positions: List[str]):
        self.orchestrator = orchestrator
        self.topic = topic
        self.positions = positions
        self.rounds: List[DebateRound] = []
        self.max_rounds = 3

    async def run(self) -> Dict[str, Any]:
        """Run the debate protocol."""
        logger.info(f"Starting debate on topic: {self.topic}")

        # Round 1: Opening statements
        round1 = await self._opening_statements()
        self.rounds.append(round1)

        # Round 2: Rebuttals
        round2 = await self._rebuttal_round()
        self.rounds.append(round2)

        # Round 3: Final synthesis
        synthesis = await self._synthesis_round()

        return {
            "topic": self.topic,
            "rounds": self.rounds,
            "final_synthesis": synthesis,
            "positions_explored": len(self.positions),
        }

    async def _opening_statements(self) -> DebateRound:
        """Generate opening statements for each position."""
        logger.info("Debate Round 1: Opening statements")

        debate_positions = []

        for i, position in enumerate(self.positions):
            # Create a persona for this position
            prompt = f"""You are participating in a structured debate on the topic: {self.topic}

Your assigned position is: {position}

Please provide:
1. Your main argument (2-3 sentences)
2. Three supporting points
3. Your confidence level (0.0-1.0) in this position
4. Any caveats or limitations you acknowledge

Be concise but persuasive."""

            # Execute via orchestrator
            result = await self.orchestrator.execute_tool(
                "ask_gemini", {"question": prompt, "context": f"Debate agent {i+1}"}
            )

            if result.success:
                # Parse the response (in a real implementation, we'd use structured output)
                debate_position = DebatePosition(
                    agent_name=f"Agent_{i+1}",
                    stance=position,
                    arguments=[result.result],  # Simplified for now
                    confidence=0.7,  # Would be parsed from response
                )
                debate_positions.append(debate_position)

        return DebateRound(round_number=1, positions=debate_positions)

    async def _rebuttal_round(self) -> DebateRound:
        """Generate rebuttals for each position."""
        logger.info("Debate Round 2: Rebuttals")

        if not self.rounds:
            raise ValueError("No opening statements to rebut")

        previous_positions = self.rounds[0].positions
        updated_positions = []

        for i, position in enumerate(previous_positions):
            rebuttals = {}

            # Generate rebuttals against other positions
            for j, other_position in enumerate(previous_positions):
                if i == j:
                    continue

                prompt = f"""You previously argued for: {position.stance}

The opposing view argues: {other_position.arguments[0]}

Please provide:
1. A concise rebuttal to their argument
2. Why your position is stronger
3. Any points of agreement or common ground

Keep your response under 100 words."""

                result = await self.orchestrator.execute_tool(
                    "ask_gemini",
                    {"question": prompt, "context": f"Rebuttal from {position.agent_name}"},
                )

                if result.success:
                    rebuttals[other_position.agent_name] = result.result

            # Update position with rebuttals
            position.rebuttals = rebuttals
            updated_positions.append(position)

        return DebateRound(round_number=2, positions=updated_positions)

    async def _synthesis_round(self) -> str:
        """Synthesize all positions into a final analysis."""
        logger.info("Debate Round 3: Synthesis")

        # Prepare perspectives for synthesis tool
        perspectives = []

        for round in self.rounds:
            for position in round.positions:
                perspectives.append(
                    {
                        "source": f"{position.agent_name} ({position.stance})",
                        "content": " ".join(position.arguments),
                    }
                )

        # Use the synthesize_perspectives tool
        result = await self.orchestrator.execute_tool(
            "synthesize_perspectives", {"topic": self.topic, "perspectives": perspectives}
        )

        return result.result if result.success else "Failed to synthesize debate"


# ========== Main server class ==========


class GeminiMCPServerV3:
    """Modular MCP Server for Gemini integration using JSON-RPC."""

    def __init__(self):
        """Initialize the server with modular components."""
        self.model_manager: Optional[DualModelManager] = None
        self.tool_registry = ToolRegistry()
        self.cache = ResponseCache(max_size=100, ttl_seconds=3600)
        self.memory = ConversationMemory(max_turns=50, max_entries=100)
        self.orchestrator: Optional[ConversationOrchestrator] = None

        # Create JSON-RPC server
        self.server = JsonRpcServer("gemini-mcp-server")
        self._setup_handlers()

    def _initialize_model_manager(self) -> bool:
        """Initialize the model manager with API key."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("No GEMINI_API_KEY found in environment. Please check your .env file.")
            # Log all env vars starting with GEMINI for debugging
            gemini_vars = {k: v for k, v in os.environ.items() if k.startswith("GEMINI")}
            if gemini_vars:
                logger.info(f"Found GEMINI env vars: {list(gemini_vars.keys())}")
            else:
                logger.warning("No GEMINI environment variables found at all")
            return False

        try:
            logger.info(f"Initializing DualModelManager with API key (length: {len(api_key)})")
            self.model_manager = DualModelManager(api_key)

            # Inject model manager into tools
            logger.info("Injecting model manager into tools...")
            for tool_name in self.tool_registry.list_tools():
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    setattr(tool, "_model_manager", self.model_manager)
                    logger.debug(f"Injected model manager into tool: {tool_name}")

            # Create orchestrator with all components
            logger.info("Creating conversation orchestrator...")
            self.orchestrator = ConversationOrchestrator(
                tool_registry=self.tool_registry,
                model_manager=self.model_manager,
                memory=self.memory,
                cache=self.cache,
            )

            logger.info("Model manager initialization complete")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize model manager: {e}", exc_info=True)
            return False

    def _setup_handlers(self):
        """Set up JSON-RPC handlers."""

        # Register handlers
        self.server.register_handler("initialize", self.handle_initialize)
        self.server.register_handler("tools/list", self.handle_tools_list)
        self.server.register_handler("tools/call", self.handle_tool_call)

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialization request."""
        # Load environment variables from the MCP installation directory
        mcp_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        env_path = os.path.join(mcp_dir, ".env")

        if load_dotenv and os.path.exists(env_path):
            logger.info(f"Loading .env from {env_path}")
            load_dotenv(env_path)
        else:
            # Try loading from current directory as fallback
            if load_dotenv:
                load_dotenv()

        # Log the API key status
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            logger.info(f"GEMINI_API_KEY found (length: {len(api_key)})")
        else:
            logger.warning("GEMINI_API_KEY not found in environment")

        # Discover and register all tools FIRST
        self.tool_registry.discover_tools()
        logger.info(f"Registered {len(self.tool_registry.list_tools())} tools")

        # Initialize model manager AFTER tools are registered
        model_initialized = self._initialize_model_manager()

        return create_result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "gemini-mcp-server",
                    "version": __version__,
                    "modelsAvailable": model_initialized,
                },
                "capabilities": {"tools": {}},
            },
        )

    def handle_tools_list(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool list request."""
        # Get tool definitions from registry
        tool_defs = self.tool_registry.get_mcp_tool_definitions()

        # Convert to tool list format
        tools = []
        for tool_def in tool_defs:
            tools.append(
                {
                    "name": tool_def["name"],
                    "description": tool_def["description"],
                    "inputSchema": tool_def["inputSchema"],
                }
            )

        # Add server info tool
        tools.append(
            {
                "name": "server_info",
                "description": "Get server version and status",
                "inputSchema": {"type": "object", "properties": {}},
            }
        )

        return create_result_response(request_id, {"tools": tools})

    def handle_tool_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"Executing tool: {tool_name}")

        # Handle server info specially
        if tool_name == "server_info":
            result = self._get_server_info()
            return create_result_response(
                request_id, {"content": [{"type": "text", "text": result}]}
            )

        # Check if models are initialized
        if not self.orchestrator:
            result = (
                "❌ Gemini models not initialized. "
                "Please set GEMINI_API_KEY environment variable."
            )
            return create_result_response(
                request_id, {"content": [{"type": "text", "text": result}]}
            )

        # Execute tool directly
        # Set global model manager for tools
        global model_manager
        model_manager = self.model_manager

        if tool_name == "ask_gemini":
            result = self._ask_gemini(arguments)
        elif tool_name == "gemini_code_review":
            result = self._code_review(arguments)
        elif tool_name == "gemini_brainstorm":
            result = self._brainstorm(arguments)
        elif tool_name == "gemini_test_cases":
            result = self._suggest_test_cases(arguments)
        elif tool_name == "gemini_explain":
            result = self._explain(arguments)
        elif tool_name == "synthesize_perspectives":
            result = self._synthesize(arguments)
        else:
            result = f"❌ Unknown tool: {tool_name}"

        return create_result_response(request_id, {"content": [{"type": "text", "text": result}]})

    def _get_server_info(self) -> str:
        """Get server information and status."""
        # Get list of available tools
        registered_tools = self.tool_registry.list_tools()
        all_tools = registered_tools + ["server_info"]  # Include server_info tool

        info = {
            "version": __version__,
            "architecture": "modular-single-file",
            "available_tools": all_tools,
            "components": {
                "tools_registered": len(registered_tools),
                "total_tools_available": len(all_tools),
                "cache_stats": self.cache.get_stats() if self.cache else None,
                "memory_stats": self.memory.get_stats() if self.memory else None,
            },
            "models": {
                "initialized": self.model_manager is not None,
                "primary": getattr(self.model_manager, "primary_model_name", None),
                "fallback": getattr(self.model_manager, "fallback_model_name", None),
            },
        }

        if self.orchestrator:
            info["execution_stats"] = self.orchestrator.get_execution_stats()

        return f"🤖 Gemini MCP Server v{__version__}\n\n{json.dumps(info, indent=2)}"

    def _ask_gemini(self, arguments: Dict[str, Any]) -> str:
        """Ask Gemini a general question."""
        question = arguments.get("question", "")
        context = arguments.get("context", "")

        if not question:
            return "❌ Question is required"

        prompt = f"Context: {context}\n\n" if context else ""
        prompt += f"Question: {question}"

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            result = f"🤖 Gemini's Response:\n\n{response_text}"
            if model_used != self.model_manager.primary_model_name:
                result += f"\n\n[Model: {model_used}]"
            return result
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error: {str(e)}"

    def _code_review(self, arguments: Dict[str, Any]) -> str:
        """Code review implementation."""
        code = arguments.get("code")
        if not code:
            return "❌ Code is required for review"

        language = arguments.get("language", "javascript")
        focus = arguments.get("focus", "general")

        focus_instructions = {
            "security": "Pay special attention to security vulnerabilities.",
            "performance": "Focus on performance optimizations.",
            "readability": "Emphasize code clarity and maintainability.",
            "general": "Provide a comprehensive review.",
        }

        prompt = f"""Please review the following {language} code:

```{language}
{code}
```

{focus_instructions.get(focus, focus_instructions["general"])}

Provide specific feedback and suggestions."""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            result = f"🔍 Code Review:\n\n{response_text}"
            if model_used != self.model_manager.primary_model_name:
                result += f"\n\n[Model: {model_used}]"
            return result
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def _brainstorm(self, arguments: Dict[str, Any]) -> str:
        """Brainstorm implementation."""
        topic = arguments.get("topic")
        if not topic:
            return "❌ Topic is required for brainstorming"

        constraints = arguments.get("constraints", "")
        constraints_text = f"\nConstraints: {constraints}" if constraints else ""

        prompt = f"""Let's brainstorm ideas about: {topic}{constraints_text}

Please provide:
1. Creative and innovative ideas
2. Different perspectives
3. Potential challenges and solutions
4. Actionable next steps"""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            result = f"💡 Brainstorming Results:\n\n{response_text}"
            if model_used != self.model_manager.primary_model_name:
                result += f"\n\n[Model: {model_used}]"
            return result
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def _suggest_test_cases(self, arguments: Dict[str, Any]) -> str:
        """Test cases implementation."""
        code_or_feature = arguments.get("code_or_feature")
        if not code_or_feature:
            return "❌ Code or feature description is required"

        test_type = arguments.get("test_type", "all")

        prompt = f"""Please suggest test cases for the following:

{code_or_feature}

Focus on {test_type} tests. For each test case, provide:
1. Test name/description
2. Input/setup required
3. Expected behavior/output
4. Why this test is important"""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            result = f"🧪 Test Cases:\n\n{response_text}"
            if model_used != self.model_manager.primary_model_name:
                result += f"\n\n[Model: {model_used}]"
            return result
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def _explain(self, arguments: Dict[str, Any]) -> str:
        """Explain implementation."""
        topic = arguments.get("topic")
        if not topic:
            return "❌ Topic is required for explanation"

        level = arguments.get("level", "intermediate")

        level_instructions = {
            "beginner": "Explain in simple terms for someone new to programming.",
            "intermediate": "Explain for someone with programming experience.",
            "expert": "Provide an in-depth technical explanation.",
        }

        prompt = f"""Please explain the following:

{topic}

{level_instructions.get(level, level_instructions["intermediate"])}

Structure your explanation clearly with examples if applicable."""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            result = f"📚 Explanation:\n\n{response_text}"
            if model_used != self.model_manager.primary_model_name:
                result += f"\n\n[Model: {model_used}]"
            return result
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def _synthesize(self, arguments: Dict[str, Any]) -> str:
        """Synthesize perspectives implementation."""
        topic = arguments.get("topic")
        if not topic:
            return "❌ Topic is required for synthesis"

        perspectives = arguments.get("perspectives", [])
        if not perspectives:
            return "❌ At least one perspective is required"

        perspectives_text = "\n\n".join(
            [
                f"**{p.get('source', f'Perspective {i+1}')}:**\n{p['content']}"
                for i, p in enumerate(perspectives)
            ]
        )

        prompt = f"""Please synthesize the following perspectives on: {topic}

{perspectives_text}

Provide a balanced synthesis that:
1. Identifies common themes
2. Highlights key differences
3. Proposes a unified understanding"""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            result = f"🔄 Synthesis:\n\n{response_text}"
            if model_used != self.model_manager.primary_model_name:
                result += f"\n\n[Model: {model_used}]"
            return result
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def run(self):
        """Run the MCP server."""
        logger.info(f"Starting Gemini MCP Server v{__version__} (Modular Single-File)")

        # Configure unbuffered output for proper MCP communication
        sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 1)
        sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 1)

        # Run the JSON-RPC server
        self.server.run()


# ========== Tool Output (Simplified for Bundled Version) ==========


class ToolOutput:
    """Standard output format for tool execution."""

    def __init__(self, success: bool, result: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.result = result
        self.error = error
        self.metadata: Dict[str, Any] = {}


# ========== Register Bundled Tools ==========

# Update the ToolRegistry to know about bundled tools
ToolRegistry._get_bundled_tools = classmethod(
    lambda cls: [
        AskGeminiTool,
        CodeReviewTool,
        BrainstormTool,
        TestCasesTool,
        ExplainTool,
        SynthesizeTool,
    ]
)


# ========== Main Execution ==========


def main():
    """Main entry point."""
    try:
        server = GeminiMCPServerV3()
        server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
