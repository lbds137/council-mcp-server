#!/usr/bin/env python3
"""
Gemini MCP Server v3.0.0 - Single File Version
A Model Context Protocol server that enables Claude to collaborate with Google's Gemini AI models.
This version combines all modular components into a single deployable file.
"""

import asyncio
import collections
import hashlib
import json
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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

# ========== JSON-RPC Implementation ==========

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


# ========== Model Manager ==========


class DualModelManager:
    """Manages primary and fallback Gemini models"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._primary_model = None
        self._fallback_model = None
        self.primary_model_name = os.environ.get(
            "GEMINI_MODEL_PRIMARY", "gemini-2.5-pro-preview-06-05"
        )
        self.fallback_model_name = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-1.5-pro")

        # Parse timeout with error handling
        try:
            self.timeout = (
                int(os.environ.get("GEMINI_MODEL_TIMEOUT", "10000")) / 1000
            )  # Convert to seconds
        except ValueError:
            logger.warning("Invalid GEMINI_MODEL_TIMEOUT, using default 10 seconds")
            self.timeout = 10.0

        # Performance tracking
        self.call_stats = {
            "primary_success": 0,
            "primary_failure": 0,
            "fallback_success": 0,
            "fallback_failure": 0,
            "total_calls": 0,
        }

        # Initialize Gemini API
        genai.configure(api_key=self.api_key)

        # Try to initialize models
        self._initialize_models()

    def _initialize_models(self):
        """Initialize primary and fallback models"""
        try:
            self._primary_model = genai.GenerativeModel(self.primary_model_name)
            logger.info(f"Primary model initialized: {self.primary_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize primary model {self.primary_model_name}: {e}")

        try:
            self._fallback_model = genai.GenerativeModel(self.fallback_model_name)
            logger.info(f"Fallback model initialized: {self.fallback_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize fallback model {self.fallback_model_name}: {e}")

        # If primary failed but fallback succeeded, swap them
        if not self._primary_model and self._fallback_model:
            self._primary_model = self._fallback_model
            self.primary_model_name = self.fallback_model_name
            self._fallback_model = None
            logger.warning("Using fallback model as primary due to initialization failure")

    def _generate_with_timeout(self, model, model_name: str, prompt: str, timeout: float) -> str:
        """Execute model generation with timeout using ThreadPoolExecutor"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, prompt)
            try:
                response = future.result(timeout=timeout)
                return response.text
            except TimeoutError:
                logger.warning(f"{model_name} timed out after {timeout}s")
                future.cancel()
                raise TimeoutError(f"{model_name} generation timed out")

    def generate_content(self, prompt: str) -> Tuple[str, str]:
        """
        Generate content using primary model with automatic fallback
        Returns: (response_text, model_used)
        """
        self.call_stats["total_calls"] += 1

        if not self._primary_model and not self._fallback_model:
            raise RuntimeError("No models available")

        # Try primary model first
        if self._primary_model:
            try:
                start_time = time.time()
                response_text = self._generate_with_timeout(
                    self._primary_model, self.primary_model_name, prompt, self.timeout
                )
                elapsed = time.time() - start_time
                logger.info(f"Primary model responded in {elapsed:.2f}s")
                self.call_stats["primary_success"] += 1
                return response_text, self.primary_model_name

            except (google_exceptions.GoogleAPICallError, ValueError, TimeoutError) as e:
                logger.error(f"Primary model failed: {e}")
                self.call_stats["primary_failure"] += 1
                if not self._fallback_model:
                    raise RuntimeError("Primary model failed with no fallback available") from e

        # Try fallback model
        if self._fallback_model:
            try:
                logger.info("Falling back to secondary model")
                response_text = self._generate_with_timeout(
                    self._fallback_model,
                    self.fallback_model_name,
                    prompt,
                    self.timeout * 1.5,  # Give fallback a bit more time
                )
                self.call_stats["fallback_success"] += 1
                return response_text, self.fallback_model_name
            except (google_exceptions.GoogleAPICallError, ValueError, TimeoutError) as e:
                logger.error(f"Fallback model also failed: {e}")
                self.call_stats["fallback_failure"] += 1
                raise RuntimeError("Both models failed to generate content") from e

        raise RuntimeError("No functional models available")

    def get_status(self) -> Dict[str, Any]:
        """Get current model status"""
        return {
            "primary": {
                "name": self.primary_model_name,
                "available": self._primary_model is not None,
            },
            "fallback": {
                "name": self.fallback_model_name,
                "available": self._fallback_model is not None,
            },
            "timeout": self.timeout,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        total_primary = self.call_stats["primary_success"] + self.call_stats["primary_failure"]
        total_fallback = self.call_stats["fallback_success"] + self.call_stats["fallback_failure"]

        return {
            "total_calls": self.call_stats["total_calls"],
            "primary_success_rate": self.call_stats["primary_success"] / max(1, total_primary),
            "fallback_success_rate": self.call_stats["fallback_success"] / max(1, total_fallback),
            "fallback_usage_rate": total_fallback / max(1, self.call_stats["total_calls"]),
            "raw_stats": self.call_stats,
        }


# ========== Tool Base Classes ==========


class ToolOutput:
    """Standard output format for tool execution."""

    def __init__(self, success: bool, result: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.result = result
        self.error = error
        self.metadata: Dict[str, Any] = {}


class MCPTool(ABC):
    """Base class for MCP tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name for MCP."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for MCP."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON schema for tool inputs."""
        pass

    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool with given parameters."""
        pass

    def get_mcp_definition(self) -> Dict[str, Any]:
        """Get MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


# ========== Cache Service ==========


class CacheEntry:
    """Single cache entry with metadata."""

    def __init__(self, key: str, value: Any, ttl_seconds: int):
        self.key = key
        self.value = value
        self.created_at = datetime.now()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0
        self.last_accessed = self.created_at

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        age = datetime.now() - self.created_at
        return age.total_seconds() > self.ttl_seconds

    def access(self) -> Any:
        """Access the cached value."""
        self.access_count += 1
        self.last_accessed = datetime.now()
        return self.value


class ResponseCache:
    """LRU cache for Gemini responses with TTL support."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.default_ttl = ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: collections.OrderedDict = collections.OrderedDict()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    def _make_key(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Create a cache key from tool name and parameters."""
        # Sort parameters for consistent hashing
        sorted_params = json.dumps(parameters, sort_keys=True)
        key_data = f"{tool_name}:{sorted_params}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def get(self, tool_name: str, parameters: Dict[str, Any]) -> Optional[str]:
        """Get cached response if available and not expired."""
        key = self._make_key(tool_name, parameters)

        if key in self._cache:
            entry = self._cache[key]

            # Check expiration
            if entry.is_expired():
                self._remove_entry(key)
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            # Update access order
            self._access_order.move_to_end(key)
            self._stats["hits"] += 1
            return entry.access()

        self._stats["misses"] += 1
        return None

    def set(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        response: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache a response."""
        key = self._make_key(tool_name, parameters)
        ttl = ttl_seconds or self.default_ttl

        # Check if we need to evict
        if len(self._cache) >= self.max_size and key not in self._cache:
            # Remove least recently used
            lru_key = next(iter(self._access_order))
            self._remove_entry(lru_key)
            self._stats["evictions"] += 1

        # Add or update entry
        self._cache[key] = CacheEntry(key, response, ttl)
        self._access_order[key] = True
        self._access_order.move_to_end(key)

    def _remove_entry(self, key: str) -> None:
        """Remove an entry from cache."""
        if key in self._cache:
            del self._cache[key]
        if key in self._access_order:
            del self._access_order[key]

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._access_order.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / max(1, total_requests)

        # Calculate size and age stats
        if self._cache:
            ages = [(datetime.now() - e.created_at).total_seconds() for e in self._cache.values()]
            avg_age = sum(ages) / len(ages)
            oldest_age = max(ages)
        else:
            avg_age = 0
            oldest_age = 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
            "stats": self._stats.copy(),
            "avg_age_seconds": avg_age,
            "oldest_age_seconds": oldest_age,
        }


# ========== Memory Service ==========


class ConversationMemory:
    """Enhanced conversation memory with turn management."""

    def __init__(self, max_turns: int = 50, max_entries: int = 100):
        self.max_turns = max_turns
        self.max_entries = max_entries
        self.turns: List[Dict[str, Any]] = []
        self.context: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.total_interactions = 0

    def add_turn(
        self,
        tool: str,
        input_params: Dict[str, Any],
        output: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a conversation turn."""
        turn = {
            "timestamp": datetime.now(),
            "tool": tool,
            "input": input_params,
            "output": output,
            "metadata": metadata or {},
        }

        self.turns.append(turn)
        self.total_interactions += 1

        # Trim old turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def get_recent_turns(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get recent conversation turns."""
        return self.turns[-count:] if self.turns else []

    def set_context(self, key: str, value: Any) -> None:
        """Store contextual information."""
        if len(self.context) >= self.max_entries:
            # Remove oldest entry
            oldest_key = next(iter(self.context))
            del self.context[oldest_key]

        self.context[key] = {"value": value, "timestamp": datetime.now()}

    def get_context(self, key: str, default: Any = None) -> Any:
        """Retrieve contextual information."""
        if key in self.context:
            return self.context[key]["value"]
        return default

    def clear_turns(self) -> None:
        """Clear conversation history."""
        self.turns.clear()

    def clear_context(self) -> None:
        """Clear stored context."""
        self.context.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        tool_usage = {}
        if self.turns:
            for turn in self.turns:
                tool = turn["tool"]
                tool_usage[tool] = tool_usage.get(tool, 0) + 1

        return {
            "total_turns": len(self.turns),
            "max_turns": self.max_turns,
            "context_entries": len(self.context),
            "max_entries": self.max_entries,
            "total_interactions": self.total_interactions,
            "created_at": self.created_at.isoformat(),
            "tool_usage": tool_usage,
        }


# ========== Tool Registry ==========


class ToolRegistry:
    """Registry for discovering and managing MCP tools."""

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._tool_classes: Set[type] = set()

    def register(self, tool: MCPTool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def register_class(self, tool_class: type) -> None:
        """Register a tool class for automatic instantiation."""
        if not issubclass(tool_class, MCPTool):
            raise ValueError(f"{tool_class} must be a subclass of MCPTool")
        self._tool_classes.add(tool_class)

    def discover_tools(self) -> None:
        """Discover and register all available tools."""
        # Register built-in tools
        self._register_builtin_tools()

        # Instantiate registered tool classes
        for tool_class in self._tool_classes:
            try:
                tool = tool_class()
                self.register(tool)
            except Exception as e:
                logger.error(f"Failed to instantiate {tool_class.__name__}: {e}")

    def _register_builtin_tools(self) -> None:
        """Register built-in tools."""
        # Register all the concrete tool implementations
        builtin_tools = [
            AskGeminiTool(),
            CodeReviewTool(),
            BrainstormTool(),
            TestCasesTool(),
            ExplainTool(),
        ]

        for tool in builtin_tools:
            self.register(tool)

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_mcp_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions in MCP format."""
        return [tool.get_mcp_definition() for tool in self._tools.values()]


# ========== Conversation Orchestrator ==========


class ConversationOrchestrator:
    """Orchestrates tool execution with caching, memory, and model management."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        model_manager: DualModelManager,
        memory: ConversationMemory,
        cache: ResponseCache,
    ):
        self.tool_registry = tool_registry
        self.model_manager = model_manager
        self.memory = memory
        self.cache = cache
        self.execution_stats = {
            "total_executions": 0,
            "cache_hits": 0,
            "errors": 0,
            "average_duration_ms": 0,
        }

    async def execute_tool(
        self, tool_name: str, parameters: Dict[str, Any], request_id: Optional[str] = None
    ) -> ToolOutput:
        """Execute a tool with full orchestration."""
        start_time = time.time()
        self.execution_stats["total_executions"] += 1

        # Check cache first
        cached_response = self.cache.get(tool_name, parameters)
        if cached_response:
            self.execution_stats["cache_hits"] += 1
            logger.info(f"Cache hit for {tool_name}")

            # Record in memory
            self.memory.add_turn(
                tool=tool_name,
                input_params=parameters,
                output=cached_response,
                metadata={"cached": True, "request_id": request_id},
            )

            return ToolOutput(success=True, result=cached_response)

        # Get the tool
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            self.execution_stats["errors"] += 1
            error_msg = f"Tool not found: {tool_name}"
            logger.error(error_msg)
            return ToolOutput(success=False, error=error_msg)

        try:
            # Execute the tool
            output = await tool.execute(parameters)

            # Cache successful responses
            if output.success and output.result:
                self.cache.set(tool_name, parameters, output.result)

            # Record in memory
            self.memory.add_turn(
                tool=tool_name,
                input_params=parameters,
                output=output.result or output.error or "No output",
                metadata={"cached": False, "request_id": request_id, "success": output.success},
            )

            # Update stats
            duration_ms = (time.time() - start_time) * 1000
            self._update_average_duration(duration_ms)

            return output

        except Exception as e:
            self.execution_stats["errors"] += 1
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)

            error_output = ToolOutput(success=False, error=f"Tool execution failed: {str(e)}")

            # Record error in memory
            self.memory.add_turn(
                tool=tool_name,
                input_params=parameters,
                output=str(e),
                metadata={"cached": False, "request_id": request_id, "error": True},
            )

            return error_output

    def _update_average_duration(self, new_duration_ms: float) -> None:
        """Update rolling average duration."""
        total = self.execution_stats["total_executions"]
        current_avg = self.execution_stats["average_duration_ms"]

        # Calculate new average
        new_avg = ((current_avg * (total - 1)) + new_duration_ms) / total
        self.execution_stats["average_duration_ms"] = new_avg

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        cache_hit_rate = self.execution_stats["cache_hits"] / max(
            1, self.execution_stats["total_executions"]
        )

        return {
            **self.execution_stats,
            "cache_hit_rate": cache_hit_rate,
            "error_rate": (
                self.execution_stats["errors"] / max(1, self.execution_stats["total_executions"])
            ),
        }


# ========== Tool Implementations ==========


class AskGeminiTool(MCPTool):
    """General question tool for Gemini."""

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

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        question = parameters.get("question", "")
        context = parameters.get("context", "")

        if not question:
            return ToolOutput(success=False, error="Question is required")

        prompt = f"Context: {context}\n\n" if context else ""
        prompt += f"Question: {question}"

        # Get model manager from context (will be injected)
        model_manager = getattr(self, "_model_manager", None)
        if not model_manager:
            return ToolOutput(success=False, error="Model manager not available")

        try:
            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🤖 Gemini's Response:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error communicating with Gemini: {str(e)}")


class CodeReviewTool(MCPTool):
    """Code review tool for Gemini."""

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
                    "description": (
                        "Specific aspect to focus on " "(e.g., security, performance, readability)"
                    ),
                    "default": "general",
                },
            },
            "required": ["code"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        code = parameters.get("code", "")
        language = parameters.get("language", "javascript")
        focus = parameters.get("focus", "general")

        if not code:
            return ToolOutput(success=False, error="Code is required")

        focus_str = f" with focus on {focus}" if focus != "general" else ""
        prompt = f"""Please review this {language} code{focus_str}:

```{language}
{code}
```

Provide feedback on:
1. Potential issues or bugs
2. Best practices and improvements
3. Security considerations
4. Performance optimizations
5. Code readability and maintainability"""

        model_manager = getattr(self, "_model_manager", None)
        if not model_manager:
            return ToolOutput(success=False, error="Model manager not available")

        try:
            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🔍 Gemini's Code Review:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error during code review: {str(e)}")


class BrainstormTool(MCPTool):
    """Brainstorming tool for Gemini."""

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

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        topic = parameters.get("topic", "")
        constraints = parameters.get("constraints", "")

        if not topic:
            return ToolOutput(success=False, error="Topic is required")

        prompt = f"Let's brainstorm about: {topic}"
        if constraints:
            prompt += f"\n\nConstraints/Requirements: {constraints}"
        prompt += "\n\nPlease provide creative ideas, approaches, and considerations."

        model_manager = getattr(self, "_model_manager", None)
        if not model_manager:
            return ToolOutput(success=False, error="Model manager not available")

        try:
            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"💡 Gemini's Ideas:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error during brainstorming: {str(e)}")


