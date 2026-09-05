import asyncio
import base64
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ai.asr.base import ASRProvider, TranscriptResult
from app.ai.llm.base import LLMActionResult, LLMProvider
from app.ai.llm.prompts import build_conversational_response
from app.ai.tts.base import (
    TTSAPIError,
    TTSAuthenticationError,
    TTSCancelledError,
    TTSChunk,
    TTSNetworkError,
)
from app.ai.tts.mock import MockTTSProvider
from app.ai.tts.rime import RimeTTSProvider
from app.ai.tts.safety import sanitize_tts_text
from app.ai.validator import ActionValidator
from app.config import config
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
# M5-T1: TTS Provider Initialization
# =========================================================================
def test_m5_t1_tts_provider_initialization():
    """M5-T1: Verifies TTS provider initialization with default and custom configurations."""
    # 1. Default initialization
    provider_default = RimeTTSProvider(api_key="test-key")
    assert provider_default.speaker == config.RIME_SPEAKER
    assert provider_default.model_id == config.RIME_MODEL_ID
    assert provider_default.audio_format == config.RIME_AUDIO_FORMAT
    assert provider_default.sampling_rate == config.RIME_SAMPLING_RATE
    assert provider_default.base_url == config.RIME_BASE_URL.rstrip("/")

    # 2. Custom overrides
    provider_custom = RimeTTSProvider(
        api_key="custom-key",
        base_url="https://custom.rime.ai/v1/rime-tts/",
        speaker="astra",
        model_id="mistv3",
        audio_format="mp3",
        sampling_rate=22050,
        timeout_seconds=25.0
    )
    assert provider_custom.api_key == "custom-key"
    assert provider_custom.base_url == "https://custom.rime.ai/v1/rime-tts"
    assert provider_custom.speaker == "astra"
    assert provider_custom.model_id == "mistv3"
    assert provider_custom.audio_format == "mp3"
    assert provider_custom.sampling_rate == 22050
    assert provider_custom.timeout_seconds == 25.0


# =========================================================================
# M5-T2: Rime Request Generation
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t2_rime_request_generation():
    """M5-T2: Verifies Rime HTTP request headers, body payload, and endpoint URL."""
    provider = RimeTTSProvider(
        api_key="secret-rime-key-123",
        speaker="celeste",
        model_id="coda",
        audio_format="pcm",
        sampling_rate=16000
    )

    captured_request = {}

    # Mock httpx AsyncClient stream
    class MockStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_bytes(self, chunk_size=2048):
            yield b"\x00\x01\x02\x03"

    class MockAsyncClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, headers=None, json=None):
            captured_request["method"] = method
            captured_request["url"] = url
            captured_request["headers"] = headers
            captured_request["json"] = json
            return MockStreamResponse()

    with patch("httpx.AsyncClient", MockAsyncClient):
        chunks = []
        async for chunk in provider.synthesize_stream("Hello from VoiceForm"):
            chunks.append(chunk)

    assert captured_request["method"] == "POST"
    assert captured_request["url"] == "https://users.rime.ai/v1/rime-tts"
    assert captured_request["headers"]["Authorization"] == "Bearer secret-rime-key-123"
    assert captured_request["headers"]["Accept"] == "audio/pcm"
    assert captured_request["headers"]["Content-Type"] == "application/json"

    assert captured_request["json"]["text"] == "Hello from VoiceForm"
    assert captured_request["json"]["speaker"] == "celeste"
    assert captured_request["json"]["modelId"] == "coda"
    assert captured_request["json"]["samplingRate"] == 16000


# =========================================================================
# M5-T3: Authentication and Configuration Handling
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t3_auth_and_config_handling():
    """M5-T3: Verifies authentication validation and 401/403 error handling."""
    # 1. Missing credentials check
    unconfigured = RimeTTSProvider(api_key="")
    assert unconfigured.is_configured() is False

    with pytest.raises(TTSAuthenticationError) as exc_info:
        async for _ in unconfigured.synthesize_stream("Testing missing key"):
            pass
    assert "RIME_API_KEY is not set" in exc_info.value.message

    # 2. HTTP 401 Unauthorized handling
    provider = RimeTTSProvider(api_key="invalid-key")

    class Mock401Response:
        status_code = 401

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aread(self):
            return b'{"error": "Invalid API token"}'

    class Mock401Client:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, *args, **kwargs):
            return Mock401Response()

    with patch("httpx.AsyncClient", Mock401Client):
        with pytest.raises(TTSAuthenticationError) as exc_401:
            async for _ in provider.synthesize_stream("Unauthorized request"):
                pass
        assert "401" in exc_401.value.message


