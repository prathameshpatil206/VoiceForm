import asyncio
import base64
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import profile_routes
from app.api.profile_routes import get_profile_service
from app.config import config
from app.db.migration import run_migrations
from app.db.session import check_db_health, close_db_engine
from app.profile.service import ProfileService
from app.schemas.actions import FillAction
from app.schemas.profile import ProfileSource
from app.schemas.protocol import MessageType, WebSocketMessage
from app.store.base import SessionState, SessionStore
from app.store.memory import InMemorySessionStore
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import WebSocketHandler

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("voiceform.main")

# State Singletons
session_store: SessionStore = InMemorySessionStore()
connection_manager = ConnectionManager()
profile_service = get_profile_service()
ws_handler = WebSocketHandler(session_store, connection_manager, profile_service=profile_service)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 VoiceForm Backend starting on {config.HOST}:{config.PORT}")
    # Milestone 7: Execute DB migrations if database configured
    try:
        migrated = await run_migrations()
        if migrated:
            logger.info("Database schema initialized successfully")
        else:
            logger.warning("Database migrations skipped or failed")
    except Exception as e:
        logger.warning(f"Could not run initial DB migrations: {e}")

    yield

    logger.info("🛑 VoiceForm Backend stopping")
    try:
        await ws_handler.profile_service.cache.close()
        await close_db_engine()
    except Exception as e:
        logger.debug(f"Cleanup error during shutdown: {e}")

app = FastAPI(
    title="VoiceForm Backend",
    version="0.1.0",
    description="Realtime WebSocket Backend for VoiceForm Chrome Extension",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Milestone 7 Profile REST Router
app.include_router(profile_routes.router)

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    rime_configured = bool(config.RIME_API_KEY and config.RIME_API_KEY.strip())
    db_healthy = await check_db_health()
    redis_healthy = await profile_service.cache.is_available()

    return {
        "status": "ok",
        "service": "voiceform-backend",
        "protocol_version": config.PROTOCOL_VERSION,
        "active_sessions": len(await session_store.list_sessions()),
        "persistence": {
            "postgres_connected": db_healthy,
            "database_url_configured": bool(config.DATABASE_URL),
            "profile_persistence_enabled": config.ENABLE_PROFILE_PERSISTENCE
        },
        "cache": {
            "redis_connected": redis_healthy,
            "redis_url_configured": bool(config.REDIS_URL),
            "cache_hits": profile_service.cache.hits,
            "cache_misses": profile_service.cache.misses,
            "last_latency_ms": round(profile_service.cache.last_latency_ms, 3)
        },
        "tts": {
            "provider": ws_handler.tts.__class__.__name__,
            "rime_configured": rime_configured,
            "speaker": config.RIME_SPEAKER,
            "model_id": config.RIME_MODEL_ID,
            "audio_format": config.RIME_AUDIO_FORMAT
        }
    }


@app.websocket("/ws")
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: Optional[str] = None):
    # If no session_id in URL query/path, generate a temporary default
    sid = session_id or f"sess_{uuid.uuid4().hex[:8]}"
    await connection_manager.connect(websocket, sid)

    try:
        while True:
            text = await websocket.receive_text()
            await ws_handler.handle_message(websocket, sid, text)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, sid)
    except Exception as e:
        logger.error(f"Unexpected error in websocket loop: {e}")
        connection_manager.disconnect(websocket, sid)

# =========================================================================
# Debug & Testing Endpoints (M3 Verification & Extension Interaction)
# =========================================================================

@app.get("/api/sessions", response_model=List[SessionState])
async def list_sessions() -> List[SessionState]:
    return await session_store.list_sessions()

@app.get("/api/sessions/{session_id}", response_model=SessionState)
async def get_session(session_id: str) -> SessionState:
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

class TriggerFillRequest(BaseModel):
    action: FillAction

@app.post("/api/sessions/{session_id}/trigger-fill")
async def trigger_fill_action(session_id: str, req: TriggerFillRequest) -> Dict[str, Any]:
    """
    Sends a structured FILL_ACTION envelope down the WebSocket to the extension for session_id.
    Enables testing the complete backend -> extension -> M2 DOM filler pipeline.
    """
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not connection_manager.is_connected(session_id):
        raise HTTPException(status_code=400, detail="No active WebSocket connected for this session")

    # Record action in session history
    await session_store.record_action(session_id, req.action)

    msg = WebSocketMessage[FillAction](
        type=MessageType.FILL_ACTION,
        session_id=session_id,
        payload=req.action
    )

    sent = await connection_manager.send_message(session_id, msg)
    return {
        "success": sent,
        "session_id": session_id,
        "action": req.action.model_dump()
    }

class ProcessUtteranceRequest(BaseModel):
    transcript: Optional[str] = None
    audio_base64: Optional[str] = None

