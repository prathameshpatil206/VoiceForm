import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from app.schemas.actions import FillAction, FillResult
from app.schemas.form import PageScanResult
from app.store.base import ConversationTurn, SessionState, SessionStore

class InMemorySessionStore(SessionStore):
    """
    Async-safe, in-memory implementation of SessionStore for early vertical slices.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> SessionState:
        async with self._lock:
            sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
            if sid in self._sessions:
                # Update last active if already exists
                session = self._sessions[sid]
                session.last_active_at = int(time.time() * 1000)
                if metadata:
                    session.metadata.update(metadata)
                return session

            session = SessionState(
                session_id=sid,
                metadata=metadata or {},
                created_at=int(time.time() * 1000),
                last_active_at=int(time.time() * 1000),
                current_generation_id=0,
                conversation_state="IDLE"
            )
            self._sessions[sid] = session
            return session

    async def get_session(self, session_id: str) -> Optional[SessionState]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_active_at = int(time.time() * 1000)
            return session

    async def update_schema(
        self, session_id: str, schema: PageScanResult
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.schema_data = schema
            session.last_active_at = int(time.time() * 1000)
            return session

    async def record_action(
        self, session_id: str, action: FillAction
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.actions_history.append(action)
            session.last_active_at = int(time.time() * 1000)
            return session

    async def record_result(
        self, session_id: str, result: FillResult
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.results_history.append(result)
            if result.field_id and result.success and result.newValue is not None:
                session.current_field_values[result.field_id] = result.newValue
            session.last_active_at = int(time.time() * 1000)
            return session

    async def update_field_value(
        self, session_id: str, field_id: str, value: Any
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.current_field_values[field_id] = value
            session.last_active_at = int(time.time() * 1000)
            return session

    async def record_transcript(
        self, session_id: str, transcript: str
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.latest_transcript = transcript
            session.last_active_at = int(time.time() * 1000)
            return session

    async def append_conversation(
        self, session_id: str, role: str, content: str
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.conversation_history.append({
                "role": role,
                "content": content,
                "timestamp": int(time.time() * 1000)
            })
            session.last_active_at = int(time.time() * 1000)
            return session

    async def record_assistant_response(
        self, session_id: str, response: str
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.latest_assistant_response = response
            session.conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": int(time.time() * 1000)
            })
            session.last_active_at = int(time.time() * 1000)
            return session

    async def record_tts_event(
        self, session_id: str, request_id: str, event_type: str, details: Optional[Dict[str, Any]] = None
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.current_tts_request_id = request_id
            session.tts_history.append({
                "request_id": request_id,
                "event_type": event_type,
                "details": details or {},
                "timestamp": int(time.time() * 1000)
            })
            session.last_active_at = int(time.time() * 1000)
            return session

    async def set_processing_state(
        self, session_id: str, state: str
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.processing_state = state
            session.last_active_at = int(time.time() * 1000)
            return session

    async def next_generation(self, session_id: str) -> int:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.current_generation_id += 1
            session.last_active_at = int(time.time() * 1000)
            return session.current_generation_id

    async def get_current_generation(self, session_id: str) -> int:
        async with self._lock:
            if session_id not in self._sessions:
                return 0
            return self._sessions[session_id].current_generation_id

    async def create_turn(self, session_id: str, generation_id: Optional[int] = None) -> ConversationTurn:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            gen_id = generation_id if generation_id is not None else session.current_generation_id
            turn = ConversationTurn(generation_id=gen_id, status="PENDING")
            session.turns.append(turn)
            session.last_active_at = int(time.time() * 1000)
            return turn

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
        async with self._lock:
            if session_id not in self._sessions:
                return None
            session = self._sessions[session_id]
            for turn in reversed(session.turns):
                if turn.generation_id == generation_id:
                    if status is not None:
                        turn.status = status
                        if status in ("COMPLETED", "INTERRUPTED", "CANCELLED", "ERROR"):
                            turn.completed_at = int(time.time() * 1000)
                    if user_utterance is not None:
                        turn.user_utterance = user_utterance
                    if transcript is not None:
                        turn.transcript = transcript
                    if actions is not None:
                        turn.actions = actions
                    if assistant_response is not None:
                        turn.assistant_response = assistant_response
                    session.last_active_at = int(time.time() * 1000)
                    return turn
            return None

    async def set_conversation_state(
        self, session_id: str, state: str
    ) -> Optional[SessionState]:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            session = self._sessions[session_id]
            session.conversation_state = state
            session.processing_state = state
            session.last_active_at = int(time.time() * 1000)
            return session

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def list_sessions(self) -> List[SessionState]:
        async with self._lock:
            return list(self._sessions.values())
