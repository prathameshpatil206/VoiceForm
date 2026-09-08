import json
import pytest
from fastapi.testclient import TestClient

from app.main import app, session_store
from app.schemas.actions import FillAction
from app.schemas.form import FormField, PageScanResult, DetectedForm

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["protocol_version"] == 1

def test_t1_websocket_connection():
    """T1: Verifies WebSocket connection can be established cleanly."""
    with client.websocket_connect("/ws/test_conn_1") as ws:
        assert ws is not None

def test_t2_session_creation():
    """T2: Verifies CLIENT_HELLO creates session and replies with SERVER_HELLO."""
    with client.websocket_connect("/ws/test_session_2") as ws:
        ws.send_text(json.dumps({
            "version": 1,
            "type": "CLIENT_HELLO",
            "session_id": "test_session_2",
            "timestamp": 1234567890,
            "payload": {"metadata": {"agent": "chrome-test"}}
        }))

        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)
        assert resp["version"] == 1
        assert resp["type"] == "SERVER_HELLO"
        assert resp["session_id"] == "test_session_2"
        assert resp["payload"]["status"] == "ready"

def test_t3_and_t4_form_schema_and_ack():
    """T3 & T4: Verifies FORM_SCHEMA transmission and ACK response."""
    with client.websocket_connect("/ws/test_schema_3") as ws:
        # 1. Initialize
        ws.send_text(json.dumps({
            "version": 1,
            "type": "CLIENT_HELLO",
            "session_id": "test_schema_3",
            "payload": {}
        }))
        ws.receive_text()

        # 2. Send Form Schema
        sample_schema = PageScanResult(
            url="http://localhost:3456/test-pages/static-forms.html",
            title="Static Forms",
            forms=[
                DetectedForm(
                    formId="profile-form",
                    selector="#profile-form",
                    title="User Profile",
                    fields=[
                        FormField(
                            id="first-name",
                            name="firstName",
                            type="text",
                            label="First Name",
                            selector="#first-name",
                            isVisible=True,
                            disabled=False,
                            readOnly=False
                        )
                    ],
                    fieldCount=1,
                    lastScannedAt=12345
                )
            ],
            orphanFields=[],
            totalFieldCount=1,
            scannedAt=12345
        )

        ws.send_text(json.dumps({
            "version": 1,
            "type": "FORM_SCHEMA",
            "session_id": "test_schema_3",
            "payload": sample_schema.model_dump()
        }))

        raw_ack = ws.receive_text()
        ack = json.loads(raw_ack)
        assert ack["version"] == 1
        assert ack["type"] == "ACK"
        assert ack["payload"]["acknowledged_type"] == "FORM_SCHEMA"
        assert ack["payload"]["status"] == "ok"

