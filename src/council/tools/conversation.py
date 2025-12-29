"""Tools for multi-turn conversations with AI models."""

import logging
from typing import Any, Dict

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)

# Global session manager instance (initialized by server)
_session_manager = None


def get_session_manager():
    """Get or create the session manager instance."""
    global _session_manager
    if _session_manager is None:
        from ..services.session_manager import SessionManager

        _session_manager = SessionManager()
    return _session_manager


class StartConversationTool(MCPTool):
    """Tool to start a new conversation session with a model."""

    @property
    def name(self) -> str:
        return "start_conversation"

    @property
    def description(self) -> str:
        return (
            "Start a new multi-turn conversation session with an AI model. "
            "Returns a session_id to use for follow-up messages."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": (
                        "The model to converse with (e.g., 'deepseek/deepseek-r1', "
                        "'anthropic/claude-3-haiku'). Use list_models to see options."
                    ),
                },
                "system_prompt": {
                    "type": "string",
                    "description": (
                        "Optional system prompt to set the model's role/context "
                        "(e.g., 'You are a Python expert specializing in async programming')"
                    ),
                    "default": "",
                },
                "initial_message": {
                    "type": "string",
                    "description": ("Optional first message to send immediately after starting"),
                },
            },
            "required": ["model"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Start a new conversation session."""
        try:
            model = parameters.get("model")
            if not model:
                return ToolOutput(success=False, error="Model is required")

            system_prompt = parameters.get("system_prompt", "")
            initial_message = parameters.get("initial_message")

            session_manager = get_session_manager()
            session_id = session_manager.create_session(
                model=model,
                system_prompt=system_prompt,
            )

            result_lines = [
                "✅ **Conversation Started**",
                "",
                f"**Session ID:** `{session_id}`",
                f"**Model:** {model}",
            ]

            if system_prompt:
                result_lines.append(f"**System Prompt:** {system_prompt[:100]}...")

            # If initial message provided, send it
            if initial_message:
                try:
                    from .. import _server_instance

                    if _server_instance and _server_instance.model_manager:
                        response, model_used = session_manager.send_message(
                            session_id, initial_message, _server_instance.model_manager
                        )
                        result_lines.extend(
                            [
                                "",
                                "---",
                                f"**You:** {initial_message}",
                                "",
                                f"**{model}:** {response}",
                            ]
                        )
                except Exception as e:
                    result_lines.append(f"\n⚠️ Initial message failed: {e}")

            result_lines.extend(
                [
                    "",
                    f"💡 Use `continue_conversation` with session_id `{session_id}` to continue.",
                ]
            )

            return ToolOutput(success=True, result="\n".join(result_lines))

        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")


class ContinueConversationTool(MCPTool):
    """Tool to continue an existing conversation session."""

    @property
    def name(self) -> str:
        return "continue_conversation"

    @property
    def description(self) -> str:
        return (
            "Send a message in an existing conversation session. "
            "The model will have full context of previous messages."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID from start_conversation",
                },
                "message": {
                    "type": "string",
                    "description": "Your message to send",
                },
            },
            "required": ["session_id", "message"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Continue a conversation."""
        try:
            session_id = parameters.get("session_id")
            message = parameters.get("message")

            if not session_id:
                return ToolOutput(success=False, error="session_id is required")
            if not message:
                return ToolOutput(success=False, error="message is required")

            session_manager = get_session_manager()
            session = session_manager.get_session(session_id)

            if not session:
                return ToolOutput(
                    success=False,
                    error=f"Session {session_id} not found. "
                    "Use list_conversations to see active sessions.",
                )

            # Get model manager
            try:
                from .. import _server_instance

                if not _server_instance or not _server_instance.model_manager:
                    raise AttributeError("Model manager not available")
                model_manager = _server_instance.model_manager
            except (ImportError, AttributeError):
                model_manager = globals().get("model_manager")
                if not model_manager:
                    return ToolOutput(success=False, error="Model manager not available")

            response, model_used = session_manager.send_message(session_id, message, model_manager)

            turn_count = len(session.turns) // 2
            result = (
                f"**Turn {turn_count}** (Session: `{session_id}`)\n\n"
                f"**You:** {message}\n\n"
                f"**{session.model}:** {response}\n\n"
                f"[Model: {model_used}]"
            )

            return ToolOutput(success=True, result=result)

        except ValueError as e:
            return ToolOutput(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error in conversation: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")


class ListConversationsTool(MCPTool):
    """Tool to list active conversation sessions."""

    @property
    def name(self) -> str:
        return "list_conversations"

    @property
    def description(self) -> str:
        return "List all active conversation sessions with their status and preview."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """List active conversations."""
        try:
            session_manager = get_session_manager()
            sessions = session_manager.list_sessions()
            stats = session_manager.get_stats()

            if not sessions:
                return ToolOutput(
                    success=True,
                    result=(
                        "📭 **No active conversations**\n\n"
                        "Use `start_conversation` to begin a new session."
                    ),
                )

            result_lines = [
                f"📋 **Active Conversations** ({stats['active_sessions']}/{stats['max_sessions']})",
                "",
            ]

            for s in sessions:
                result_lines.extend(
                    [
                        f"### `{s['session_id']}`",
                        f"- **Model:** {s['model']}",
                        f"- **Turns:** {s['turns']}",
                        f"- **Last Activity:** {s['last_activity']}",
                        f"- **Preview:** _{s['preview']}_...",
                        "",
                    ]
                )

            result_lines.append("💡 Use `continue_conversation` with a session_id to resume.")

            return ToolOutput(success=True, result="\n".join(result_lines))

        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")


class EndConversationTool(MCPTool):
    """Tool to end a conversation session."""

    @property
    def name(self) -> str:
        return "end_conversation"

    @property
    def description(self) -> str:
        return "End a conversation session. Optionally get a summary of the conversation."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to end",
                },
                "summarize": {
                    "type": "boolean",
                    "description": "Whether to return a summary of the conversation",
                    "default": True,
                },
            },
            "required": ["session_id"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """End a conversation session."""
        try:
            session_id = parameters.get("session_id")
            summarize = parameters.get("summarize", True)

            if not session_id:
                return ToolOutput(success=False, error="session_id is required")

            session_manager = get_session_manager()
            summary = session_manager.end_session(session_id, summarize=summarize)

            return ToolOutput(
                success=True,
                result=f"✅ **Conversation Ended**\n\n{summary}",
            )

        except ValueError as e:
            return ToolOutput(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error ending conversation: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")


class GetConversationHistoryTool(MCPTool):
    """Tool to get the history of a conversation."""

    @property
    def name(self) -> str:
        return "get_conversation_history"

    @property
    def description(self) -> str:
        return "Get the full message history of a conversation session."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID",
                },
                "limit": {
                    "type": "integer",
                    "description": "Limit to last N turns (optional)",
                },
            },
            "required": ["session_id"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Get conversation history."""
        try:
            session_id = parameters.get("session_id")
            limit = parameters.get("limit")

            if not session_id:
                return ToolOutput(success=False, error="session_id is required")

            session_manager = get_session_manager()
            session = session_manager.get_session(session_id)

            if not session:
                return ToolOutput(success=False, error=f"Session {session_id} not found")

            history = session_manager.get_history(session_id, limit=limit)

            result_lines = [
                f"📜 **Conversation History** (`{session_id}`)",
                f"**Model:** {session.model}",
                "",
            ]

            if session.system_prompt:
                result_lines.extend(
                    [
                        f"**System:** {session.system_prompt}",
                        "",
                        "---",
                        "",
                    ]
                )

            for i, turn in enumerate(history):
                role = "You" if turn["role"] == "user" else session.model
                result_lines.append(f"**{role}:** {turn['content']}")
                result_lines.append("")

            return ToolOutput(success=True, result="\n".join(result_lines))

        except ValueError as e:
            return ToolOutput(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")
