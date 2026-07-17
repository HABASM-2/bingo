"""Authenticated Lotto Spin realtime snapshots and heartbeat."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.lotto import service
from app.lotto.game_loop import ensure_game_loop
from app.lotto.manager import hub
from app.models.user import User

router = APIRouter()
RECEIVE_TIMEOUT_SECONDS = 45


def _authenticate(token: str) -> User | None:
    try:
        subject = decode_access_token(token).get("sub")
        if not subject:
            return None
        db = SessionLocal()
        try:
            return db.query(User).filter(User.id == UUID(subject)).first()
        finally:
            db.close()
    except Exception:
        return None


def _snapshot() -> dict:
    db = SessionLocal()
    try:
        return service.snapshot(db)
    finally:
        db.close()


@router.websocket("/ws/lotto")
async def lotto_ws(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4401)
        return
    user = await asyncio.to_thread(_authenticate, token)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    connection = await hub.connect(str(user.id), websocket)
    ensure_game_loop()
    try:
        await websocket.send_text(json.dumps(await asyncio.to_thread(_snapshot)))
        await websocket.send_text(
            json.dumps({"type": "wallet", "balance": str(user.balance)})
        )
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=RECEIVE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get("type") == "snapshot":
                await websocket.send_text(
                    json.dumps(await asyncio.to_thread(_snapshot))
                )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(connection)