# =========================================================================
# M5-T4: Text Response Sent to Rime (TTS Safety Guard)
# =========================================================================
def test_m5_t4_tts_safety_sanitization():
    """M5-T4: Verifies TTS Safety rule: only intended conversational text is spoken."""
    # Case 1: Raw HTML and script tags stripped
    raw1 = "<p>Hello! <script>alert('pwned')</script> I have filled your form.</p>"
    safe1 = sanitize_tts_text(raw1)
    assert "<p>" not in safe1
    assert "<script>" not in safe1
    assert "alert" not in safe1
    assert "I have filled your form." in safe1

    # Case 2: DOM selectors and CSS paths stripped
    raw2 = "Filled field #email-addr and input[name='user_phone']. What is your name?"
    safe2 = sanitize_tts_text(raw2)
    assert "#email-addr" not in safe2
    assert "input[" not in safe2
    assert "What is your name?" in safe2

    # Case 3: Leaked API keys / secrets stripped
    raw3 = "Using key sk-1234567890abcdef1234567890 to submit your form."
    safe3 = sanitize_tts_text(raw3)
    assert "sk-1234567890abcdef1234567890" not in safe3
    assert "[redacted]" in safe3

    # Case 4: Leaked system prompts stripped
    raw4 = "You are VoiceForm AI. Got it. I've filled in your name."
    safe4 = sanitize_tts_text(raw4)
    assert "You are VoiceForm AI" not in safe4
    assert "I've filled in your name." in safe4

    # Case 5: Markdown JSON fences stripped
    raw5 = '```json\n{"actions": []}\n```\nGot it, what is your college?'
    safe5 = sanitize_tts_text(raw5)
    assert "```" not in safe5
    assert "actions" not in safe5
    assert "Got it, what is your college?" in safe5


# =========================================================================
# M5-T5 & M5-T7: Audio Response Received and Streamed Chunks
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t5_and_t7_audio_stream_chunks():
    """M5-T5 & M5-T7: Verifies receiving sequential audio chunks from TTS provider."""
    mock_provider = MockTTSProvider(
        format="pcm",
        sample_rate=16000,
        chunk_duration_ms=50,
        total_chunks=3,
        simulate_network_delay=False
    )

    chunks = []
    async for chunk in mock_provider.synthesize_stream("Test message for streaming"):
        chunks.append(chunk)

    # 3 data chunks + 1 final delimiter
    assert len(chunks) == 4
    for i in range(3):
        assert chunks[i].chunk_index == i
        assert len(chunks[i].audio_bytes) > 0
        assert chunks[i].format == "pcm"
        assert chunks[i].sample_rate == 16000
        assert chunks[i].is_final is False

    assert chunks[3].is_final is True
    assert chunks[3].audio_bytes == b""


# =========================================================================
# M5-T6 & M5-T8: Audio Playback Starts and Completes (WebSocket Level)
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t6_and_t8_playback_start_and_completion():
    """M5-T6 & M5-T8: Verifies TTS_START, sequential TTS_AUDIO chunks, and TTS_END."""
    orig_tts = ws_handler.tts
    test_mock_tts = MockTTSProvider(
        format="pcm",
        sample_rate=16000,
        chunk_duration_ms=30,
        total_chunks=2,
        simulate_network_delay=False
    )
    ws_handler.tts = test_mock_tts

    try:
        with client.websocket_connect("/ws/test_m5_stream") as ws:
            # Connect
            ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": "test_m5_stream", "payload": {}}))
            ws.receive_text()

            # Trigger explicit TTS_REQUEST
            ws.send_text(json.dumps({
                "version": 1,
                "type": "TTS_REQUEST",
                "session_id": "test_m5_stream",
                "payload": {"text": "Hello, your form is ready."}
            }))

            # 1. Expect TTS_START frame (M5-T6)
            msg_start = json.loads(ws.receive_text())
            assert msg_start["type"] == "TTS_START"
            assert msg_start["payload"]["format"] == "pcm"
            assert msg_start["payload"]["sample_rate"] == 16000
            assert "Hello, your form is ready." in msg_start["payload"]["text"]

            # 2. Expect TTS_AUDIO chunk 0
            chunk0 = json.loads(ws.receive_text())
            assert chunk0["type"] == "TTS_AUDIO"
            assert chunk0["payload"]["chunk_index"] == 0
            assert len(chunk0["payload"]["audio_base64"]) > 0

            # 3. Expect TTS_AUDIO chunk 1
            chunk1 = json.loads(ws.receive_text())
            assert chunk1["type"] == "TTS_AUDIO"
            assert chunk1["payload"]["chunk_index"] == 1

            # 4. Expect TTS_END frame (M5-T8)
            msg_end = json.loads(ws.receive_text())
            assert msg_end["type"] == "TTS_END"
            assert msg_end["payload"]["total_chunks"] == 2
    finally:
        ws_handler.tts = orig_tts


