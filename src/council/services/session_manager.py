"""Session manager for multi-turn AI conversations."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConversationSession:
    """A conversation session with a model."""

    session_id: str
    model: str
    system_prompt: str
    turns: List[ConversationTurn] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_turn(self, role: str, content: str) -> None:
        """Add a turn to the conversation."""
        self.turns.append(ConversationTurn(role=role, content=content))
        self.last_activity = datetime.now()

    def get_message_history(self) -> List[Dict[str, str]]:
        """Get conversation history in OpenAI message format."""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for turn in self.turns:
            messages.append({"role": turn.role, "content": turn.content})
        return messages

    def get_summary(self) -> str:
        """Get a brief summary of the session."""
        turn_count = len(self.turns)
        duration = (self.last_activity - self.created_at).total_seconds()
        first_message = self.turns[0].content[:100] if self.turns else "No messages"
        return (
            f"Session with {self.model}: {turn_count} turns over "
            f"{duration:.0f}s. Started with: '{first_message}...'"
        )


class SessionManager:
    """Manages multiple conversation sessions."""

    def __init__(self, max_sessions: int = 20, max_turns_per_session: int = 50):
        self.sessions: Dict[str, ConversationSession] = {}
        self.max_sessions = max_sessions
        self.max_turns_per_session = max_turns_per_session

    def create_session(
        self,
        model: str,
        system_prompt: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new conversation session.

        Args:
            model: The model to use for this session
            system_prompt: Optional system prompt to set context
            metadata: Optional metadata for the session

        Returns:
            The session ID
        """
        # Clean up old sessions if at capacity
        if len(self.sessions) >= self.max_sessions:
            self._cleanup_oldest_session()

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        self.sessions[session_id] = ConversationSession(
            session_id=session_id,
            model=model,
            system_prompt=system_prompt,
            metadata=metadata or {},
        )
        logger.info(f"Created session {session_id} with model {model}")
        return session_id

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def send_message(self, session_id: str, message: str, model_manager: Any) -> tuple[str, str]:
        """Send a message in a session and get a response.

        Args:
            session_id: The session ID
            message: The user's message
            model_manager: The model manager to use for generation

        Returns:
            Tuple of (response_text, model_used)

        Raises:
            ValueError: If session not found or turn limit exceeded
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if len(session.turns) >= self.max_turns_per_session:
            raise ValueError(
                f"Session {session_id} has reached the maximum of "
                f"{self.max_turns_per_session} turns"
            )

        # Add user message
        session.add_turn("user", message)

        # Build prompt with history
        history = session.get_message_history()
        prompt = self._format_prompt_with_history(history)

        # Generate response
        response_text, model_used = model_manager.generate_content(prompt, model=session.model)

        # Add assistant response
        session.add_turn("assistant", response_text)

        logger.info(f"Session {session_id}: Turn {len(session.turns)//2} completed")
        return response_text, model_used

    def _format_prompt_with_history(self, messages: List[Dict[str, str]]) -> str:
        """Format message history into a prompt string."""
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions with summaries."""
        return [
            {
                "session_id": s.session_id,
                "model": s.model,
                "turns": len(s.turns),
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "preview": s.turns[0].content[:50] if s.turns else "Empty",
            }
            for s in sorted(
                self.sessions.values(),
                key=lambda x: x.last_activity,
                reverse=True,
            )
        ]

    def get_history(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Get conversation history for a session.

        Args:
            session_id: The session ID
            limit: Optional limit on number of turns to return

        Returns:
            List of message dicts with role and content
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        turns = session.turns
        if limit:
            turns = turns[-limit:]

        return [{"role": t.role, "content": t.content} for t in turns]

    def end_session(self, session_id: str, summarize: bool = False) -> str:
        """End a session and optionally return a summary.

        Args:
            session_id: The session ID
            summarize: Whether to return a summary

        Returns:
            Summary string or confirmation message
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        summary = session.get_summary() if summarize else f"Session {session_id} ended"
        del self.sessions[session_id]
        logger.info(f"Ended session {session_id}")
        return summary

    def _cleanup_oldest_session(self) -> None:
        """Remove the oldest session to make room for new ones."""
        if not self.sessions:
            return
        oldest_id = min(
            self.sessions.keys(),
            key=lambda k: self.sessions[k].last_activity,
        )
        logger.warning(f"Cleaning up oldest session {oldest_id} to make room")
        del self.sessions[oldest_id]

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        total_turns = sum(len(s.turns) for s in self.sessions.values())
        return {
            "active_sessions": len(self.sessions),
            "max_sessions": self.max_sessions,
            "total_turns": total_turns,
            "max_turns_per_session": self.max_turns_per_session,
        }
