#!/usr/bin/env python3
"""
Gemini Collaboration MCP Server for Claude Code
Provides tools for Claude to collaborate with Google's Gemini AI
Enhanced with dual-model support and automatic fallback
"""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from typing import Any, Dict, Tuple

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# Note: stdout/stderr are configured for unbuffered output in main()

# Set up logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("gemini-mcp")

# Server version info
__version__ = "2.1.0"
__updated__ = "2025-06-12"

# JSON-RPC constants
JSONRPC_VERSION = "2.0"
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INTERNAL = -32603
ERROR_INVALID_PARAMS = -32602


class DualModelManager:
    """Manages primary and fallback Gemini models"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.primary_model = None
        self.fallback_model = None
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
            self.primary_model = genai.GenerativeModel(self.primary_model_name)
            logger.info(f"Primary model initialized: {self.primary_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize primary model {self.primary_model_name}: {e}")

        try:
            self.fallback_model = genai.GenerativeModel(self.fallback_model_name)
            logger.info(f"Fallback model initialized: {self.fallback_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize fallback model {self.fallback_model_name}: {e}")

        # If primary failed but fallback succeeded, swap them
        if not self.primary_model and self.fallback_model:
            self.primary_model = self.fallback_model
            self.primary_model_name = self.fallback_model_name
            self.fallback_model = None
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

        if not self.primary_model and not self.fallback_model:
            raise RuntimeError("No models available")

        # Try primary model first
        if self.primary_model:
            try:
                start_time = time.time()
                response_text = self._generate_with_timeout(
                    self.primary_model, self.primary_model_name, prompt, self.timeout
                )
                elapsed = time.time() - start_time
                logger.info(f"Primary model responded in {elapsed:.2f}s")
                self.call_stats["primary_success"] += 1
                return response_text, self.primary_model_name

            except (google_exceptions.GoogleAPICallError, ValueError, TimeoutError) as e:
                logger.error(f"Primary model failed: {e}")
                self.call_stats["primary_failure"] += 1
                if not self.fallback_model:
                    raise RuntimeError("Primary model failed with no fallback available") from e

        # Try fallback model
        if self.fallback_model:
            try:
                logger.info("Falling back to secondary model")
                response_text = self._generate_with_timeout(
                    self.fallback_model,
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
                "available": self.primary_model is not None,
            },
            "fallback": {
                "name": self.fallback_model_name,
                "available": self.fallback_model is not None,
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


class ConversationMemory:
    """Simple in-memory storage for conversation context"""

    def __init__(self, max_size: int = 100):
        self.data: Dict[str, Any] = {}
        self.max_size = max_size
        self.created_at = datetime.now()
        self.access_count = 0

    def set(self, key: str, value: Any) -> None:
        """Store a value with a key"""
        if len(self.data) >= self.max_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self.data))
            del self.data[oldest_key]
        self.data[key] = {"value": value, "timestamp": datetime.now(), "access_count": 0}
        self.access_count += 1

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key"""
        if key in self.data:
            self.data[key]["access_count"] += 1
            self.access_count += 1
            return self.data[key]["value"]
        return default

    def clear(self) -> None:
        """Clear all stored data"""
        self.data.clear()
        self.access_count = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        return {
            "size": len(self.data),
            "max_size": self.max_size,
            "total_accesses": self.access_count,
            "created_at": self.created_at.isoformat(),
            "keys": list(self.data.keys()),
        }