def test_t5_structured_fill_action():
    """T5: Verifies backend can dispatch structured FILL_ACTION to client."""
    with client.websocket_connect("/ws/test_fill_5") as ws:
        # Initialize session
        ws.send_text(json.dumps({
            "version": 1,
            "type": "CLIENT_HELLO",
            "session_id": "test_fill_5",
            "payload": {}
        }))
        ws.receive_text()

        # Call REST endpoint to trigger fill action on session
        resp = client.post(
            "/api/sessions/test_fill_5/trigger-fill",
            json={
                "action": {
                    "action": "fill_field",
                    "field_id": "first-name",
                    "value": "Bob Vance"
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Receive action frame on the WebSocket
        raw_msg = ws.receive_text()
        msg = json.loads(raw_msg)
        assert msg["type"] == "FILL_ACTION"
        assert msg["session_id"] == "test_fill_5"
        assert msg["payload"]["field_id"] == "first-name"
        assert msg["payload"]["value"] == "Bob Vance"

def test_t7_malformed_message_handling():
    """T7: Verifies malformed JSON or unsupported version/type returns structured ERROR."""
    with client.websocket_connect("/ws/test_err_7") as ws:
        # Invalid JSON
        ws.send_text("THIS IS NOT JSON")
        raw_err = ws.receive_text()
        err = json.loads(raw_err)
        assert err["type"] == "ERROR"
        assert err["payload"]["error_code"] == "MALFORMED_JSON"

        # Unsupported protocol version
        ws.send_text(json.dumps({"version": 99, "type": "PING", "session_id": "test_err_7"}))
        raw_err = ws.receive_text()
        err = json.loads(raw_err)
        assert err["type"] == "ERROR"
        assert err["payload"]["error_code"] == "UNSUPPORTED_VERSION"

        # Unknown message type
        ws.send_text(json.dumps({"version": 1, "type": "FAKE_TYPE", "session_id": "test_err_7"}))
        raw_err = ws.receive_text()
        err = json.loads(raw_err)
        assert err["type"] == "ERROR"
        assert err["payload"]["error_code"] == "UNKNOWN_MESSAGE_TYPE"

def test_t8_disconnect_reconnect():
    """T8: Verifies disconnect and reconnect to the same session preserves state."""
    # First connection
    with client.websocket_connect("/ws/test_reconn_8") as ws1:
        ws1.send_text(json.dumps({
            "version": 1,
            "type": "CLIENT_HELLO",
            "session_id": "test_reconn_8",
            "payload": {"metadata": {"step": 1}}
        }))
        ws1.receive_text()

    # Reconnect with same session ID
    with client.websocket_connect("/ws/test_reconn_8") as ws2:
        ws2.send_text(json.dumps({
            "version": 1,
            "type": "PING",
            "session_id": "test_reconn_8",
            "payload": {}
        }))
        raw_pong = ws2.receive_text()
        pong = json.loads(raw_pong)
        assert pong["type"] == "PONG"
        assert pong["session_id"] == "test_reconn_8"

def test_t9_multiple_independent_sessions():
    """T9: Verifies multiple independent sessions maintain distinct state."""
    with client.websocket_connect("/ws/session_alpha") as ws_a, \
         client.websocket_connect("/ws/session_beta") as ws_b:

        ws_a.send_text(json.dumps({
            "version": 1, "type": "CLIENT_HELLO", "session_id": "session_alpha", "payload": {}
        }))
        ws_b.send_text(json.dumps({
            "version": 1, "type": "CLIENT_HELLO", "session_id": "session_beta", "payload": {}
        }))

        resp_a = json.loads(ws_a.receive_text())
        resp_b = json.loads(ws_b.receive_text())

        assert resp_a["session_id"] == "session_alpha"
        assert resp_b["session_id"] == "session_beta"

def test_t10_direct_transcript_message():
    """T10: Verifies direct TRANSCRIPT message triggers text pipeline and echoes transcript."""
    with client.websocket_connect("/ws/test_transcript_10") as ws:
        # 1. Initialize session
        ws.send_text(json.dumps({
            "version": 1,
            "type": "CLIENT_HELLO",
            "session_id": "test_transcript_10",
            "payload": {}
        }))
        ws.receive_text()

        # 2. Send direct TRANSCRIPT message
        ws.send_text(json.dumps({
            "version": 1,
            "type": "TRANSCRIPT",
            "session_id": "test_transcript_10",
            "payload": {
                "text": "Hello world my name is Alice",
                "is_final": True
            }
        }))

        # Expect echoed TRANSCRIPT
        raw_transcript = ws.receive_text()
        transcript = json.loads(raw_transcript)
        assert transcript["version"] == 1
        assert transcript["type"] == "TRANSCRIPT"
        assert transcript["payload"]["text"] == "Hello world my name is Alice"
        assert transcript["payload"]["is_final"] is True

        # Expect AI_ERROR (NO_FORM_SCHEMA because no schema was sent)
        raw_err = ws.receive_text()
        err = json.loads(raw_err)
        assert err["version"] == 1
        assert err["type"] == "AI_ERROR"
        assert err["payload"]["error_code"] == "NO_FORM_SCHEMA"
