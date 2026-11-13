"""Privacy-Compliant Ephemeral Session Memory (30-minute TTL).

Enforces Taiwan PDPA privacy rules:
- Ephemeral in-memory session tracking with 30-minute timeout.
- Instant data purge via /forget or /opt_out commands.
- Zero persistent cross-session profiling.
"""

from typing import Dict, List, Optional, Any
import time
from pydantic import BaseModel, Field


class MessageTurn(BaseModel):
    """Single turn of student interaction."""
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: float = Field(default_factory=time.time)


class SessionState(BaseModel):
    """Stateful session container with TTL expiration."""
    session_id: str
    created_at: float = Field(default_factory=time.time)
    last_active: float = Field(default_factory=time.time)
    fsm_state: str = "DISCOVERY"
    detected_lang: str = "en"
    history: List[MessageTurn] = Field(default_factory=list)
    slots: Dict[str, Any] = Field(default_factory=dict)
    pending_action: Optional[Dict[str, Any]] = None

    def is_expired(self, ttl_seconds: float = 1800.0) -> bool:
        """Checks if session has been inactive for longer than TTL (default 30 mins)."""
        return (time.time() - self.last_active) > ttl_seconds

    def touch(self) -> None:
        """Updates last active timestamp."""
        self.last_active = time.time()


class SessionMemoryManager:
    """Manages ephemeral in-memory sessions with automatic eviction and manual purge."""

    def __init__(self, ttl_seconds: float = 1800.0):
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, SessionState] = {}

    def get_or_create(self, session_id: str) -> SessionState:
        """Retrieves active session or creates a new one, evicting expired ones."""
        self._cleanup_expired()
        
        session = self._sessions.get(session_id)
        if not session or session.is_expired(self.ttl_seconds):
            session = SessionState(session_id=session_id)
            self._sessions[session_id] = session
        else:
            session.touch()
            
        return session

    def record_turn(self, session_id: str, role: str, content: str) -> None:
        """Records an interaction turn in the active session."""
        session = self.get_or_create(session_id)
        session.history.append(MessageTurn(role=role, content=content))
        session.touch()

    def set_pending_action(self, session_id: str, action_data: Dict[str, Any]) -> None:
        """Stores a pending action proposal awaiting explicit user confirmation."""
        session = self.get_or_create(session_id)
        session.pending_action = action_data
        session.fsm_state = "AWAITING_CONFIRMATION"
        session.touch()

    def get_pending_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves currently pending action proposal if present and unexpired."""
        session = self.get_or_create(session_id)
        return session.pending_action

    def clear_pending_action(self, session_id: str) -> None:
        """Clears pending action proposal following execution or cancellation rollback."""
        session = self.get_or_create(session_id)
        session.pending_action = None
        session.touch()

    def purge_session(self, session_id: str) -> bool:
        """Purges session immediately upon /forget or /opt_out command."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def active_session_count(self) -> int:
        """Returns number of non-expired sessions."""
        self._cleanup_expired()
        return len(self._sessions)

    def _cleanup_expired(self) -> None:
        """Removes all expired sessions from memory."""
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if (now - s.last_active) > self.ttl_seconds]
        for sid in expired:
            del self._sessions[sid]