class TestCasesTool(MCPTool):
    """Test case generation tool for Gemini."""

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

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        code_or_feature = parameters.get("code_or_feature", "")
        test_type = parameters.get("test_type", "all")

        if not code_or_feature:
            return ToolOutput(success=False, error="Code or feature description is required")

        prompt = f"""Suggest {test_type} test cases for:

{code_or_feature}

Please provide:
1. Test case descriptions
2. Expected inputs and outputs
3. Edge cases to consider
4. Potential failure scenarios"""

        model_manager = getattr(self, "_model_manager", None)
        if not model_manager:
            return ToolOutput(success=False, error="Model manager not available")

        try:
            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"🧪 Gemini's Test Suggestions:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error generating test cases: {str(e)}")


class ExplainTool(MCPTool):
    """Explanation tool for Gemini."""

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

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        topic = parameters.get("topic", "")
        level = parameters.get("level", "intermediate")

        if not topic:
            return ToolOutput(success=False, error="Topic is required")

        prompt = f"Please explain the following at a {level} level:\n\n{topic}"

        model_manager = getattr(self, "_model_manager", None)
        if not model_manager:
            return ToolOutput(success=False, error="Model manager not available")

        try:
            response_text, model_used = model_manager.generate_content(prompt)
            formatted_response = f"📚 Gemini's Explanation:\n\n{response_text}"
            if model_used != model_manager.primary_model_name:
                formatted_response += f"\n\n[Model: {model_used}]"
            return ToolOutput(success=True, result=formatted_response)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ToolOutput(success=False, error=f"Error getting explanation: {str(e)}")


