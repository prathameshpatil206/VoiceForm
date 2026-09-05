from abc import ABC, abstractmethod
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.actions import FillAction, FillResult
from app.schemas.form import PageScanResult

class ConversationTurn(BaseModel):
    generation_id: int
    status: str = "PENDING"  # PENDING, PROCESSING, SPEAKING, COMPLETED, INTERRUPTED, CANCELLED, ERROR
    user_utterance: Optional[str] = None
    transcript: Optional[str] = None
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    assistant_response: Optional[str] = None
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    completed_at: Optional[int] = None

class SessionState(BaseModel):
    session_id: str
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    last_active_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    schema_data: Optional[PageScanResult] = None
    actions_history: List[FillAction] = Field(default_factory=list)
    results_history: List[FillResult] = Field(default_factory=list)

    # Milestone 4: AI & Conversation State
    current_field_values: Dict[str, Any] = Field(default_factory=dict)
    latest_transcript: Optional[str] = None
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    processing_state: str = "IDLE"

    # Milestone 5: TTS State
    latest_assistant_response: Optional[str] = None
    current_tts_request_id: Optional[str] = None
    tts_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Milestone 6: Interruption, Recovery & Generation Synchronization
    current_generation_id: int = 0
    conversation_state: str = "IDLE"  # IDLE, LISTENING, PROCESSING, SPEAKING, INTERRUPTED, ERROR
    turns: List[ConversationTurn] = Field(default_factory=list)

class SessionStore(ABC):
    """
    Abstract interface for VoiceForm session persistence.
    Enables zero-friction replacement of in-memory store with PostgreSQL/Redis in M7.
    """

    @abstractmethod
    async def create_session(
        self, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> SessionState:
        """Create a new session state."""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """Retrieve a session by its ID."""
        pass

    @abstractmethod
    async def update_schema(
        self, session_id: str, schema: PageScanResult
    ) -> Optional[SessionState]:
        """Update or store the latest scanned page schema for this session."""
        pass

    @abstractmethod
    async def record_action(
        self, session_id: str, action: FillAction
    ) -> Optional[SessionState]:
        """Append an outgoing action dispatched to the client."""
        pass

    @abstractmethod
    async def record_result(
        self, session_id: str, result: FillResult
    ) -> Optional[SessionState]:
        """Record the client's execution outcome for an action."""
        pass

    @abstractmethod
    async def update_field_value(
        self, session_id: str, field_id: str, value: Any
    ) -> Optional[SessionState]:
        """Record current user or filled value for a field."""
        pass

    @abstractmethod
    async def record_transcript(
        self, session_id: str, transcript: str
    ) -> Optional[SessionState]:
        """Record the latest user speech transcript."""
        pass

    @abstractmethod
    async def append_conversation(
        self, session_id: str, role: str, content: str
    ) -> Optional[SessionState]:
        """Record a turn in the dialogue history."""
        pass

    @abstractmethod
    async def record_assistant_response(
        self, session_id: str, response: str
    ) -> Optional[SessionState]:
        """Record the latest spoken response generated for the user."""
        pass

    @abstractmethod
    async def record_tts_event(
        self, session_id: str, request_id: str, event_type: str, details: Optional[Dict[str, Any]] = None
    ) -> Optional[SessionState]:
        """Record a TTS lifecycle event (e.g. started, finished, cancelled, error)."""
        pass

    @abstractmethod
    async def set_processing_state(
        self, session_id: str, state: str
    ) -> Optional[SessionState]:
        """Update current AI processing lifecycle status."""
        pass

    # Milestone 6 Generation & Turn Methods
    @abstractmethod
    async def next_generation(self, session_id: str) -> int:
        """Monotonically increments and returns the new generation ID for this session."""
        pass

    @abstractmethod
    async def get_current_generation(self, session_id: str) -> int:
        """Returns the active generation ID for the session."""
        pass

    @abstractmethod
    async def create_turn(self, session_id: str, generation_id: Optional[int] = None) -> ConversationTurn:
        """Creates and attaches a new ConversationTurn to the session."""
        pass

    @abstractmethod
    async def update_turn(
        self,
        session_id: str,
        generation_id: int,
        status: Optional[str] = None,
        user_utterance: Optional[str] = None,
        transcript: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        assistant_response: Optional[str] = None
    ) -> Optional[ConversationTurn]:
        """Updates an existing turn for a specific generation ID."""
        pass

    @abstractmethod
    async def set_conversation_state(
        self, session_id: str, state: str
    ) -> Optional[SessionState]:
        """Updates the conversation state machine state (IDLE, LISTENING, PROCESSING, SPEAKING, INTERRUPTED, ERROR)."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Remove a session."""
        pass

    @abstractmethod
    async def list_sessions(self) -> List[SessionState]:
        """List all active sessions."""
        pass