@app.post("/api/sessions/{session_id}/process-utterance")
async def process_utterance_endpoint(session_id: str, req: ProcessUtteranceRequest) -> Dict[str, Any]:
    """
    Directly triggers the VoiceForm AI pipeline for session_id.
    Accepts either an explicit transcript or base64 audio.
    """
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if req.transcript:
        text = req.transcript.strip()
        await session_store.record_transcript(session_id, text)
        await session_store.append_conversation(session_id, "user", text)

        if not session.schema_data:
            raise HTTPException(status_code=400, detail="Session has no scanned form schema")

        # Retrieve profile context
        profile_candidates = await profile_service.get_candidate_values_for_schema(session.schema_data)
        profile_context = {
            c.canonical_key: c.value for c in profile_candidates if c.canonical_key and c.value
        } if profile_candidates else None

        try:
            llm_res = await ws_handler.llm.extract_actions(
                transcript=text,
                schema=session.schema_data,
                current_values=session.current_field_values,
                conversation_history=session.conversation_history,
                profile_context=profile_context
            )
        except TypeError:
            llm_res = await ws_handler.llm.extract_actions(
                transcript=text,
                schema=session.schema_data,
                current_values=session.current_field_values,
                conversation_history=session.conversation_history
            )

        valid_actions, rejected = ws_handler.validator.validate_actions(
            llm_res.actions, session.schema_data
        )

        # Dispatch down websocket if connected
        if connection_manager.is_connected(session_id) and valid_actions:
            fill_frame = WebSocketMessage[Dict[str, Any]](
                type=MessageType.FILL_ACTIONS,
                session_id=session_id,
                payload={"actions": [a.model_dump() for a in valid_actions]}
            )
            await connection_manager.send_message(session_id, fill_frame)

        # Persist eligible profile candidates
        if valid_actions:
            try:
                cands = profile_service.extract_profile_candidates_from_actions(
                    [a.model_dump() for a in valid_actions],
                    session.schema_data,
                    source=ProfileSource.USER_SPOKEN
                )
                if cands:
                    await profile_service.save_eligible_candidates(cands)
            except Exception as pe:
                logger.warning(f"Profile candidate save error: {pe}")

        return {
            "transcript": text,
            "raw_actions": llm_res.actions,
            "valid_actions": [a.model_dump() for a in valid_actions],
            "rejected_actions": rejected,
            "response": llm_res.response,
            "ask_user": llm_res.ask_user,
            "reasoning": llm_res.reasoning
        }

    elif req.audio_base64:
        audio_bytes = base64.b64decode(req.audio_base64)
        t_res = await ws_handler.asr.transcribe(audio_bytes)
        return {
            "transcript": t_res.text,
            "language": t_res.language,
            "confidence": t_res.confidence
        }

    raise HTTPException(status_code=400, detail="Must provide either 'transcript' or 'audio_base64'")


class TTSSpeakRequest(BaseModel):
    text: str
    speaker: Optional[str] = None

@app.post("/api/sessions/{session_id}/tts-speak")
async def tts_speak_endpoint(session_id: str, req: TTSSpeakRequest) -> Dict[str, Any]:
    """
    Synthesizes text and streams it as TTS_START, TTS_AUDIO, TTS_END
    down the connected WebSocket for session_id.
    """
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    connections = connection_manager.active_connections.get(session_id)
    if not connections:
        raise HTTPException(status_code=400, detail="No active WebSocket connection for this session")

    ws = connections[0]
    gen_id = await session_store.next_generation(session_id)

    # Use handler's streaming TTS method
    asyncio.create_task(
        ws_handler._stream_tts(ws, session_id, req.text, generation_id=gen_id, speaker=req.speaker)
    )

    return {
        "status": "queued",
        "session_id": session_id,
        "text": req.text,
        "speaker": req.speaker or config.RIME_SPEAKER
    }


@app.post("/api/tts/synthesize")
async def direct_synthesize_endpoint(req: TTSSpeakRequest) -> Dict[str, Any]:
    """
    Directly invokes the configured TTS provider to synthesize text.
    Returns total chunks, format, sample rate, and combined base64 audio.
    Enables instant verification of Rime credentials and audio generation.
    """
    chunks: list[bytes] = []
    chunk_count = 0
    audio_format = getattr(ws_handler.tts, "audio_format", "pcm")
    sample_rate = getattr(ws_handler.tts, "sampling_rate", 16000)

    try:
        async for chunk in ws_handler.tts.synthesize_stream(
            text=req.text,
            speaker=req.speaker
        ):
            if chunk.audio_bytes:
                chunks.append(chunk.audio_bytes)
                chunk_count += 1
            if chunk.is_final:
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")

    combined_bytes = b"".join(chunks)
    return {
        "text": req.text,
        "provider": ws_handler.tts.__class__.__name__,
        "format": audio_format,
        "sample_rate": sample_rate,
        "chunk_count": chunk_count,
        "total_bytes": len(combined_bytes),
        "audio_base64": base64.b64encode(combined_bytes).decode("ascii")
    }