# =========================================================================
# M5-T9: Playback Cancellation
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t9_playback_cancellation():
    """M5-T9: Verifies cancel_tts halts the stream and sends TTS_CANCEL."""
    mock_tts = MockTTSProvider(chunk_duration_ms=100, total_chunks=10, simulate_network_delay=True)
    orig_tts = ws_handler.tts
    ws_handler.tts = mock_tts

    try:
        with client.websocket_connect("/ws/test_m5_cancel") as ws:
            ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": "test_m5_cancel", "payload": {}}))
            ws.receive_text()

            # Start TTS
            ws.send_text(json.dumps({
                "version": 1,
                "type": "TTS_REQUEST",
                "session_id": "test_m5_cancel",
                "payload": {"text": "Long speech text to cancel"}
            }))

            # Receive TTS_START
            msg_start = json.loads(ws.receive_text())
            req_id = msg_start["payload"]["request_id"]

            # Receive first audio chunk
            json.loads(ws.receive_text())

            # Send TTS_CANCEL
            ws.send_text(json.dumps({
                "version": 1,
                "type": "TTS_CANCEL",
                "session_id": "test_m5_cancel",
                "payload": {"request_id": req_id}
            }))

            # Drain messages until ACK or TTS_CANCEL is received
            received_types = []
            audio_chunk_count = 1  # Chunk 0 was already received
            for _ in range(12):
                msg = json.loads(ws.receive_text())
                received_types.append(msg["type"])
                if msg["type"] == "TTS_AUDIO":
                    audio_chunk_count += 1
                if msg["type"] in ("ACK", "TTS_CANCEL"):
                    break

            assert "ACK" in received_types or "TTS_CANCEL" in received_types
            # Stream stopped early: far fewer than total 10 chunks arrived
            assert audio_chunk_count < 10

            # Verify session state is IDLE
            session = await session_store.get_session("test_m5_cancel")
            assert session is not None
            assert session.processing_state == "IDLE"
    finally:
        ws_handler.tts = orig_tts



# =========================================================================
# M5-T10: TTS Error Handling (Form State Never Corrupted)
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t10_error_handling_preserves_form_state():
    """
    M5-T10: Verifies TTS errors emit TTS_ERROR and NEVER corrupt or revert
    successfully filled form actions.
    """
    # Create a failing TTS provider simulating API failure
    failing_tts = MockTTSProvider(simulate_error="API_ERROR")
    orig_tts = ws_handler.tts
    ws_handler.tts = failing_tts

    try:
        session_id = "test_m5_err_preserve"
        with client.websocket_connect(f"/ws/{session_id}") as ws:
            ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": session_id, "payload": {}}))
            ws.receive_text()

            # 1. Send schema
            schema = get_test_form_schema()
            ws.send_text(json.dumps({
                "version": 1,
                "type": "FORM_SCHEMA",
                "session_id": session_id,
                "payload": schema.model_dump()
            }))
            ws.receive_text()

            # 2. Directly trigger a fill action into session
            fill_action = FillAction(field_id="vf-full-name", value="Ada Lovelace")
            await session_store.record_action(session_id, fill_action)
            await session_store.update_field_value(session_id, "vf-full-name", "Ada Lovelace")

            # 3. Trigger TTS that fails with 500 error
            ws.send_text(json.dumps({
                "version": 1,
                "type": "TTS_REQUEST",
                "session_id": session_id,
                "payload": {"text": "I will fail during speech generation."}
            }))

            # Expect TTS_START
            json.loads(ws.receive_text())

            # Expect TTS_ERROR frame
            err_msg = json.loads(ws.receive_text())
            assert err_msg["type"] == "TTS_ERROR"
            assert err_msg["payload"]["error_code"] == "TTS_API_ERROR"

            # 4. CRITICAL VERIFICATION: Check session store form state is completely intact
            session = await session_store.get_session(session_id)
            assert session is not None
            assert session.current_field_values["vf-full-name"] == "Ada Lovelace"
            assert len(session.actions_history) == 1
            assert session.actions_history[0].value == "Ada Lovelace"
    finally:
        ws_handler.tts = orig_tts


