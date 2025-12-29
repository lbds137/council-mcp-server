"""Debug tool for structured debugging with hypothesis tracking."""

import logging
from typing import Any, Dict, List, Optional

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)


class DebugTool(MCPTool):
    """Tool for structured debugging with hypothesis ranking and verification guidance."""

    @property
    def name(self) -> str:
        return "debug"

    @property
    def description(self) -> str:
        return (
            "Analyze an error or bug with structured hypothesis generation. "
            "Provides ranked probable causes, verification steps, and recommended next actions. "
            "Tracks previous attempts to prevent circular debugging."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "error_message": {
                    "type": "string",
                    "description": "The error message or symptom description",
                },
                "code_context": {
                    "type": "string",
                    "description": "Relevant code where the error occurs",
                },
                "stack_trace": {
                    "type": "string",
                    "description": "Stack trace if available",
                },
                "previous_attempts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of fixes already tried that didn't work",
                },
                "environment": {
                    "type": "string",
                    "description": "Runtime environment (e.g., 'Python 3.13', 'Node 20')",
                    "default": "Python 3.x",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Optional session ID from start_conversation to track "
                        "debugging history across multiple debug calls"
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Optional model override (e.g., 'anthropic/claude-3-opus'). "
                        "Use list_models to see available options."
                    ),
                },
            },
            "required": ["error_message", "code_context"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute structured debugging analysis."""
        try:
            error_message = parameters.get("error_message")
            code_context = parameters.get("code_context")

            if not error_message:
                return ToolOutput(success=False, error="error_message is required")
            if not code_context:
                return ToolOutput(success=False, error="code_context is required")

            stack_trace = parameters.get("stack_trace", "")
            previous_attempts = parameters.get("previous_attempts", [])
            environment = parameters.get("environment", "Python 3.x")
            session_id = parameters.get("session_id")
            model_override = parameters.get("model")

            # Get debugging history from session if available
            session_context = ""
            if session_id:
                session_context = self._get_session_context(session_id)

            # Build the prompt
            prompt = self._build_prompt(
                error_message=error_message,
                code_context=code_context,
                stack_trace=stack_trace,
                previous_attempts=previous_attempts,
                environment=environment,
                session_context=session_context,
            )

            # Get model manager
            try:
                from .. import _server_instance

                if _server_instance and _server_instance.model_manager:
                    model_manager = _server_instance.model_manager
                else:
                    raise AttributeError("Server instance not available")
            except (ImportError, AttributeError):
                model_manager = globals().get("model_manager")
                if not model_manager:
                    return ToolOutput(success=False, error="Model manager not available")

            response_text, model_used = model_manager.generate_content(prompt, model=model_override)

            # Format response
            formatted_response = self._format_response(
                response_text,
                model_used,
                session_id,
                len(previous_attempts),
            )

            return ToolOutput(success=True, result=formatted_response)

        except Exception as e:
            logger.error(f"Debug tool error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    def _get_session_context(self, session_id: str) -> str:
        """Get previous debugging context from session if available."""
        try:
            from .conversation import get_session_manager

            session_manager = get_session_manager()
            session = session_manager.get_session(session_id)

            if session and session.turns:
                # Extract recent debugging history
                recent_turns = session.turns[-6:]  # Last 3 exchanges
                context_parts = ["## Previous Debugging Context"]
                for turn in recent_turns:
                    role = "User" if turn.role == "user" else "Assistant"
                    # Truncate long content
                    content = (
                        turn.content[:500] + "..." if len(turn.content) > 500 else turn.content
                    )
                    context_parts.append(f"**{role}:** {content}")
                return "\n\n".join(context_parts)
        except Exception as e:
            logger.debug(f"Could not get session context: {e}")

        return ""

    def _build_prompt(
        self,
        error_message: str,
        code_context: str,
        stack_trace: str,
        previous_attempts: List[str],
        environment: str,
        session_context: str,
    ) -> str:
        """Build the structured debugging prompt."""
        parts = [
            "You are a senior debugging expert. Analyze the following error and provide "
            "a structured debugging analysis with ranked hypotheses.",
            "",
            "## Environment",
            environment,
            "",
            "## Error Message",
            "```",
            error_message,
            "```",
            "",
            "## Code Context",
            "```",
            code_context,
            "```",
        ]

        if stack_trace:
            parts.extend(
                [
                    "",
                    "## Stack Trace",
                    "```",
                    f"{stack_trace}",
                    "```",
                ]
            )

        if previous_attempts:
            parts.extend(
                [
                    "",
                    "## Previous Attempts (Already Tried)",
                    "The following fixes have been attempted but DID NOT solve the issue:",
                ]
            )
            for i, attempt in enumerate(previous_attempts, 1):
                parts.append(f"{i}. {attempt}")
            parts.append("")
            parts.append("**Important:** Do NOT suggest these approaches again.")

        if session_context:
            parts.extend(
                [
                    "",
                    session_context,
                ]
            )

        parts.extend(
            [
                "",
                "## Required Output Format",
                "",
                "Provide your analysis in this exact structure:",
                "",
                "### Root Cause Analysis",
                "[Explain the most likely root cause based on the evidence. "
                "Be specific about what's happening and why.]",
                "",
                "### Hypotheses (Ranked by Probability)",
                "",
                "**1. [Most Likely Cause]** (Confidence: High/Medium/Low)",
                "- Evidence: [What points to this being the issue]",
                "- Verification: [Concrete step to confirm this is the cause]",
                "- Fix Strategy: [High-level approach, not full implementation yet]",
                "",
                "**2. [Second Most Likely]** (Confidence: High/Medium/Low)",
                "[Same structure...]",
                "",
                "(Provide 2-4 hypotheses)",
                "",
                "### Recommended Next Step",
                "[Single, concrete action to take RIGHT NOW to make progress. "
                "Focus on verification before fix.]",
                "",
                "### What NOT to Try",
                "[Anti-patterns or approaches that won't work for this specific issue, "
                "especially based on previous attempts]",
            ]
        )

        return "\n".join(parts)

    def _format_response(
        self,
        response_text: str,
        model_used: str,
        session_id: Optional[str],
        attempt_count: int,
    ) -> str:
        """Format the debugging response."""
        header_parts = ["# Debugging Analysis"]

        if attempt_count > 0:
            header_parts.append(f"*Attempt #{attempt_count + 1}*")

        if session_id:
            header_parts.append(f"*Session: `{session_id}`*")

        header = " | ".join(header_parts)

        return f"{header}\n\n{response_text}\n\n[Model: {model_used}]"