class GeminiMCPServer:
    def __init__(self):
        self.model_manager = None
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.conversation_history = []
        self.memory = ConversationMemory()

        if self.api_key:
            try:
                self.model_manager = DualModelManager(self.api_key)
                logger.info("Dual-model Gemini API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
        else:
            logger.warning("GEMINI_API_KEY not found in environment variables")

    def send_response(self, response: Dict[str, Any]):
        """Send a JSON-RPC response"""
        print(json.dumps(response), flush=True)
        logger.debug(f"Sent response: {response.get('id', 'no-id')}")

    def handle_initialize(self, request_id: Any) -> Dict[str, Any]:
        """Handle initialization request"""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "gemini-collab", "version": __version__},
            },
        }

    def handle_tools_list(self, request_id: Any) -> Dict[str, Any]:
        """List available tools"""
        tools = [
            {
                "name": "ask_gemini",
                "description": "Ask Gemini a general question or for help with a problem",
                "inputSchema": {
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
                },
            },
            {
                "name": "gemini_code_review",
                "description": (
                    "Ask Gemini to review code for issues, improvements, or best practices"
                ),
                "inputSchema": {
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
                                "Specific aspect to focus on "
                                "(e.g., security, performance, readability)"
                            ),
                            "default": "general",
                        },
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "gemini_brainstorm",
                "description": "Brainstorm ideas or solutions with Gemini",
                "inputSchema": {
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
                },
            },
            {
                "name": "gemini_test_cases",
                "description": "Ask Gemini to suggest test cases for code or features",
                "inputSchema": {
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
                },
            },
            {
                "name": "gemini_explain",
                "description": "Ask Gemini to explain complex code or concepts",
                "inputSchema": {
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
                },
            },
            {
                "name": "synthesize_perspectives",
                "description": "Synthesize multiple perspectives into a unified analysis",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The topic or question being analyzed",
                        },
                        "perspectives": {
                            "type": "array",
                            "description": "Array of different perspectives to synthesize",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source": {
                                        "type": "string",
                                        "description": "Source or viewpoint label",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "The perspective content",
                                    },
                                },
                                "required": ["source", "content"],
                            },
                        },
                    },
                    "required": ["topic", "perspectives"],
                },
            },
            {
                "name": "server_info",
                "description": "Get server version and status",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}

    def handle_tool_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "server_info":
                result = self._server_info()
            elif not self.model_manager:
                result = (
                    "❌ Gemini API not initialized. Please set GEMINI_API_KEY environment variable."
                )
            elif tool_name == "ask_gemini":
                result = self._ask_gemini(arguments.get("question"), arguments.get("context", ""))
            elif tool_name == "gemini_code_review":
                result = self._code_review(
                    arguments.get("code"),
                    arguments.get("language", "javascript"),
                    arguments.get("focus", "general"),
                )
            elif tool_name == "gemini_brainstorm":
                result = self._brainstorm(arguments.get("topic"), arguments.get("constraints", ""))
            elif tool_name == "gemini_test_cases":
                result = self._suggest_test_cases(
                    arguments.get("code_or_feature"), arguments.get("test_type", "all")
                )
            elif tool_name == "gemini_explain":
                result = self._explain(
                    arguments.get("topic"), arguments.get("level", "intermediate")
                )
            elif tool_name == "synthesize_perspectives":
                result = self._synthesize_perspectives(
                    arguments.get("topic"), arguments.get("perspectives", [])
                )
            else:
                raise ValueError(f"Unknown tool: {tool_name}")

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }
        except Exception as e:
            logger.error(f"Error in tool {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _server_info(self) -> str:
        """Get server information"""
        if self.model_manager:
            model_status = self.model_manager.get_status()
            perf_stats = self.model_manager.get_stats()

            primary_status = "✅" if model_status["primary"]["available"] else "❌"
            fallback_status = "✅" if model_status["fallback"]["available"] else "❌"

            status_lines = [
                f"Primary Model: {model_status['primary']['name']} ({primary_status})",
                f"Fallback Model: {model_status['fallback']['name']} ({fallback_status})",
                f"Timeout: {model_status['timeout']}s",
                "\nPerformance Stats:",
                f"Total Calls: {perf_stats['total_calls']}",
                f"Primary Success Rate: {perf_stats['primary_success_rate']:.1%}",
                f"Fallback Usage Rate: {perf_stats['fallback_usage_rate']:.1%}",
                "\nMemory Stats:",
                f"Stored Items: {len(self.memory.data)}/{self.memory.max_size}",
                f"Total Accesses: {self.memory.access_count}",
            ]
            status_text = "\n".join(status_lines)
        else:
            status_text = "❌ No API Key"

        tools_list = [
            "ask_gemini",
            "gemini_code_review",
            "gemini_brainstorm",
            "gemini_test_cases",
            "gemini_explain",
            "synthesize_perspectives",
        ]

        return f"""Gemini Collaboration Server v{__version__}
Updated: {__updated__}
Status:
{status_text}
Available Tools: {', '.join(tools_list)}"""

    def _format_response(self, response_text: str, model_used: str) -> str:
        """Format response with model information"""
        model_indicator = (
            f"\n\n[Model: {model_used}]"
            if model_used != self.model_manager.primary_model_name
            else ""
        )
        return response_text + model_indicator

    def _ask_gemini(self, question: str, context: str = "") -> str:
        """Ask Gemini a general question"""
        prompt = f"Context: {context}\n\n" if context else ""
        prompt += f"Question: {question}"

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            formatted_response = self._format_response(response_text, model_used)
            return f"🤖 Gemini's Response:\n\n{formatted_response}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error communicating with Gemini: {str(e)}"

    def _code_review(self, code: str, language: str, focus: str) -> str:
        """Review code with Gemini"""
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

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            formatted_response = self._format_response(response_text, model_used)
            return f"🔍 Gemini's Code Review:\n\n{formatted_response}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error during code review: {str(e)}"

    def _brainstorm(self, topic: str, constraints: str = "") -> str:
        """Brainstorm with Gemini"""
        prompt = f"Let's brainstorm about: {topic}"
        if constraints:
            prompt += f"\n\nConstraints/Requirements: {constraints}"
        prompt += "\n\nPlease provide creative ideas, approaches, and considerations."

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            formatted_response = self._format_response(response_text, model_used)
            return f"💡 Gemini's Ideas:\n\n{formatted_response}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error during brainstorming: {str(e)}"

    def _suggest_test_cases(self, code_or_feature: str, test_type: str) -> str:
        """Suggest test cases with Gemini"""
        prompt = f"""Suggest {test_type} test cases for:

{code_or_feature}

Please provide:
1. Test case descriptions
2. Expected inputs and outputs
3. Edge cases to consider
4. Potential failure scenarios"""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            formatted_response = self._format_response(response_text, model_used)
            return f"🧪 Gemini's Test Suggestions:\n\n{formatted_response}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error generating test cases: {str(e)}"

    def _explain(self, topic: str, level: str) -> str:
        """Get explanations from Gemini"""
        prompt = f"Please explain the following at a {level} level:\n\n{topic}"

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            formatted_response = self._format_response(response_text, model_used)
            return f"📚 Gemini's Explanation:\n\n{formatted_response}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error getting explanation: {str(e)}"

    def _synthesize_perspectives(self, topic: str, perspectives: list) -> str:
        """Synthesize multiple perspectives into a unified analysis"""
        if not perspectives:
            return "❌ No perspectives provided to synthesize"

        # Build the prompt
        perspectives_text = "\n\n".join(
            [f"**{p['source']}**: {p['content']}" for p in perspectives]
        )

        prompt = f"""Please analyze and synthesize the following perspectives on this topic:

Topic: {topic}

Perspectives:
{perspectives_text}

Please provide:
1. A synthesis that integrates all viewpoints
2. Key agreements across perspectives
3. Key disagreements or tensions
4. A balanced recommendation or conclusion
5. Any unresolved questions or areas needing further exploration"""

        try:
            response_text, model_used = self.model_manager.generate_content(prompt)
            formatted_response = self._format_response(response_text, model_used)

            # Store synthesis in memory for potential follow-up
            self.memory.set(
                f"synthesis_{topic[:30]}",
                {
                    "topic": topic,
                    "perspectives": perspectives,
                    "synthesis": response_text,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            return f"🤝 Synthesized Analysis:\n\n{formatted_response}"
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"❌ Error synthesizing perspectives: {str(e)}"

    def run(self):
        """Main server loop"""
        logger.info("Gemini MCP Server started with dual-model support")

        while True:
            request_id = None  # Initialize to avoid reference errors
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line.strip())
                method = request.get("method")
                request_id = request.get("id")
                params = request.get("params", {})

                logger.debug(f"Received request: {method} (id: {request_id})")

                if method == "initialize":
                    response = self.handle_initialize(request_id)
                elif method == "tools/list":
                    response = self.handle_tools_list(request_id)
                elif method == "tools/call":
                    response = self.handle_tool_call(request_id, params)
                else:
                    response = {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": request_id,
                        "error": {
                            "code": ERROR_METHOD_NOT_FOUND,
                            "message": f"Method not found: {method}",
                        },
                    }

                self.send_response(response)

            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                continue
            except EOFError:
                logger.info("EOF reached, shutting down")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if request_id is not None:
                    self.send_response(
                        {
                            "jsonrpc": JSONRPC_VERSION,
                            "id": request_id,
                            "error": {
                                "code": ERROR_INTERNAL,
                                "message": f"Internal error: {str(e)}",
                            },
                        }
                    )


def main():
    """Main entry point for the server"""
    # Configure unbuffered output for proper MCP communication
    sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 1)

    server = GeminiMCPServer()
    server.run()


if __name__ == "__main__":
    main()
