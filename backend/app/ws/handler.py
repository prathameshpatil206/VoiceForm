import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional, Tuple
from fastapi import WebSocket

from app.ai.asr.base import ASRProvider, TranscriptResult
from app.ai.asr.qwen_asr import Qwen3ASRProvider
from app.ai.llm.base import LLMActionResult, LLMProvider
from app.ai.llm.prompts import build_conversational_response
from app.ai.llm.qwen import Qwen3LLMProvider
from app.ai.tts.base import (
    TTSCancelledError,
    TTSError,
    TTSProvider,
)
from app.ai.tts.mock import MockTTSProvider
from app.ai.tts.rime import RimeTTSProvider
from app.ai.tts.safety import sanitize_tts_text
from app.ai.vad.base import VADProvider
from app.ai.vad.silero import SileroVADProvider
from app.ai.validator import ActionValidator
from app.config import config
from app.schemas.actions import FillAction, FillResult
from app.schemas.form import PageScanResult
from app.schemas.protocol import (
    AckPayload,
    AiActionsPayload,
    AiErrorPayload,
    AskUserPayload,
    ErrorPayload,
    GenerationCancelledPayload,
    GenerationCompletePayload,
    GenerationStartPayload,
    InterruptPayload,
    MessageType,
    TranscriptPayload,
    TtsAudioPayload,
    TtsCancelPayload,
    TtsEndPayload,
    TtsErrorPayload,
    TtsStartPayload,
    WebSocketMessage,
)
from app.profile.service import ProfileService
from app.schemas.profile import ProfileSource
from app.store.base import SessionStore
from app.ws.connection_manager import ConnectionManager

logger = logging.getLogger("voiceform.handler")