# ========== Main Server Implementation ==========


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
            logger.warning("No GEMINI_API_KEY found in environment")
            return False

        try:
            self.model_manager = DualModelManager(api_key)

            # Inject model manager into tools
            for tool_name in self.tool_registry.list_tools():
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    setattr(tool, "_model_manager", self.model_manager)

            # Create orchestrator with all components
            self.orchestrator = ConversationOrchestrator(
                tool_registry=self.tool_registry,
                model_manager=self.model_manager,
                memory=self.memory,
                cache=self.cache,
            )

            return True
        except Exception as e:
            logger.error(f"Failed to initialize model manager: {e}")
            return False

    def _setup_handlers(self):
        """Set up JSON-RPC handlers."""

        # Register handlers
        self.server.register_handler("initialize", self.handle_initialize)
        self.server.register_handler("tools/list", self.handle_tools_list)
        self.server.register_handler("tools/call", self.handle_tool_call)

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialization request."""
        # Load environment variables if available
        if load_dotenv:
            load_dotenv()

        # Initialize model manager
        model_initialized = self._initialize_model_manager()

        # Discover and register all tools
        self.tool_registry.discover_tools()
        logger.info(f"Registered {len(self.tool_registry.list_tools())} tools")

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

        try:
            # Execute through orchestrator (convert async to sync)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                output = loop.run_until_complete(
                    self.orchestrator.execute_tool(
                        tool_name=tool_name, parameters=arguments, request_id=request_id
                    )
                )
            finally:
                loop.close()

            if output.success:
                result = output.result
            else:
                result = f"❌ Error: {output.error or 'Unknown error'}"

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            result = f"❌ Error executing tool: {str(e)}"

        return create_result_response(request_id, {"content": [{"type": "text", "text": result}]})

    def _get_server_info(self) -> str:
        """Get server information and status."""
        info = {
            "version": __version__,
            "architecture": "modular-single-file",
            "components": {
                "tools_registered": len(self.tool_registry.list_tools()),
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

    def run(self):
        """Run the MCP server."""
        logger.info(f"Starting Gemini MCP Server v{__version__} (Modular Single-File)")

        # Configure unbuffered output for proper MCP communication
        sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 1)
        sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 1)

        # Run the JSON-RPC server
        self.server.run()


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
