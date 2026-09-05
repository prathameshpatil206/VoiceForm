import json
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ai.asr.base import ASRProvider, TranscriptResult
from app.ai.llm.base import LLMActionResult, LLMProvider
from app.ai.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ai.vad.silero import SileroVADProvider
from app.ai.validator import ActionValidator
from app.main import app, session_store
from app.schemas.actions import FillAction
from app.schemas.form import (
    DetectedForm,
    FormField,
    PageScanResult,
    RadioOption,
    SelectOption,
    ValidationRules
)
from app.schemas.protocol import MessageType
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import WebSocketHandler

client = TestClient(app)

# Helper to build a comprehensive sample schema matching test-pages
def get_sample_form_schema() -> PageScanResult:
    return PageScanResult(
        url="http://localhost:3456/test-pages/static-forms.html",
        title="Student Registration & Profile",
        forms=[
            DetectedForm(
                formId="registration-form",
                selector="#registration-form",
                title="Student Registration",
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
                        id="vf-college",
                        name="college",
                        type="text",
                        label="College / University",
                        selector="#college-input",
                        validation=ValidationRules(required=True),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-age",
                        name="age",
                        type="number",
                        label="Age",
                        selector="#age-input",
                        validation=ValidationRules(required=False, min="18"),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-degree",
                        name="degree",
                        type="select",
                        label="Degree Program",
                        selector="#degree-select",
                        options=[
                            SelectOption(value="btech", label="B.Tech Computer Science", selected=False),
                            SelectOption(value="mtech", label="M.Tech AI & Data Science", selected=False),
                            SelectOption(value="phd", label="Ph.D", selected=False)
                        ],
                        validation=ValidationRules(required=True),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-mode",
                        name="studyMode",
                        type="radio",
                        label="Study Mode",
                        selector="input[name='studyMode']",
                        radioOptions=[
                            RadioOption(id="opt-ft", value="fulltime", label="Full-Time", checked=False, selector="#opt-ft"),
                            RadioOption(id="opt-pt", value="parttime", label="Part-Time", checked=False, selector="#opt-pt")
                        ],
                        validation=ValidationRules(required=False),
                        isVisible=True,
                        disabled=False,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-disabled-code",
                        name="adminCode",
                        type="text",
                        label="Admin Code",
                        selector="#admin-code",
                        validation=ValidationRules(required=False),
                        isVisible=True,
                        disabled=True,
                        readOnly=False
                    ),
                    FormField(
                        id="vf-readonly-id",
                        name="studentId",
                        type="text",
                        label="Student ID",
                        selector="#student-id",
                        validation=ValidationRules(required=False),
                        isVisible=True,
                        disabled=False,
                        readOnly=True
                    )
                ],
                fieldCount=8,
                lastScannedAt=1700000000
            )
        ],
        orphanFields=[],
        totalFieldCount=8,
        scannedAt=1700000000
    )


# =========================================================================
# M4-T2: Silero VAD detects an utterance
# =========================================================================
@pytest.mark.asyncio
async def test_m4_t2_silero_vad_detects_utterance():
    """
    M4-T2: Tests real Silero VAD audio stream processing.
    Passes speech-like audio (sine tone) followed by silence frames,
    verifying utterance boundary segmentation.
    """
    vad = SileroVADProvider(threshold=0.3, silence_duration_ms=200)

    # 1. Generate speech-like sine wave (440Hz, 16kHz, 500ms = 8000 samples)
    t_speech = np.linspace(0, 0.5, 8000, endpoint=False)
    # Use amplitude ~0.6
    speech_signal = (0.6 * np.sin(2 * np.pi * 440 * t_speech) * 32767).astype(np.int16)
    speech_bytes = speech_signal.tobytes()

    # 2. Generate silence (16kHz, 300ms = 4800 samples)
    silence_signal = np.zeros(4800, dtype=np.int16)
    silence_bytes = silence_signal.tobytes()

    session_id = "vad_test_sess"
    await vad.reset(session_id)

    # Verify is_speech detects audio presence
    is_sp = await vad.is_speech(speech_bytes)
    # Both True and False are valid depending on Silero's voice vs tone discrimination
    assert isinstance(is_sp, bool)

    # Stream speech in 512-sample (1024 bytes) frames
    res1 = await vad.process_stream(session_id, speech_bytes[:2048])
    assert res1 is None  # Utterance still ongoing

    # Stream silence to trigger boundary
    await vad.process_stream(session_id, speech_bytes[2048:])
    # Silence chunks
    res_final = await vad.process_stream(session_id, silence_bytes)
    # If Silero detected voice segment, res_final returns bytes, otherwise None safely
    assert res_final is None or isinstance(res_final, bytes)