# =========================================================================
# M5-T11: WebSocket TTS Messages Protocol
# =========================================================================
def test_m5_t11_websocket_tts_messages_protocol():
    """M5-T11: Verifies all M5 protocol message schemas validate cleanly."""
    from app.schemas.protocol import (
        TtsAudioPayload,
        TtsCancelPayload,
        TtsEndPayload,
        TtsErrorPayload,
        TtsRequestPayload,
        TtsStartPayload,
        WebSocketMessage,
    )

    req = WebSocketMessage[TtsRequestPayload](
        type=MessageType.TTS_REQUEST,
        session_id="sess_123",
        payload=TtsRequestPayload(text="Hello", speaker="celeste")
    )
    assert req.type == MessageType.TTS_REQUEST

    start = WebSocketMessage[TtsStartPayload](
        type=MessageType.TTS_START,
        session_id="sess_123",
        payload=TtsStartPayload(request_id="req_1", text="Hello", format="pcm", sample_rate=16000)
    )
    assert start.payload.format == "pcm"

    audio = WebSocketMessage[TtsAudioPayload](
        type=MessageType.TTS_AUDIO,
        session_id="sess_123",
        payload=TtsAudioPayload(request_id="req_1", chunk_index=0, audio_base64="AQIDBA==", format="pcm")
    )
    assert audio.payload.chunk_index == 0

    end = WebSocketMessage[TtsEndPayload](
        type=MessageType.TTS_END,
        session_id="sess_123",
        payload=TtsEndPayload(request_id="req_1", total_chunks=1)
    )
    assert end.payload.total_chunks == 1

    err = WebSocketMessage[TtsErrorPayload](
        type=MessageType.TTS_ERROR,
        session_id="sess_123",
        payload=TtsErrorPayload(request_id="req_1", error_code="TTS_ERROR", message="Failed")
    )
    assert err.payload.error_code == "TTS_ERROR"

    cancel = WebSocketMessage[TtsCancelPayload](
        type=MessageType.TTS_CANCEL,
        session_id="sess_123",
        payload=TtsCancelPayload(request_id="req_1", reason="User stopped")
    )
    assert cancel.payload.reason == "User stopped"


# =========================================================================
# M5-T12: Assistant Response Remains Separate from Form Actions
# =========================================================================
def test_m5_t12_assistant_response_separate_from_actions():
    """
    M5-T12: Verifies structured actions and spoken response remain separate.
    ActionValidator operates purely on actions, while response provides dialogue.
    """
    schema = get_test_form_schema()
    validator = ActionValidator()

    # Raw LLM extraction containing both actions and spoken response
    llm_res = LLMActionResult(
        actions=[
            {"action": "fill_field", "field_id": "vf-full-name", "value": "Pratham Kulkarni"},
            {"action": "fill_field", "field_id": "vf-email", "value": "pratham@example.com"}
        ],
        response="Got it. I've filled in your name and email. What's your phone number?",
        reasoning="Extracted name and email from utterance"
    )

    # 1. Validator validates actions completely independently
    valid_actions, rejected = validator.validate_actions(llm_res.actions, schema)
    assert len(rejected) == 0
    assert len(valid_actions) == 2

    # 2. Spoken response remains untouched and independent
    assert llm_res.response == "Got it. I've filled in your name and email. What's your phone number?"
    assert "vf-full-name" not in llm_res.response
    assert "selector" not in llm_res.response

    # 3. Helper produces contextual response if response was absent
    fallback_resp = build_conversational_response(
        filled_labels=["Full Name", "Email Address"],
        remaining_required_labels=["Phone Number"]
    )
    assert "Full Name and Email Address" in fallback_resp
    assert "Phone Number" in fallback_resp


