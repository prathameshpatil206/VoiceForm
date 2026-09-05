import json
import logging
from typing import Dict, List, Optional
from fastapi import WebSocket
from app.schemas.protocol import BaseMessage

logger = logging.getLogger("voiceform.ws")

class ConnectionManager:
    """
    Manages active WebSocket connections mapped by session_id.
    """

    def __init__(self) -> None:
        # session_id -> list of active websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"Connected client to session={session_id}. Active tabs={len(self.active_connections[session_id])}")

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"Disconnected client from session={session_id}")

    async def send_message(self, session_id: str, message: BaseMessage) -> bool:
        """Sends a typed message to all active sockets connected to this session."""
        connections = self.active_connections.get(session_id, [])
        if not connections:
            logger.warning(f"No active WebSocket connections found for session={session_id}")
            return False

        payload_json = message.model_dump_json()
        dead_connections: List[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(payload_json)
            except Exception as e:
                logger.error(f"Failed to send to socket in session={session_id}: {e}")
                dead_connections.append(ws)

        for dead_ws in dead_connections:
            self.disconnect(dead_ws, session_id)

        return True

    async def send_raw_text(self, websocket: WebSocket, text: str) -> None:
        await websocket.send_text(text)

    def is_connected(self, session_id: str) -> bool:
        return bool(self.active_connections.get(session_id))