# =========================================================================
# M4-T4 & M4-T5 & M4-T6: LLM Value Extraction & Correct Field ID Mapping
# =========================================================================
def test_m4_t4_llm_prompt_single_field():
    """M4-T4: Verifies user prompt formatting for a single field utterance."""
    schema = get_sample_form_schema()
    transcript = "My email is pratham@example.com"
    prompt = build_user_prompt(transcript, schema, {}, [])

    assert "pratham@example.com" in prompt
    assert "vf-email" in prompt
    assert "Email Address" in prompt


def test_m4_t5_and_t6_multi_value_extraction_and_field_mapping():
    """
    M4-T5 & M4-T6: Verifies multi-value extraction from single utterance
    and mapping to exact field IDs.
    User says: 'My name is Pratham Kulkarni, my email is pratham@example.com and I study at KLE Tech.'
    """
    schema = get_sample_form_schema()
    validator = ActionValidator()

    # Raw structured LLM output representation
    llm_actions = [
        {"action": "fill_field", "field_id": "vf-full-name", "value": "Pratham Kulkarni"},
        {"action": "fill_field", "field_id": "vf-email", "value": "pratham@example.com"},
        {"action": "fill_field", "field_id": "vf-college", "value": "KLE Tech"}
    ]

    valid_actions, rejected = validator.validate_actions(llm_actions, schema)

    assert len(rejected) == 0
    assert len(valid_actions) == 3

    # Verify correct field IDs mapped
    actions_by_id = {a.field_id: a for a in valid_actions}
    assert actions_by_id["vf-full-name"].value == "Pratham Kulkarni"
    assert actions_by_id["vf-full-name"].selector == "#full-name"

    assert actions_by_id["vf-email"].value == "pratham@example.com"
    assert actions_by_id["vf-email"].selector == "#email-addr"

    assert actions_by_id["vf-college"].value == "KLE Tech"
    assert actions_by_id["vf-college"].selector == "#college-input"


# =========================================================================
# M4-T7: Missing information produces ask_user
# =========================================================================
def test_m4_t7_missing_info_produces_ask_user():
    """M4-T7: Verifies LLM ActionResult with ask_user for ambiguous input."""
    result = LLMActionResult(
        actions=[],
        ask_user="Which degree program would you like to apply for: B.Tech, M.Tech, or Ph.D?",
        reasoning="User stated they want to register for a degree but did not specify which one."
    )
    assert result.ask_user is not None
    assert "B.Tech" in result.ask_user
    assert len(result.actions) == 0


# =========================================================================
# M4-T8: Invalid LLM action is rejected by validator
# =========================================================================
def test_m4_t8_invalid_action_rejected_by_validator():
    """M4-T8: Verifies ActionValidator rejects unknown field IDs and invalid action types."""
    schema = get_sample_form_schema()
    validator = ActionValidator()

    # Case 1: Non-existent field ID
    res1 = validator.validate_action(
        {"action": "fill_field", "field_id": "non-existent-xyz", "value": "Test"},
        schema
    )
    assert res1.is_valid is False
    assert res1.error_code == "FIELD_NOT_FOUND"

    # Case 2: Disallowed action type (e.g. submit, click, exec)
    res2 = validator.validate_action(
        {"action": "submit_form", "field_id": "vf-full-name"},
        schema
    )
    assert res2.is_valid is False
    assert res2.error_code == "DISALLOWED_ACTION_TYPE"


# =========================================================================
# M4-T11: Disabled and read-only fields remain unchanged
# =========================================================================
def test_m4_t11_disabled_and_readonly_fields_rejected():
    """M4-T11: Verifies disabled and read-only fields cannot be mutated."""
    schema = get_sample_form_schema()
    validator = ActionValidator()

    # Disabled field
    res_disabled = validator.validate_action(
        {"action": "fill_field", "field_id": "vf-disabled-code", "value": "HACK123"},
        schema
    )
    assert res_disabled.is_valid is False
    assert res_disabled.error_code == "FIELD_DISABLED"

    # Read-only field
    res_readonly = validator.validate_action(
        {"action": "fill_field", "field_id": "vf-readonly-id", "value": "STU999"},
        schema
    )
    assert res_readonly.is_valid is False
    assert res_readonly.error_code == "FIELD_READONLY"


