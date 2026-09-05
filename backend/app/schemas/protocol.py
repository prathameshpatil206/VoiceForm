from enum import Enum
import time
from typing import Any, Dict, Generic, Optional, TypeVar, cast
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    # Lifecycle
    CLIENT_HELLO = "CLIENT_HELLO"
    SERVER_HELLO = "SERVER_HELLO"
    ACK = "ACK"
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"

    # Form & Actions
    FORM_SCHEMA = "FORM_SCHEMA"
    FILL_ACTION = "FILL_ACTION"
    FILL_ACTIONS = "FILL_ACTIONS"
    FILL_RESULT = "FILL_RESULT"

    # AI & Voice Pipeline (M4 - M6)
    AUDIO_CHUNK = "AUDIO_CHUNK"
    AUDIO = "AUDIO"
    TRANSCRIPT = "TRANSCRIPT"
    AI_ACTIONS = "AI_ACTIONS"
    AI_RESPONSE = "AI_RESPONSE"
    ASK_USER = "ASK_USER"
    AI_ERROR = "AI_ERROR"
    INTERRUPT = "INTERRUPT"

    # Milestone 5: TTS Protocol
    TTS_REQUEST = "TTS_REQUEST"
    TTS_START = "TTS_START"
    TTS_AUDIO = "TTS_AUDIO"
    TTS_END = "TTS_END"
    TTS_ERROR = "TTS_ERROR"
    TTS_CANCEL = "TTS_CANCEL"

    # Milestone 6: Generation Synchronization Protocol
    GENERATION_START = "GENERATION_START"
    GENERATION_CANCELLED = "GENERATION_CANCELLED"
    GENERATION_COMPLETE = "GENERATION_COMPLETE"

T = TypeVar("T")

class BaseMessage(BaseModel):
    version: int = 1
    type: MessageType
    session_id: str
    generation_id: Optional[int] = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))

class WebSocketMessage(BaseMessage, Generic[T]):
    payload: T = Field(default_factory=cast(Any, dict))

class AckPayload(BaseModel):
    acknowledged_type: MessageType
    status: str = "ok"
    details: Optional[str] = None
    generation_id: Optional[int] = None

class ErrorPayload(BaseModel):
    error_code: str
    message: str
    details: Optional[Any] = None
    generation_id: Optional[int] = None

class AudioChunkPayload(BaseModel):
    pcm_base64: str
    generation_id: Optional[int] = None

class AudioPayload(BaseModel):
    audio_base64: str
    duration_ms: Optional[int] = None
    sample_rate: int = 16000
    generation_id: Optional[int] = None

class TranscriptPayload(BaseModel):
    text: str
    language: Optional[str] = "en"
    confidence: Optional[float] = None
    is_final: bool = True
    generation_id: Optional[int] = None

class AiActionsPayload(BaseModel):
    actions: list[Dict[str, Any]] = Field(default_factory=list)
    reasoning: Optional[str] = None
    generation_id: Optional[int] = None

class AskUserPayload(BaseModel):
    question: str
    field_id: Optional[str] = None
    generation_id: Optional[int] = None

class AiErrorPayload(BaseModel):
    stage: str
    error_code: str
    message: str
    details: Optional[str] = None
    generation_id: Optional[int] = None

class TtsRequestPayload(BaseModel):
    text: str
    speaker: Optional[str] = None
    speed: Optional[float] = None
    generation_id: Optional[int] = None

class TtsStartPayload(BaseModel):
    request_id: str
    text: str
    format: str = "pcm"
    sample_rate: int = 16000
    generation_id: Optional[int] = None

class TtsAudioPayload(BaseModel):
    request_id: str
    chunk_index: int
    audio_base64: str
    format: str = "pcm"
    is_final: bool = False
    generation_id: Optional[int] = None

class TtsEndPayload(BaseModel):
    request_id: str
    total_chunks: int
    generation_id: Optional[int] = None

class TtsErrorPayload(BaseModel):
    request_id: str
    error_code: str
    message: str
    details: Optional[str] = None
    generation_id: Optional[int] = None

class TtsCancelPayload(BaseModel):
    request_id: str
    reason: Optional[str] = None
    generation_id: Optional[int] = None

# M6 Interruption & Generation Payloads
class InterruptPayload(BaseModel):
    generation_id: Optional[int] = None
    reason: Optional[str] = "user_speech_detected"
    timestamp_t0: Optional[int] = None

class GenerationStartPayload(BaseModel):
    generation_id: int
    trigger: str = "user_utterance"

class GenerationCancelledPayload(BaseModel):
    generation_id: int
    reason: str = "interrupted"

class GenerationCompletePayload(BaseModel):
    generation_id: int
    status: str = "completed"
