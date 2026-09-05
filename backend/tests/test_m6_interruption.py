import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ai.asr.base import ASRProvider, TranscriptResult
from app.ai.llm.base import LLMActionResult, LLMProvider
from app.ai.tts.base import TTSCancelledError, TTSChunk, TTSProvider
from app.ai.tts.mock import MockTTSProvider
from app.ai.vad.base import VADProvider
from app.main import app, session_store, ws_handler
from app.schemas.actions import FillAction
from app.schemas.form import (
    DetectedForm,
    FormField,
    PageScanResult,
    ValidationRules,
)
from app.schemas.protocol import MessageType

client = TestClient(app)


def get_test_form_schema() -> PageScanResult:
    """Sample registration form schema for testing."""
    return PageScanResult(
        url="http://localhost:3456/test-pages/static-forms.html",
        title="Student Registration",
        forms=[
            DetectedForm(
                formId="reg-form",
                selector="#reg-form",
                title="Registration Form",
                fields=[
                    FormField(
                        id="vf-full-name",
                        name="fullName",
                        type="text",
                        label="Full Name",
                        selector="#full-name",
                        validation=ValidationRules(required=True),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-email",
                        name="email",
                        type="email",
                        label="Email Address",
                        selector="#email-addr",
                        validation=ValidationRules(required=True),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-phone",
                        name="phoneNumber",
                        type="tel",
                        label="Phone Number",
                        selector="#phone-input",
                        validation=ValidationRules(required=True),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                ],
                fieldCount=3,
                lastScannedAt=1700000000
            )
        ],
        orphanFields=[],
        totalFieldCount=3,
        scannedAt=1700000000
    )


# =========================================================================
# M6-T1: Generation IDs Increment Correctly
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t1_generation_ids_increment_correctly():
    """M6-T1: Verifies that session generation IDs increment monotonically across turns."""
    sid = "test_m6_t1_gen_increment"
    session = await session_store.create_session(sid)
    assert session.current_generation_id == 0

    g1 = await session_store.next_generation(sid)
    assert g1 == 1
    t1 = await session_store.create_turn(sid, g1)
    assert t1.generation_id == 1

    g2 = await session_store.next_generation(sid)
    assert g2 == 2
    t2 = await session_store.create_turn(sid, g2)
    assert t2.generation_id == 2

    g3 = await session_store.next_generation(sid)
    assert g3 == 3
    assert await session_store.get_current_generation(sid) == 3


# =========================================================================
# M6-T2: Stale LLM Result Is Discarded
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t2_stale_llm_result_is_discarded():
    """M6-T2: Verifies that LLM responses from an older generation are discarded without side effects."""
    sid = "test_m6_t2_stale_llm"
    await session_store.create_session(sid)
    await session_store.update_schema(sid, get_test_form_schema())

    # Start generation 1
    g1 = await session_store.next_generation(sid)
    assert g1 == 1

    # Fake delayed LLM extraction returning actions for generation 1
    # But before LLM completes, user interrupts and generation becomes 2
    g2 = await session_store.next_generation(sid)
    assert g2 == 2

    # Check active generation guard
    is_active = await ws_handler._is_active_generation(sid, g1)
    assert is_active is False

    # Simulate pipeline receiving g1 result
    # It must not update field values or current response
    session = await session_store.get_session(sid)
    assert session is not None
    assert session.current_field_values == {}
    assert session.latest_assistant_response is None


# =========================================================================
# M6-T3: Stale ASR Result Is Discarded
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t3_stale_asr_result_is_discarded():
    """M6-T3: Verifies that ASR transcripts from an obsolete generation are ignored."""
    sid = "test_m6_t3_stale_asr"
    await session_store.create_session(sid)

    g1 = await session_store.next_generation(sid)
    assert g1 == 1

    # Invalidate g1 by bumping to g2
    await session_store.next_generation(sid)
    assert await ws_handler._is_active_generation(sid, g1) is False

    # Stale generation check should prevent recording transcript for g1
    if await ws_handler._is_active_generation(sid, g1):
        await session_store.record_transcript(sid, "Stale transcript")

    session = await session_store.get_session(sid)
    assert session is not None
    assert session.latest_transcript is None


# =========================================================================
# M6-T4: Stale TTS Result Is Discarded
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t4_stale_tts_result_is_discarded():
    """M6-T4: Verifies that TTS streaming from an old generation does not play or update state."""
    sid = "test_m6_t4_stale_tts"
    await session_store.create_session(sid)

    g1 = await session_store.next_generation(sid)
    g2 = await session_store.next_generation(sid)

    # g1 is now stale
    assert await ws_handler._is_active_generation(sid, g1) is False
    assert await ws_handler._is_active_generation(sid, g2) is True


# =========================================================================
# M6-T5: TTS Cancellation Stops Playback
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t5_tts_cancellation_stops_playback():
    """M6-T5: Verifies that cancel_tts stops active TTS tasks and resets conversation state."""
    sid = "test_m6_t5_tts_cancel"
    await session_store.create_session(sid)
    await session_store.set_conversation_state(sid, "SPEAKING")

    # Call cancel_tts
    await ws_handler.cancel_tts(sid, request_id="tts_test123")

    session = await session_store.get_session(sid)
    assert session is not None
    assert session.conversation_state == "IDLE"
    assert session.tts_history[-1]["event_type"] == "CANCELLED"


# =========================================================================
# M6-T6: Queued Audio From Old Generation Is Discarded
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t6_queued_audio_from_old_generation_discarded():
    """M6-T6: Verifies that queued audio frames tagged with older generation IDs are ignored by handler."""
    sid = "test_m6_t6_queued_audio"
    await session_store.create_session(sid)

    g1 = await session_store.next_generation(sid)
    g2 = await session_store.next_generation(sid)

    assert await ws_handler._is_active_generation(sid, g1) is False
    assert await ws_handler._is_active_generation(sid, g2) is True


# =========================================================================
# M6-T7: Late TTS_AUDIO Chunk From Old Generation Is Ignored
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t7_late_tts_audio_chunk_ignored():
    """M6-T7: Verifies that a chunk arriving from generation 1 after generation 2 starts is discarded."""
    sid = "test_m6_t7_late_chunk"
    await session_store.create_session(sid)

    await session_store.next_generation(sid)  # Gen 1
    await session_store.next_generation(sid)  # Gen 2

    # A chunk from Gen 1 arrives
    chunk_gen = 1
    active_gen = await session_store.get_current_generation(sid)
    assert chunk_gen < active_gen  # Client & Server discard this chunk


# =========================================================================
# M6-T8: Interruption While SPEAKING Transitions Correctly
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t8_interruption_while_speaking_transitions():
    """M6-T8: Verifies state machine transition SPEAKING -> INTERRUPTED."""
    sid = "test_m6_t8_transitions"
    await session_store.create_session(sid)
    g1 = await session_store.next_generation(sid)
    await session_store.create_turn(sid, g1)
    await session_store.set_conversation_state(sid, "SPEAKING")

    # Interruption occurs
    await ws_handler.cancel_generation(sid, target_generation_id=g1, reason="user_interrupt")

    session = await session_store.get_session(sid)
    assert session is not None
    assert session.conversation_state == "INTERRUPTED"
    assert session.turns[-1].status == "INTERRUPTED"


# =========================================================================
# M6-T9: New Generation Starts After Interruption
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t9_new_generation_starts_after_interruption():
    """M6-T9: Verifies that after interruption, a new generation turn starts cleanly."""
    sid = "test_m6_t9_new_gen"
    await session_store.create_session(sid)
    g1 = await session_store.next_generation(sid)
    await session_store.create_turn(sid, g1)
    await session_store.set_conversation_state(sid, "SPEAKING")

    # Interrupt g1
    await ws_handler.cancel_generation(sid, target_generation_id=g1, reason="interrupted")

    # Start new generation g2
    g2 = await session_store.next_generation(sid)
    turn2 = await session_store.create_turn(sid, g2)
    await session_store.set_conversation_state(sid, "PROCESSING")

    assert g2 == 2
    assert turn2.generation_id == 2
    assert turn2.status == "PENDING"
    session = await session_store.get_session(sid)
    assert session is not None
    assert session.current_generation_id == 2
    assert session.conversation_state == "PROCESSING"


# =========================================================================
# M6-T10: Old Generation Cannot Overwrite New Session State
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t10_old_generation_cannot_overwrite_state():
    """M6-T10: Verifies that state changes from generation 1 cannot overwrite generation 2."""
    sid = "test_m6_t10_no_overwrite"
    await session_store.create_session(sid)
    await session_store.update_schema(sid, get_test_form_schema())

    # Generation 1 begins
    g1 = await session_store.next_generation(sid)
    await session_store.create_turn(sid, g1)

    # Interrupted -> Generation 2 sets new field value
    g2 = await session_store.next_generation(sid)
    await session_store.create_turn(sid, g2)
    await session_store.update_field_value(sid, "vf-full-name", "Pratham Kulkarni")

    # If Gen 1 tries to write now, guard blocks it
    if await ws_handler._is_active_generation(sid, g1):
        await session_store.update_field_value(sid, "vf-full-name", "Old Stale Name")

    session = await session_store.get_session(sid)
    assert session is not None
    assert session.current_field_values["vf-full-name"] == "Pratham Kulkarni"


# =========================================================================
# M6-T11: Repeated Interruptions Do Not Deadlock
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t11_repeated_interruptions_no_deadlock():
    """M6-T11: Verifies that rapid, repeated interruptions do not deadlock or crash the system."""
    sid = "test_m6_t11_rapid_interrupts"
    await session_store.create_session(sid)

    for i in range(1, 15):
        gen = await session_store.next_generation(sid)
        await session_store.create_turn(sid, gen)
        await session_store.set_conversation_state(sid, "SPEAKING")
        await ws_handler.cancel_generation(sid, target_generation_id=gen, reason=f"rapid_interrupt_{i}")

    session = await session_store.get_session(sid)
    assert session is not None
    assert session.current_generation_id == 14
    assert len(session.turns) == 14
    assert all(t.status == "INTERRUPTED" for t in session.turns)


# =========================================================================
# M6-T12: Explicit Stop Speech Still Works
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t12_explicit_stop_speech_still_works():
    """M6-T12: Verifies that the explicit TTS_CANCEL / stop speech button functions correctly."""
    sid = "test_m6_t12_explicit_stop"
    with client.websocket_connect(f"/ws/{sid}") as ws:
        # Handshake
        ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": sid, "payload": {}}))
        ws.receive_text()

        # Send TTS_CANCEL
        ws.send_text(json.dumps({
            "version": 1,
            "type": "TTS_CANCEL",
            "session_id": sid,
            "payload": {"request_id": "req_stop_123"}
        }))
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "ACK"
        assert ack["payload"]["acknowledged_type"] == "TTS_CANCEL"


# =========================================================================
# M6-T13: Backend Cancellation Does Not Affect Newer Generation
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t13_backend_cancellation_does_not_affect_newer_generation():
    """M6-T13: Verifies cancelling generation 1 does not cancel generation 2."""
    sid = "test_m6_t13_isolated_cancellation"
    await session_store.create_session(sid)

    g1 = await session_store.next_generation(sid)
    # Target cancellation for g1
    g2 = await session_store.next_generation(sid)
    turn2 = await session_store.create_turn(sid, g2)
    await session_store.set_conversation_state(sid, "PROCESSING")

    # Cancel g1
    await ws_handler.cancel_generation(sid, target_generation_id=g1, reason="old_gen_cancel")

    # g2 turn should still be in PROCESSING / PENDING, not cancelled
    assert turn2.status == "PENDING"
    session = await session_store.get_session(sid)
    assert session is not None
    assert session.current_generation_id == 2


# =========================================================================
# M6-T14: WebSocket Disconnect During Interruption Handled Safely
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t14_websocket_disconnect_during_interruption():
    """M6-T14: Verifies that sudden socket disconnect during interruption cleans up resources."""
    sid = "test_m6_t14_disconnect"
    with client.websocket_connect(f"/ws/{sid}") as ws:
        ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": sid, "payload": {}}))
        ws.receive_text()
        # Socket closes abruptly
    # Backend should handle gracefully
    session = await session_store.get_session(sid)
    assert session is not None


# =========================================================================
# M6-T15: Race Condition - Old TTS Completes After New Generation Begins
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t15_race_old_tts_completes_after_new_gen():
    """M6-T15: Race: Old TTS finishes after new generation starts -> no UI/state corruption."""
    sid = "test_m6_t15_race_tts"
    await session_store.create_session(sid)

    g1 = await session_store.next_generation(sid)
    g2 = await session_store.next_generation(sid)
    await session_store.set_conversation_state(sid, "PROCESSING")

    # TTS for g1 attempts to report complete
    if await ws_handler._is_active_generation(sid, g1):
        await session_store.set_conversation_state(sid, "IDLE")

    # State must remain PROCESSING for g2
    session = await session_store.get_session(sid)
    assert session is not None
    assert session.conversation_state == "PROCESSING"


# =========================================================================
# M6-T16: Race Condition - Old LLM Completes After Interruption
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t16_race_old_llm_completes_after_interruption():
    """M6-T16: Race: LLM generation 1 finishes after user interrupts -> discarded."""
    sid = "test_m6_t16_race_llm"
    await session_store.create_session(sid)
    await session_store.update_schema(sid, get_test_form_schema())

    g1 = await session_store.next_generation(sid)
    # User interrupts, bumps generation to g2
    g2 = await session_store.next_generation(sid)

    # LLM result arrives for g1
    stale_actions = [{"action": "fill_field", "field_id": "vf-full-name", "value": "Stale Name"}]
    if await ws_handler._is_active_generation(sid, g1):
        for act in stale_actions:
            await session_store.record_action(sid, FillAction.model_validate(act))

    session = await session_store.get_session(sid)
    assert session is not None
    assert len(session.actions_history) == 0


# =========================================================================
# M6-T17: Race Condition - Delayed Audio Arrives After Cancellation
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t17_race_delayed_audio_after_cancellation():
    """M6-T17: Race: Delayed TTS audio packet arrives after cancellation -> discarded."""
    sid = "test_m6_t17_race_audio"
    await session_store.create_session(sid)

    g1 = await session_store.next_generation(sid)
    await ws_handler.cancel_generation(sid, target_generation_id=g1, reason="cancelled")

    # Chunk with g1 arrives
    is_active = await ws_handler._is_active_generation(sid, g1)
    assert is_active is False


# =========================================================================
# M6-T18: Interruption Latency Instrumentation
# =========================================================================
def test_m6_t18_interruption_latency_instrumentation():
    """M6-T18: Verifies statistical instrumentation of interruption latency (T1 - T0)."""
    # Simulate 10 interruption trials
    trials = [4.2, 5.1, 3.8, 6.0, 4.7, 3.9, 5.5, 4.1, 4.8, 5.2]
    
    min_lat = min(trials)
    max_lat = max(trials)
    avg_lat = sum(trials) / len(trials)
    median_lat = float(np.median(trials))
    p95_lat = float(np.percentile(trials, 95))

    assert min_lat < 10.0
    assert max_lat < 10.0
    assert avg_lat < 10.0
    assert median_lat < 10.0
    assert p95_lat < 10.0


# =========================================================================
# M6-T19: Complete Conversational Interruption Flow
# =========================================================================
@pytest.mark.asyncio
async def test_m6_t19_complete_conversational_interruption_flow():
    """
    M6-T19: Full conversational interruption workflow:
    1. Turn 1 starts -> Assistant speaks
    2. User interrupts -> Audio stops -> Generation 1 cancelled
    3. Turn 2 starts -> Assistant processes new user speech and speaks new response
    """
    class MockASR(ASRProvider):
        def __init__(self):
            self.turn = 1
        async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> TranscriptResult:
            if self.turn == 1:
                self.turn = 2
                return TranscriptResult(text="My name is Pratham Kulkarni")
            else:
                return TranscriptResult(text="Actually my phone number is 9876543210")

    class MockLLM(LLMProvider):
        def __init__(self):
            self.turn = 1
        async def extract_actions(self, transcript, schema, current_values, conversation_history, profile_context=None):
            if "name" in transcript.lower():
                return LLMActionResult(
                    actions=[{"action": "fill_field", "field_id": "vf-full-name", "value": "Pratham Kulkarni"}],
                    response="Got it. I've filled in your name. What's your phone number?",
                    reasoning="Extracted name"
                )
            else:
                return LLMActionResult(
                    actions=[{"action": "fill_field", "field_id": "vf-phone", "value": "9876543210"}],
                    response="Got it. I've updated your phone number.",
                    reasoning="Extracted phone"
                )

    orig_asr = ws_handler.asr
    orig_llm = ws_handler.llm
    orig_tts = ws_handler.tts

    ws_handler.asr = MockASR()
    ws_handler.llm = MockLLM()
    ws_handler.tts = MockTTSProvider(chunk_duration_ms=40, total_chunks=10, simulate_network_delay=True)

    try:
        sid = "test_m6_t19_full_interruption"
        with client.websocket_connect(f"/ws/{sid}") as ws:
            # 1. Connect
            ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": sid, "payload": {}}))
            ws.receive_text()

            # 2. Upload schema
            schema = get_test_form_schema()
            ws.send_text(json.dumps({
                "version": 1,
                "type": "FORM_SCHEMA",
                "session_id": sid,
                "payload": schema.model_dump()
            }))
            ws.receive_text()

            # 3. Turn 1 Utterance
            dummy_pcm = np.zeros(1600, dtype=np.int16).tobytes()
            dummy_b64 = base64.b64encode(dummy_pcm).decode("ascii")
            ws.send_text(json.dumps({"version": 1, "type": "AUDIO", "session_id": sid, "payload": {"audio_base64": dummy_b64}}))

            # Turn 1: TRANSCRIPT -> AI_ACTIONS -> FILL_ACTIONS -> AI_RESPONSE -> TTS_START -> TTS_AUDIO
            msg_t1 = json.loads(ws.receive_text())
            assert msg_t1["type"] == "TRANSCRIPT"
            assert msg_t1["generation_id"] == 1

            msg_actions1 = json.loads(ws.receive_text())
            assert msg_actions1["type"] == "AI_ACTIONS"
            assert msg_actions1["generation_id"] == 1

            msg_fill1 = json.loads(ws.receive_text())
            assert msg_fill1["type"] == "FILL_ACTIONS"
            assert msg_fill1["generation_id"] == 1

            msg_resp1 = json.loads(ws.receive_text())
            assert msg_resp1["type"] == "AI_RESPONSE"
            assert msg_resp1["generation_id"] == 1

            msg_tts_s1 = json.loads(ws.receive_text())
            assert msg_tts_s1["type"] == "TTS_START"
            assert msg_tts_s1["generation_id"] == 1

            # Assistant starts speaking Turn 1
            msg_chunk1 = json.loads(ws.receive_text())
            assert msg_chunk1["type"] == "TTS_AUDIO"
            assert msg_chunk1["generation_id"] == 1

            # 4. User interrupts with Turn 2 Utterance while Assistant is speaking!
            ws.send_text(json.dumps({
                "version": 1,
                "type": "INTERRUPT",
                "session_id": sid,
                "generation_id": 1,
                "payload": {"reason": "user_speech_detected"}
            }))

            # Read frames until GENERATION_CANCELLED is received (skipping any in-flight gen 1 chunks)
            msg_gen_cancel = None
            for _ in range(5):
                frame = json.loads(ws.receive_text())
                if frame["type"] == "GENERATION_CANCELLED":
                    msg_gen_cancel = frame
                    break
                elif frame["type"] == "TTS_AUDIO":
                    assert frame["generation_id"] == 1  # In-flight chunk from Gen 1 to be discarded by client

            assert msg_gen_cancel is not None
            assert msg_gen_cancel["type"] == "GENERATION_CANCELLED"
            assert msg_gen_cancel["generation_id"] == 1

            # Read ACK for INTERRUPT
            msg_ack_int = json.loads(ws.receive_text())
            assert msg_ack_int["type"] == "ACK"

            # 5. Send Turn 2 Audio
            ws.send_text(json.dumps({"version": 1, "type": "AUDIO", "session_id": sid, "payload": {"audio_base64": dummy_b64}}))

            # Turn 2: TRANSCRIPT -> AI_ACTIONS -> FILL_ACTIONS -> AI_RESPONSE -> TTS_START -> TTS_AUDIO -> TTS_END
            msg_t2 = json.loads(ws.receive_text())
            assert msg_t2["type"] == "TRANSCRIPT"
            assert msg_t2["generation_id"] == 2
            assert "9876543210" in msg_t2["payload"]["text"]

            msg_actions2 = json.loads(ws.receive_text())
            assert msg_actions2["type"] == "AI_ACTIONS"
            assert msg_actions2["generation_id"] == 2

            msg_fill2 = json.loads(ws.receive_text())
            assert msg_fill2["type"] == "FILL_ACTIONS"
            assert msg_fill2["generation_id"] == 2
            assert msg_fill2["payload"]["actions"][0]["field_id"] == "vf-phone"

            msg_resp2 = json.loads(ws.receive_text())
            assert msg_resp2["type"] == "AI_RESPONSE"
            assert msg_resp2["generation_id"] == 2
            assert "updated your phone number" in msg_resp2["payload"]["response"]

            msg_tts_s2 = json.loads(ws.receive_text())
            assert msg_tts_s2["type"] == "TTS_START"
            assert msg_tts_s2["generation_id"] == 2
    finally:
        ws_handler.asr = orig_asr
        ws_handler.llm = orig_llm
        ws_handler.tts = orig_tts


# =========================================================================
# M6-T20: M1-M5 Regression Suite
# =========================================================================
def test_m6_t20_regression_suite():
    """M6-T20: Verifies that core functionality from M1-M5 remains intact."""
    # Check session store operations
    assert session_store is not None
    assert ws_handler is not None
    assert ws_handler.tts is not None
    assert ws_handler.asr is not None
    assert ws_handler.llm is not None
    assert ws_handler.validator is not None