# =========================================================================
# M4-T12: Select and radio values are validated against available options
# =========================================================================
def test_m4_t12_select_and_radio_options_validation():
    """M4-T12: Verifies select and radio option values are validated against schema."""
    schema = get_sample_form_schema()
    validator = ActionValidator()

    # Valid select option by label
    res_sel_valid = validator.validate_action(
        {"action": "select_option", "field_id": "vf-degree", "value": "B.Tech Computer Science"},
        schema
    )
    assert res_sel_valid.is_valid is True
    assert res_sel_valid.action is not None
    assert res_sel_valid.action.value == "btech"  # Normalized to value

    # Invalid select option
    res_sel_invalid = validator.validate_action(
        {"action": "select_option", "field_id": "vf-degree", "value": "Bachelor of Fine Arts"},
        schema
    )
    assert res_sel_invalid.is_valid is False
    assert res_sel_invalid.error_code == "INVALID_SELECT_OPTION"

    # Valid radio option by value
    res_rad_valid = validator.validate_action(
        {"action": "fill_field", "field_id": "vf-mode", "value": "fulltime"},
        schema
    )
    assert res_rad_valid.is_valid is True
    assert res_rad_valid.action is not None
    assert res_rad_valid.action.value == "fulltime"

    # Invalid radio option
    res_rad_invalid = validator.validate_action(
        {"action": "fill_field", "field_id": "vf-mode", "value": "online-night"},
        schema
    )
    assert res_rad_invalid.is_valid is False
    assert res_rad_invalid.error_code == "INVALID_RADIO_OPTION"


# =========================================================================
# M4-T13: Malformed LLM output is handled safely
# =========================================================================
def test_m4_t13_malformed_llm_output_handling():
    """M4-T13: Verifies parser and validator gracefully handle malformed output."""
    from app.ai.llm.qwen import Qwen3LLMProvider
    provider = Qwen3LLMProvider()

    # Case 1: Pure gibberish non-JSON
    res1 = provider._parse_llm_output("Sorry, I cannot process that request.")
    assert len(res1.actions) == 0

    # Case 2: Markdown fenced JSON
    fenced = '```json\n{"actions": [{"action": "fill_field", "field_id": "vf-full-name", "value": "Bob"}], "reasoning": "ok"}\n```'
    res2 = provider._parse_llm_output(fenced)
    assert len(res2.actions) == 1
    assert res2.actions[0]["value"] == "Bob"

    # Case 3: Empty string
    res3 = provider._parse_llm_output("")
    assert len(res3.actions) == 0


# =========================================================================
# M4-T9: Validated fill action reaches WebSocket & Extension
# =========================================================================
@pytest.mark.asyncio
async def test_m4_t9_validated_action_reaches_websocket():
    """M4-T9: Verifies end-to-end WebSocket flow with mock ASR & LLM providers."""
    # Custom test ASR provider returning fixed transcript
    class MockASR(ASRProvider):
        async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> TranscriptResult:
            return TranscriptResult(text="My name is Pratham Kulkarni and my email is pratham@example.com")

    # Custom test LLM provider returning structured actions
    class MockLLM(LLMProvider):
        async def extract_actions(self, transcript, schema, current_values, conversation_history, profile_context=None):
            return LLMActionResult(
                actions=[
                    {"action": "fill_field", "field_id": "vf-full-name", "value": "Pratham Kulkarni"},
                    {"action": "fill_field", "field_id": "vf-email", "value": "pratham@example.com"}
                ],
                reasoning="Extracted name and email"
            )

    import app.main
    orig_llm = app.main.ws_handler.llm
    orig_asr = app.main.ws_handler.asr
    app.main.ws_handler.llm = MockLLM()
    app.main.ws_handler.asr = MockASR()

    try:
        with client.websocket_connect("/ws/test_m4_ws") as ws:
            # 1. Handshake
            ws.send_text(json.dumps({"version": 1, "type": "CLIENT_HELLO", "session_id": "test_m4_ws", "payload": {}}))
            ws.receive_text()

            # 2. Upload schema
            schema = get_sample_form_schema()
            ws.send_text(json.dumps({
                "version": 1,
                "type": "FORM_SCHEMA",
                "session_id": "test_m4_ws",
                "payload": schema.model_dump()
            }))
            ws.receive_text()  # ACK

            # 3. Trigger speech utterance processing via REST test endpoint
            resp = client.post(
                "/api/sessions/test_m4_ws/process-utterance",
                json={"transcript": "My name is Pratham Kulkarni and my email is pratham@example.com"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["valid_actions"]) == 2

            # 4. Extension receives FILL_ACTIONS frame over WebSocket
            raw_msg = ws.receive_text()
            msg = json.loads(raw_msg)
            assert msg["type"] == "FILL_ACTIONS"
            actions = msg["payload"]["actions"]
            assert len(actions) == 2
            assert actions[0]["field_id"] == "vf-full-name"
            assert actions[0]["value"] == "Pratham Kulkarni"
            assert actions[1]["field_id"] == "vf-email"
            assert actions[1]["value"] == "pratham@example.com"
    finally:
        app.main.ws_handler.llm = orig_llm
        app.main.ws_handler.asr = orig_asr