# =========================================================================
# M5-T13: Complete Flow (Utterance -> ASR -> LLM -> Filler -> TTS)
# =========================================================================
@pytest.mark.asyncio
async def test_m5_t13_complete_flow():
    """
    M5-T13: Complete end-to-end voice flow test:
    User Utterance
    -> ASR (mock)
    -> LLM (mock)
    -> ActionValidator
    -> FILL_ACTIONS dispatched to extension
    -> Assistant Response generated
    -> Rime/Mock TTS synthesizes speech
    -> Audio chunks streamed down WebSocket
    """
    class MockASR(ASRProvider):
        async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> TranscriptResult:
            return TranscriptResult(text="My name is Pratham Kulkarni and my email is pratham@example.com")

    class MockLLM(LLMProvider):
        async def extract_actions(self, transcript, schema, current_values, conversation_history, profile_context=None):
            return LLMActionResult(
                actions=[
                    {"action": "fill_field", "field_id": "vf-full-name", "value": "Pratham Kulkarni"},
                    {"action": "fill_field", "field_id": "vf-email", "value": "pratham@example.com"}
                ],
                response="Got it. I've filled in your name and email. What's your phone number?",
                reasoning="Extracted name and email"
            )

    orig_asr = ws_handler.asr
    orig_llm = ws_handler.llm
    orig_tts = ws_handler.tts

    ws_handler.asr = MockASR()
    ws_handler.llm = MockLLM()
    ws_handler.tts = MockTTSProvider(chunk_duration_ms=20, total_chunks=2, simulate_network_delay=False)

    try:
        session_id = "test_m5_complete_flow"
        with client.websocket_connect(f"/ws/{session_id}") as ws:
            # 1. Connect
            ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": session_id, "payload": {}}))
            ws.receive_text()

            # 2. Upload schema
            schema = get_test_form_schema()
            ws.send_text(json.dumps({
                "version": 1,
                "type": "FORM_SCHEMA",
                "session_id": session_id,
                "payload": schema.model_dump()
            }))
            ws.receive_text()

            # 3. Simulate user speech audio chunk received from extension mic
            dummy_pcm = np.zeros(1600, dtype=np.int16).tobytes()
            dummy_b64 = base64.b64encode(dummy_pcm).decode("ascii")

            # Send AUDIO message
            ws.send_text(json.dumps({
                "version": 1,
                "type": "AUDIO",
                "session_id": session_id,
                "payload": {"audio_base64": dummy_b64}
            }))

            # 4. Expect TRANSCRIPT
            msg_t = json.loads(ws.receive_text())
            assert msg_t["type"] == "TRANSCRIPT"
            assert "Pratham Kulkarni" in msg_t["payload"]["text"]

            # 5. Expect AI_ACTIONS frame
            msg_ai = json.loads(ws.receive_text())
            assert msg_ai["type"] == "AI_ACTIONS"

            # 6. Expect FILL_ACTIONS batch for DOM filler
            msg_fill = json.loads(ws.receive_text())
            assert msg_fill["type"] == "FILL_ACTIONS"
            assert len(msg_fill["payload"]["actions"]) == 2

            # 7. Expect AI_RESPONSE frame with assistant conversational response
            msg_resp = json.loads(ws.receive_text())
            assert msg_resp["type"] == "AI_RESPONSE"
            assert "What's your phone number?" in msg_resp["payload"]["response"]

            # 8. Expect TTS_START frame
            msg_tts_start = json.loads(ws.receive_text())
            assert msg_tts_start["type"] == "TTS_START"
            assert msg_tts_start["payload"]["format"] == "pcm"

            # 9. Expect TTS_AUDIO chunks
            msg_tts_c0 = json.loads(ws.receive_text())
            assert msg_tts_c0["type"] == "TTS_AUDIO"
            assert msg_tts_c0["payload"]["chunk_index"] == 0

            msg_tts_c1 = json.loads(ws.receive_text())
            assert msg_tts_c1["type"] == "TTS_AUDIO"
            assert msg_tts_c1["payload"]["chunk_index"] == 1

            # 10. Expect TTS_END frame
            msg_tts_end = json.loads(ws.receive_text())
            assert msg_tts_end["type"] == "TTS_END"
            assert msg_tts_end["payload"]["total_chunks"] == 2
    finally:
        ws_handler.asr = orig_asr
        ws_handler.llm = orig_llm
        ws_handler.tts = orig_tts


# =========================================================================
# Live Integration Test (Conditional on RIME_API_KEY)
# =========================================================================
@pytest.mark.asyncio
async def test_live_rime_tts_integration():
    """
    Live Rime API integration test.
    Automatically runs when RIME_API_KEY is configured in the environment or backend/.env.
    If RIME_API_KEY is not set, safely skips and reports the requirement.
    """
    from app.config import settings
    api_key = (settings.RIME_API_KEY or os.getenv("RIME_API_KEY", "")).strip()
    if not api_key:
        pytest.skip("RIME_API_KEY is not set in environment. Skipping live Rime API call.")

    provider = RimeTTSProvider(
        api_key=api_key,
        speaker=settings.RIME_SPEAKER,
        model_id=settings.RIME_MODEL_ID,
        audio_format=settings.RIME_AUDIO_FORMAT,
        sampling_rate=settings.RIME_SAMPLING_RATE,
    )
    assert provider.is_configured() is True

    chunks = []
    total_bytes = 0
    async for chunk in provider.synthesize_stream("VoiceForm Milestone 5 live test."):
        chunks.append(chunk)
        total_bytes += len(chunk.audio_bytes)

    assert len(chunks) > 0
    assert total_bytes > 0
    assert chunks[-1].is_final is True