class WebSocketHandler:
    def __init__(
        self,
        store: SessionStore,
        manager: ConnectionManager,
        vad: Optional[VADProvider] = None,
        asr: Optional[ASRProvider] = None,
        llm: Optional[LLMProvider] = None,
        validator: Optional[ActionValidator] = None,
        tts: Optional[TTSProvider] = None,
        profile_service: Optional[ProfileService] = None
    ) -> None:
        self.store = store
        self.manager = manager
        self.vad = vad or SileroVADProvider()
        self.asr = asr or Qwen3ASRProvider()
        self.llm = llm or Qwen3LLMProvider()
        self.validator = validator or ActionValidator()
        self.profile_service = profile_service or ProfileService()

        # Milestone 5: TTS Provider (defaults to RimeTTSProvider or MockTTSProvider if configured)
        if tts is not None:
            self.tts = tts
        elif os.getenv("VOICEFORM_USE_MOCK_TTS", "").lower() in ("1", "true"):
            self.tts = MockTTSProvider()
        else:
            self.tts = RimeTTSProvider()

        # Active tasks tracked by (generation_id, asyncio.Task)
        self._active_pipeline_tasks: Dict[str, Tuple[int, asyncio.Task]] = {}
        self._active_tts_tasks: Dict[str, Tuple[int, asyncio.Task]] = {}
        self._task_lock = asyncio.Lock()

    async def _is_active_generation(self, session_id: str, generation_id: int) -> bool:
        """Returns True only if generation_id is active, not interrupted, and matches current turn."""
        session = await self.store.get_session(session_id)
        if not session:
            return False
        if session.current_generation_id != generation_id:
            return False
        if session.conversation_state in ("INTERRUPTED", "ERROR"):
            return False
        for turn in reversed(session.turns):
            if turn.generation_id == generation_id:
                return turn.status not in ("INTERRUPTED", "CANCELLED", "ERROR")
        return True

    async def cancel_generation(
        self,
        session_id: str,
        target_generation_id: Optional[int] = None,
        reason: str = "interrupted"
    ) -> None:
        """
        Cancels active asynchronous processing and TTS tasks for a session.
        Guarantees that cancelling generation N does not cancel generation N+1.
        """
        async with self._task_lock:
            # 1. Cancel pipeline task if it belongs to target_generation_id or earlier
            if session_id in self._active_pipeline_tasks:
                gen_id, task = self._active_pipeline_tasks[session_id]
                if target_generation_id is None or gen_id <= target_generation_id:
                    self._active_pipeline_tasks.pop(session_id, None)
                    if not task.done():
                        task.cancel()
                        logger.info(f"Cancelled pipeline task for session={session_id} gen={gen_id}")

            # 2. Cancel TTS task if it belongs to target_generation_id or earlier
            if session_id in self._active_tts_tasks:
                gen_id, task = self._active_tts_tasks[session_id]
                if target_generation_id is None or gen_id <= target_generation_id:
                    self._active_tts_tasks.pop(session_id, None)
                    if not task.done():
                        task.cancel()
                        logger.info(f"Cancelled active TTS task for session={session_id} gen={gen_id}")

        session = await self.store.get_session(session_id)
        if session:
            effective_gen = target_generation_id or session.current_generation_id
            if session.current_tts_request_id:
                await self.tts.cancel(session.current_tts_request_id)
            await self.store.update_turn(session_id, effective_gen, status="INTERRUPTED")
            await self.store.record_tts_event(session_id, session.current_tts_request_id or "all", "CANCELLED")
            await self.store.set_conversation_state(session_id, "INTERRUPTED")

    async def cancel_tts(self, session_id: str, request_id: Optional[str] = None) -> None:
        """Explicit TTS cancellation (e.g. from Stop Speech button or TTS_CANCEL message)."""
        session = await self.store.get_session(session_id)
        gen_id = session.current_generation_id if session else 0
        await self.cancel_generation(session_id, target_generation_id=gen_id, reason="explicit_tts_cancel")
        if request_id:
            await self.tts.cancel(request_id)
        await self.store.set_conversation_state(session_id, "IDLE")

    async def handle_message(
        self, websocket: WebSocket, session_id: str, raw_text: str
    ) -> None:
        # 1. Parse JSON
        try:
            data: Dict[str, Any] = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"Malformed JSON from session={session_id}: {e}")
            err_msg = WebSocketMessage(
                type=MessageType.ERROR,
                session_id=session_id,
                payload=ErrorPayload(
                    error_code="MALFORMED_JSON",
                    message="Message must be a valid JSON string",
                    details=str(e)
                )
            )
            await websocket.send_text(err_msg.model_dump_json())
            return

        # 2. Check protocol version
        version = data.get("version")
        if version != 1:
            err_msg = WebSocketMessage(
                type=MessageType.ERROR,
                session_id=session_id,
                payload=ErrorPayload(
                    error_code="UNSUPPORTED_VERSION",
                    message=f"Protocol version {version} not supported. Expected version 1."
                )
            )
            await websocket.send_text(err_msg.model_dump_json())
            return

        msg_type_str = data.get("type")
        payload = data.get("payload", {})
        incoming_sid = data.get("session_id", session_id)
        incoming_gen_id = data.get("generation_id")

        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            err_msg = WebSocketMessage(
                type=MessageType.ERROR,
                session_id=incoming_sid,
                payload=ErrorPayload(
                    error_code="UNKNOWN_MESSAGE_TYPE",
                    message=f"Unknown message type '{msg_type_str}'"
                )
            )
            await websocket.send_text(err_msg.model_dump_json())
            return

        logger.debug(f"Received msg={msg_type.value} session={incoming_sid} gen={incoming_gen_id}")

        # 3. Route message by type
        if msg_type == MessageType.CLIENT_HELLO:
            session = await self.store.create_session(
                session_id=incoming_sid,
                metadata=payload.get("metadata", {})
            )
            resp = WebSocketMessage(
                type=MessageType.SERVER_HELLO,
                session_id=session.session_id,
                generation_id=session.current_generation_id,
                payload={
                    "status": "ready",
                    "session_id": session.session_id,
                    "server_version": "0.1.0",
                    "current_generation_id": session.current_generation_id
                }
            )
            await websocket.send_text(resp.model_dump_json())

        elif msg_type == MessageType.FORM_SCHEMA:
            try:
                schema = PageScanResult.model_validate(payload)
                await self.store.update_schema(incoming_sid, schema)
                # Milestone 7: Query profile candidate matches for this form
                candidates = await self.profile_service.get_candidate_values_for_schema(schema)
                session = await self.store.get_session(incoming_sid)
                ack = WebSocketMessage(
                    type=MessageType.ACK,
                    session_id=incoming_sid,
                    generation_id=session.current_generation_id if session else 0,
                    payload=AckPayload(
                        acknowledged_type=MessageType.FORM_SCHEMA,
                        status="ok",
                        details=f"Stored schema with {schema.totalFieldCount} fields across {len(schema.forms)} forms ({len(candidates)} profile matches)",
                        generation_id=session.current_generation_id if session else 0
                    )
                )
                await websocket.send_text(ack.model_dump_json())
            except Exception as e:
                err_msg = WebSocketMessage(
                    type=MessageType.ERROR,
                    session_id=incoming_sid,
                    payload=ErrorPayload(
                        error_code="INVALID_SCHEMA_PAYLOAD",
                        message="Payload does not match PageScanResult schema",
                        details=str(e)
                    )
                )
                await websocket.send_text(err_msg.model_dump_json())

        elif msg_type == MessageType.AUDIO_CHUNK:
            try:
                pcm_b64 = payload.get("pcm_base64", "")
                if not pcm_b64 or not isinstance(pcm_b64, str):
                    return
                pcm_bytes = base64.b64decode(pcm_b64)
                complete_audio = await self.vad.process_stream(incoming_sid, pcm_bytes)
                if complete_audio:
                    # Utterance boundary detected by VAD! Trigger new generation turn
                    await self._start_utterance_generation(websocket, incoming_sid, complete_audio)
            except Exception as e:
                logger.error(f"Error in AUDIO_CHUNK handling: {e}")
                err_frame = WebSocketMessage[AiErrorPayload](
                    type=MessageType.AI_ERROR,
                    session_id=incoming_sid,
                    payload=AiErrorPayload(
                        stage="VAD",
                        error_code="VAD_PROCESSING_ERROR",
                        message=str(e)
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())

        elif msg_type == MessageType.AUDIO:
            try:
                audio_b64 = payload.get("audio_base64", "")
                if not audio_b64:
                    return
                audio_bytes = base64.b64decode(audio_b64)
                await self._start_utterance_generation(websocket, incoming_sid, audio_bytes)
            except Exception as e:
                logger.error(f"Error in AUDIO handling: {e}")
                err_frame = WebSocketMessage[AiErrorPayload](
                    type=MessageType.AI_ERROR,
                    session_id=incoming_sid,
                    payload=AiErrorPayload(
                        stage="AUDIO",
                        error_code="AUDIO_PAYLOAD_ERROR",
                        message=str(e)
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())

        elif msg_type == MessageType.INTERRUPT:
            # Explicit or VAD-driven interruption notification from client
            target_gen = payload.get("generation_id") or incoming_gen_id
            session = await self.store.get_session(incoming_sid)
            active_gen = session.current_generation_id if session else 0
            cancelled_gen = target_gen if target_gen is not None else active_gen

            await self.cancel_generation(incoming_sid, target_generation_id=cancelled_gen, reason="client_interrupt")

            # Acknowledge interruption & notify generation cancellation
            cancel_frame = WebSocketMessage[GenerationCancelledPayload](
                type=MessageType.GENERATION_CANCELLED,
                session_id=incoming_sid,
                generation_id=cancelled_gen,
                payload=GenerationCancelledPayload(
                    generation_id=cancelled_gen,
                    reason=payload.get("reason", "interrupted")
                )
            )
            await websocket.send_text(cancel_frame.model_dump_json())

            ack = WebSocketMessage(
                type=MessageType.ACK,
                session_id=incoming_sid,
                generation_id=cancelled_gen,
                payload=AckPayload(
                    acknowledged_type=MessageType.INTERRUPT,
                    status="ok",
                    details=f"Interrupted generation {cancelled_gen}",
                    generation_id=cancelled_gen
                )
            )
            await websocket.send_text(ack.model_dump_json())

        elif msg_type == MessageType.FILL_RESULT:
            try:
                fill_res = FillResult.model_validate(payload)
                await self.store.record_result(incoming_sid, fill_res)
                session = await self.store.get_session(incoming_sid)
                ack = WebSocketMessage(
                    type=MessageType.ACK,
                    session_id=incoming_sid,
                    generation_id=session.current_generation_id if session else 0,
                    payload=AckPayload(
                        acknowledged_type=MessageType.FILL_RESULT,
                        status="ok" if fill_res.success else "error",
                        details=fill_res.message or fill_res.error,
                        generation_id=session.current_generation_id if session else 0
                    )
                )
                await websocket.send_text(ack.model_dump_json())
            except Exception as e:
                err_msg = WebSocketMessage(
                    type=MessageType.ERROR,
                    session_id=incoming_sid,
                    payload=ErrorPayload(
                        error_code="INVALID_RESULT_PAYLOAD",
                        message="Payload does not match FillResult schema",
                        details=str(e)
                    )
                )
                await websocket.send_text(err_msg.model_dump_json())

        elif msg_type == MessageType.TTS_REQUEST:
            try:
                text_to_speak = payload.get("text", "").strip()
                speaker_voice = payload.get("speaker")
                if not text_to_speak:
                    err_msg = WebSocketMessage(
                        type=MessageType.ERROR,
                        session_id=incoming_sid,
                        payload=ErrorPayload(
                            error_code="EMPTY_TTS_REQUEST",
                            message="Text parameter is required for TTS_REQUEST"
                        )
                    )
                    await websocket.send_text(err_msg.model_dump_json())
                    return

                # Allocate or use current generation ID
                gen_id = payload.get("generation_id") or await self.store.next_generation(incoming_sid)
                safe_text = sanitize_tts_text(text_to_speak)
                await self._start_tts_task(websocket, incoming_sid, safe_text, generation_id=gen_id, speaker=speaker_voice)
            except Exception as e:
                logger.error(f"Error handling TTS_REQUEST: {e}")

        elif msg_type == MessageType.TTS_CANCEL:
            req_id = payload.get("request_id")
            await self.cancel_tts(incoming_sid, req_id)
            session = await self.store.get_session(incoming_sid)
            ack = WebSocketMessage(
                type=MessageType.ACK,
                session_id=incoming_sid,
                generation_id=session.current_generation_id if session else 0,
                payload=AckPayload(
                    acknowledged_type=MessageType.TTS_CANCEL,
                    status="ok",
                    details=f"Cancelled TTS for session={incoming_sid} req_id={req_id or 'all'}",
                    generation_id=session.current_generation_id if session else 0
                )
            )
            await websocket.send_text(ack.model_dump_json())

        elif msg_type == MessageType.PING:
            session = await self.store.get_session(incoming_sid)
            pong = WebSocketMessage(
                type=MessageType.PONG,
                session_id=incoming_sid,
                generation_id=session.current_generation_id if session else 0,
                payload={"echo_timestamp": data.get("timestamp")}
            )
            await websocket.send_text(pong.model_dump_json())

        else:
            err_msg = WebSocketMessage(
                type=MessageType.ERROR,
                session_id=incoming_sid,
                payload=ErrorPayload(
                    error_code="UNHANDLED_TYPE",
                    message=f"No server handler configured for type '{msg_type}'"
                )
            )
            await websocket.send_text(err_msg.model_dump_json())

    async def _start_utterance_generation(
        self, websocket: WebSocket, session_id: str, audio_bytes: bytes
    ) -> None:
        """
        Coordinates the start of a new conversational generation turn:
        1. Cancels any currently active generation / playback.
        2. Monotonically allocates new generation_id.
        3. Creates a new ConversationTurn in the SessionStore.
        4. Broadcasts GENERATION_START frame.
        5. Launches async pipeline task bound to generation_id.
        """
        # Step 1: Invalidate and cancel previous generation if active
        session = await self.store.get_session(session_id)
        if session and session.conversation_state in ("SPEAKING", "PROCESSING"):
            await self.cancel_generation(session_id, target_generation_id=session.current_generation_id, reason="interrupted_by_new_utterance")

        # Step 2: Increment monotonic generation ID and create turn
        gen_id = await self.store.next_generation(session_id)
        await self.store.create_turn(session_id, generation_id=gen_id)
        await self.store.set_conversation_state(session_id, "PROCESSING")

        # Step 3: Launch pipeline task tracked by generation_id
        async with self._task_lock:
            existing = self._active_pipeline_tasks.pop(session_id, None)
            if existing and not existing[1].done():
                existing[1].cancel()

            task = asyncio.create_task(
                self._process_utterance(websocket, session_id, audio_bytes, gen_id)
            )
            self._active_pipeline_tasks[session_id] = (gen_id, task)

    async def _process_utterance(
        self, websocket: WebSocket, session_id: str, audio_bytes: bytes, generation_id: int
    ) -> None:
        """
        Executes the full VoiceForm conversational AI Pipeline on a completed utterance
        strictly verified against generation_id:
        audio_bytes -> ASR -> transcript -> LLM -> actions + response -> Validator -> FILL_ACTIONS -> Rime TTS
        """
        try:
            # Guard: check if generation is still active
            if not await self._is_active_generation(session_id, generation_id):
                logger.info(f"Discarding stale utterance processing for session={session_id} gen={generation_id}")
                return

            await self.store.set_conversation_state(session_id, "PROCESSING")
            await self.store.update_turn(session_id, generation_id, status="PROCESSING")

            # Step 1: Automatic Speech Recognition (Qwen3-ASR)
            try:
                transcript_res: TranscriptResult = await self.asr.transcribe(audio_bytes)
            except Exception as e:
                if not await self._is_active_generation(session_id, generation_id):
                    return
                logger.error(f"ASR transcription failed for session={session_id} gen={generation_id}: {e}")
                await self.store.set_conversation_state(session_id, "ERROR")
                await self.store.update_turn(session_id, generation_id, status="ERROR")
                err_frame = WebSocketMessage[AiErrorPayload](
                    type=MessageType.AI_ERROR,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload=AiErrorPayload(
                        stage="ASR",
                        error_code="ASR_TRANSCRIPTION_FAILED",
                        message=str(e),
                        generation_id=generation_id
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())
                return

            # Stale guard after ASR
            if not await self._is_active_generation(session_id, generation_id):
                logger.info(f"Discarding stale ASR result for session={session_id} gen={generation_id}")
                return

            text = transcript_res.text.strip()
            if not text:
                logger.info(f"No speech detected in audio for session={session_id} gen={generation_id}")
                await self.store.set_conversation_state(session_id, "IDLE")
                await self.store.update_turn(session_id, generation_id, status="COMPLETED")
                return

            logger.info(f"🎙️ Transcript for session={session_id} [gen={generation_id}]: '{text}'")

            # Send TRANSCRIPT message to extension
            transcript_frame = WebSocketMessage[TranscriptPayload](
                type=MessageType.TRANSCRIPT,
                session_id=session_id,
                generation_id=generation_id,
                payload=TranscriptPayload(
                    text=text,
                    language=transcript_res.language,
                    confidence=transcript_res.confidence,
                    is_final=True,
                    generation_id=generation_id
                )
            )
            await websocket.send_text(transcript_frame.model_dump_json())
            await self.store.record_transcript(session_id, text)
            await self.store.append_conversation(session_id, "user", text)
            await self.store.update_turn(session_id, generation_id, transcript=text, user_utterance=text)

            # Step 2: Retrieve current form schema & context
            session = await self.store.get_session(session_id)
            if not session or not session.schema_data or session.schema_data.totalFieldCount == 0:
                logger.warning(f"No form schema present for session={session_id} gen={generation_id}")
                await self.store.set_conversation_state(session_id, "IDLE")
                await self.store.update_turn(session_id, generation_id, status="ERROR")
                err_frame = WebSocketMessage[AiErrorPayload](
                    type=MessageType.AI_ERROR,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload=AiErrorPayload(
                        stage="LLM",
                        error_code="NO_FORM_SCHEMA",
                        message="No active form inputs detected on the current page.",
                        generation_id=generation_id
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())
                return

            # Step 3: LLM Reasoning & Extraction (Qwen3) with Profile Context
            try:
                # Milestone 7: Retrieve matching profile candidate values
                profile_candidates = await self.profile_service.get_candidate_values_for_schema(session.schema_data)
                profile_context = {
                    c.canonical_key: c.value for c in profile_candidates if c.canonical_key and c.value
                } if profile_candidates else None

                try:
                    llm_result = await self.llm.extract_actions(
                        transcript=text,
                        schema=session.schema_data,
                        current_values=session.current_field_values,
                        conversation_history=session.conversation_history,
                        profile_context=profile_context
                    )
                except TypeError:
                    llm_result = await self.llm.extract_actions(
                        transcript=text,
                        schema=session.schema_data,
                        current_values=session.current_field_values,
                        conversation_history=session.conversation_history
                    )
            except Exception as e:
                if not await self._is_active_generation(session_id, generation_id):
                    return
                logger.error(f"LLM extraction failed for session={session_id} gen={generation_id}: {e}")
                await self.store.set_conversation_state(session_id, "ERROR")
                await self.store.update_turn(session_id, generation_id, status="ERROR")
                err_frame = WebSocketMessage[AiErrorPayload](
                    type=MessageType.AI_ERROR,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload=AiErrorPayload(
                        stage="LLM",
                        error_code="LLM_EXTRACTION_FAILED",
                        message=str(e),
                        generation_id=generation_id
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())
                return

            # Stale guard after LLM
            if not await self._is_active_generation(session_id, generation_id):
                logger.info(f"Discarding stale LLM result for session={session_id} gen={generation_id}")
                return

            # If LLM generated a clarification or question for missing information
            if llm_result.ask_user:
                logger.info(f"❓ LLM asked user [gen={generation_id}]: '{llm_result.ask_user}'")
                await self.store.append_conversation(session_id, "assistant", llm_result.ask_user)
                ask_frame = WebSocketMessage[AskUserPayload](
                    type=MessageType.ASK_USER,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload=AskUserPayload(question=llm_result.ask_user, generation_id=generation_id)
                )
                await websocket.send_text(ask_frame.model_dump_json())

            # Step 4: Action Validation Layer (Safety & Schema Guard)
            raw_actions = llm_result.actions
            valid_actions: list[FillAction] = []
            if raw_actions:
                v_acts, rejected = self.validator.validate_actions(raw_actions, session.schema_data)
                valid_actions = v_acts
                if rejected:
                    for r in rejected:
                        logger.warning(
                            f"Action rejected for session={session_id} gen={generation_id}: {r['error']} ({r['error_code']})"
                        )

            # Stale guard before dispatching actions
            if not await self._is_active_generation(session_id, generation_id):
                logger.info(f"Discarding stale actions dispatch for session={session_id} gen={generation_id}")
                return

            # Step 5: Dispatch Validated Actions to Extension (M2 DOM Filler)
            if valid_actions:
                await self.store.update_turn(
                    session_id,
                    generation_id,
                    actions=[a.model_dump() for a in valid_actions]
                )

                # Emit AI_ACTIONS telemetry frame to UI
                ai_actions_frame = WebSocketMessage[AiActionsPayload](
                    type=MessageType.AI_ACTIONS,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload=AiActionsPayload(
                        actions=[a.model_dump() for a in valid_actions],
                        reasoning=llm_result.reasoning,
                        generation_id=generation_id
                    )
                )
                await websocket.send_text(ai_actions_frame.model_dump_json())

                # Record actions in store
                for act in valid_actions:
                    await self.store.record_action(session_id, act)

                # Dispatch FILL_ACTIONS batch to M2 DOM filler
                fill_frame = WebSocketMessage[Dict[str, Any]](
                    type=MessageType.FILL_ACTIONS,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload={"actions": [a.model_dump() for a in valid_actions], "generation_id": generation_id}
                )
                await websocket.send_text(fill_frame.model_dump_json())
                logger.info(f"⚡ Dispatched {len(valid_actions)} validated actions for session={session_id} gen={generation_id}")

                # Milestone 7: Extract and persist eligible profile candidates
                try:
                    profile_cands = self.profile_service.extract_profile_candidates_from_actions(
                        [a.model_dump() for a in valid_actions],
                        session.schema_data,
                        source=ProfileSource.USER_SPOKEN
                    )
                    if profile_cands:
                        await self.profile_service.save_eligible_candidates(profile_cands)
                except Exception as p_err:
                    logger.warning(f"Error persisting profile candidates: {p_err}")

            # Step 6: Determine Spoken Assistant Response (Milestone 5)
            spoken_response = llm_result.response

            # Fallback response generation grounded in current form state
            if not spoken_response:
                field_map = {}
                for form in session.schema_data.forms:
                    for f in form.fields:
                        field_map[f.id] = f.label
                for f in session.schema_data.orphanFields:
                    field_map[f.id] = f.label

                filled_labels: list[str] = []
                for act in valid_actions:
                    if act.field_id and act.field_id in field_map:
                        lbl = field_map[act.field_id]
                        if lbl and lbl not in filled_labels:
                            filled_labels.append(lbl)

                # Check remaining unfilled required fields
                remaining_required: list[str] = []
                all_fields = [f for form in session.schema_data.forms for f in form.fields] + list(session.schema_data.orphanFields)
                curr_vals = dict(session.current_field_values)
                for a in valid_actions:
                    if a.field_id:
                        curr_vals[a.field_id] = a.value

                for f in all_fields:
                    if f.validation.required and not f.disabled and not f.readOnly:
                        val = curr_vals.get(f.id)
                        if val is None or str(val).strip() == "":
                            if f.label and f.label not in remaining_required:
                                remaining_required.append(f.label)

                spoken_response = build_conversational_response(
                    filled_labels=filled_labels,
                    ask_user=llm_result.ask_user,
                    remaining_required_labels=remaining_required
                )

            # Apply TTS Safety Guard
            safe_response = sanitize_tts_text(spoken_response)

            # Stale guard before starting TTS
            if not await self._is_active_generation(session_id, generation_id):
                logger.info(f"Discarding stale response/TTS for session={session_id} gen={generation_id}")
                return

            if safe_response:
                logger.info(f"🗣️ Assistant response [session={session_id} gen={generation_id}]: '{safe_response}'")
                await self.store.record_assistant_response(session_id, safe_response)
                await self.store.update_turn(session_id, generation_id, assistant_response=safe_response)

                # Emit conversational response text to extension for UI display
                resp_frame = WebSocketMessage[Dict[str, Any]](
                    type=MessageType.AI_RESPONSE,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload={"response": safe_response, "generation_id": generation_id}
                )
                await websocket.send_text(resp_frame.model_dump_json())

                # Synthesize and stream speech via Rime TTS
                await self._start_tts_task(websocket, session_id, safe_response, generation_id=generation_id)
            else:
                await self.store.set_conversation_state(session_id, "IDLE")
                await self.store.update_turn(session_id, generation_id, status="COMPLETED")
                complete_frame = WebSocketMessage[GenerationCompletePayload](
                    type=MessageType.GENERATION_COMPLETE,
                    session_id=session_id,
                    generation_id=generation_id,
                    payload=GenerationCompletePayload(generation_id=generation_id, status="completed")
                )
                await websocket.send_text(complete_frame.model_dump_json())

        except asyncio.CancelledError:
            logger.info(f"Pipeline task cancelled for session={session_id} gen={generation_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in pipeline for session={session_id} gen={generation_id}: {e}")
            if await self._is_active_generation(session_id, generation_id):
                await self.store.set_conversation_state(session_id, "ERROR")
                await self.store.update_turn(session_id, generation_id, status="ERROR")
        finally:
            async with self._task_lock:
                if session_id in self._active_pipeline_tasks:
                    curr_g, curr_t = self._active_pipeline_tasks[session_id]
                    if curr_g == generation_id and curr_t == asyncio.current_task():
                        self._active_pipeline_tasks.pop(session_id, None)

    async def _start_tts_task(
        self,
        websocket: WebSocket,
        session_id: str,
        text: str,
        generation_id: int,
        speaker: Optional[str] = None
    ) -> asyncio.Task:
        """Launches TTS streaming as an asynchronous task bound to generation_id."""
        async with self._task_lock:
            existing = self._active_tts_tasks.pop(session_id, None)
            if existing and not existing[1].done():
                existing[1].cancel()

            task = asyncio.create_task(
                self._stream_tts(websocket, session_id, text, generation_id=generation_id, speaker=speaker)
            )
            self._active_tts_tasks[session_id] = (generation_id, task)
            return task

    async def _stream_tts(
        self,
        websocket: WebSocket,
        session_id: str,
        text: str,
        generation_id: Optional[int] = None,
        speaker: Optional[str] = None
    ) -> None:
        """
        Streams synthesized audio chunks to the browser over the session WebSocket.
        Strictly guards against stale generations and handles cancellation cleanly.
        """
        session = await self.store.get_session(session_id)
        effective_gen = generation_id if generation_id is not None else (session.current_generation_id if session else 0)
        req_id = f"tts_{uuid.uuid4().hex[:8]}"

        # Stale guard before starting playback
        if not await self._is_active_generation(session_id, effective_gen):
            logger.info(f"Skipping stale TTS stream for session={session_id} gen={effective_gen}")
            return

        await self.store.set_conversation_state(session_id, "SPEAKING")
        await self.store.update_turn(session_id, effective_gen, status="SPEAKING")
        await self.store.record_tts_event(session_id, req_id, "STARTED", {"text": text, "generation_id": effective_gen})

        audio_format = getattr(self.tts, "audio_format", "pcm")
        sample_rate = getattr(self.tts, "sampling_rate", 16000)

        # 1. Send TTS_START frame
        start_frame = WebSocketMessage[TtsStartPayload](
            type=MessageType.TTS_START,
            session_id=session_id,
            generation_id=effective_gen,
            payload=TtsStartPayload(
                request_id=req_id,
                text=text,
                format=audio_format,
                sample_rate=sample_rate,
                generation_id=effective_gen
            )
        )
        await websocket.send_text(start_frame.model_dump_json())

        chunk_count = 0

        try:
            # 2. Stream audio chunks from TTS provider
            async for chunk in self.tts.synthesize_stream(
                text=text,
                session_id=session_id,
                request_id=req_id,
                speaker=speaker
            ):
                # Stale check during streaming loop
                if not await self._is_active_generation(session_id, effective_gen):
                    logger.info(f"Aborting stale TTS stream loop for session={session_id} gen={effective_gen}")
                    break

                if chunk.audio_bytes:
                    b64_audio = base64.b64encode(chunk.audio_bytes).decode("ascii")
                    audio_frame = WebSocketMessage[TtsAudioPayload](
                        type=MessageType.TTS_AUDIO,
                        session_id=session_id,
                        generation_id=effective_gen,
                        payload=TtsAudioPayload(
                            request_id=req_id,
                            chunk_index=chunk.chunk_index,
                            audio_base64=b64_audio,
                            format=chunk.format,
                            is_final=chunk.is_final,
                            generation_id=effective_gen
                        )
                    )
                    await websocket.send_text(audio_frame.model_dump_json())
                    chunk_count += 1

                if chunk.is_final:
                    break

            # Stale check before finishing
            if not await self._is_active_generation(session_id, effective_gen):
                return

            # 3. Send TTS_END frame
            end_frame = WebSocketMessage[TtsEndPayload](
                type=MessageType.TTS_END,
                session_id=session_id,
                generation_id=effective_gen,
                payload=TtsEndPayload(
                    request_id=req_id,
                    total_chunks=chunk_count,
                    generation_id=effective_gen
                )
            )
            await websocket.send_text(end_frame.model_dump_json())

            # 4. Send GENERATION_COMPLETE frame
            complete_frame = WebSocketMessage[GenerationCompletePayload](
                type=MessageType.GENERATION_COMPLETE,
                session_id=session_id,
                generation_id=effective_gen,
                payload=GenerationCompletePayload(
                    generation_id=effective_gen,
                    status="completed"
                )
            )
            await websocket.send_text(complete_frame.model_dump_json())

            await self.store.record_tts_event(session_id, req_id, "COMPLETED", {"total_chunks": chunk_count, "generation_id": effective_gen})
            await self.store.update_turn(session_id, effective_gen, status="COMPLETED")
            await self.store.set_conversation_state(session_id, "IDLE")
            logger.info(f"🔊 Completed TTS stream for session={session_id} gen={effective_gen} ({chunk_count} chunks)")

        except (TTSCancelledError, asyncio.CancelledError):
            logger.info(f"TTS stream cancelled for session={session_id} gen={effective_gen} req_id={req_id}")
            if await self._is_active_generation(session_id, effective_gen):
                cancel_frame = WebSocketMessage[TtsCancelPayload](
                    type=MessageType.TTS_CANCEL,
                    session_id=session_id,
                    generation_id=effective_gen,
                    payload=TtsCancelPayload(request_id=req_id, reason="Playback cancelled", generation_id=effective_gen)
                )
                await websocket.send_text(cancel_frame.model_dump_json())
                await self.store.record_tts_event(session_id, req_id, "CANCELLED")
                await self.store.set_conversation_state(session_id, "IDLE")

        except TTSError as e:
            logger.warning(f"TTS provider error for session={session_id} gen={effective_gen}: {e.message} ({e.error_code})")
            if await self._is_active_generation(session_id, effective_gen):
                err_frame = WebSocketMessage[TtsErrorPayload](
                    type=MessageType.TTS_ERROR,
                    session_id=session_id,
                    generation_id=effective_gen,
                    payload=TtsErrorPayload(
                        request_id=req_id,
                        error_code=e.error_code,
                        message=e.message,
                        details=e.details,
                        generation_id=effective_gen
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())
                await self.store.record_tts_event(session_id, req_id, "ERROR", {"error_code": e.error_code, "message": e.message})
                await self.store.set_conversation_state(session_id, "IDLE")

        except Exception as e:
            logger.error(f"Unexpected error in TTS streaming for session={session_id} gen={effective_gen}: {e}")
            if await self._is_active_generation(session_id, effective_gen):
                err_frame = WebSocketMessage[TtsErrorPayload](
                    type=MessageType.TTS_ERROR,
                    session_id=session_id,
                    generation_id=effective_gen,
                    payload=TtsErrorPayload(
                        request_id=req_id,
                        error_code="TTS_INTERNAL_ERROR",
                        message=str(e),
                        generation_id=effective_gen
                    )
                )
                await websocket.send_text(err_frame.model_dump_json())
                await self.store.record_tts_event(session_id, req_id, "ERROR", {"error": str(e)})
                await self.store.set_conversation_state(session_id, "IDLE")
        finally:
            async with self._task_lock:
                if session_id in self._active_tts_tasks:
                    curr_g, curr_t = self._active_tts_tasks[session_id]
                    if curr_g == effective_gen and curr_t == asyncio.current_task():
                        self._active_tts_tasks.pop(session_id, None)
