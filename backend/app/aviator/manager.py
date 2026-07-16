"""Aviator hub — broadcast to all connected players."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class ConnectionInfo:
    websocket: WebSocket
    user_id: str
    display_name: str
    token: str = ""
    last_seen: float = field(default_factory=time.time)


class AviatorHub:
    def __init__(self) -> None:
        self._by_user: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, display_name: str, websocket: WebSocket) -> str:
        stale: ConnectionInfo | None = None
        token = uuid.uuid4().hex
        async with self._lock:
            stale = self._by_user.get(user_id)
            self._by_user[user_id] = ConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                display_name=display_name,
                token=token,
            )
        if stale is not None:
            try:
                await stale.websocket.close(code=4409, reason="Replaced by new connection")
            except Exception:
                pass
        return token

    async def disconnect(self, user_id: str, token: str | None = None) -> bool:
        async with self._lock:
            conn = self._by_user.get(user_id)
            if conn is None:
                return False
            if token is not None and conn.token != token:
                return False
            self._by_user.pop(user_id, None)
            return True

    def touch(self, user_id: str) -> None:
        conn = self._by_user.get(user_id)
        if conn is not None:
            conn.last_seen = time.time()

    async def send(self, user_id: str, message: dict) -> bool:
        conn = self._by_user.get(user_id)
        if conn is None:
            return False
        try:
            await conn.websocket.send_text(json.dumps(message))
            return True
        except Exception:
            return False

    async def broadcast(self, message: dict, *, exclude: str | None = None) -> None:
        connections = [
            c for uid, c in self._by_user.items() if exclude is None or uid != exclude
        ]
        if not connections:
            return
        payload = json.dumps(message)
        await asyncio.gather(
            *(c.websocket.send_text(payload) for c in connections),
            return_exceptions=True,
        )


hub = AviatorHub()
