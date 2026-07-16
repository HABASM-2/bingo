"""WebSocket for live Aviator rounds."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.aviator import service
from app.aviator.game_loop import ensure_game_loop
from app.aviator.manager import hub
from app.aviator.service import AviatorError
from app.db.database import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()
RECEIVE_TIMEOUT_SECONDS = 60


def _authenticate(token: str) -> User | None:
    try:
        payload = decode_access_token(token)
    except Exception:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == UUID(user_id)).first()
    except Exception:
        return None
    finally:
        db.close()


def _display_name(user: User) -> str:
    return user.first_name or user.username or f"Player {str(user.id)[:6]}"


@router.websocket("/ws/aviator")
async def aviator_ws(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4401)
        return

    user = _authenticate(token)
    if user is None:
        await websocket.close(code=4401)
        return

    user_id = str(user.id)
    display_name = _display_name(user)

    await websocket.accept()
    ensure_game_loop()
    conn_token = await hub.connect(user_id, display_name, websocket)

    try:
        import asyncio

        from app.aviator import wallet as aviator_wallet

        snap = await service.snapshot()
        bal = await asyncio.to_thread(aviator_wallet.get_balance, user_id)
        if bal:
            snap["balance"] = bal
        await websocket.send_text(json.dumps(snap))

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=RECEIVE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            hub.touch(user_id)

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Invalid JSON"})
                )
                continue

            msg_type = message.get("type")
            try:
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                elif msg_type == "snapshot":
                    snap = await service.snapshot()
                    bal = await asyncio.to_thread(aviator_wallet.get_balance, user_id)
                    if bal:
                        snap["balance"] = bal
                    await websocket.send_text(json.dumps(snap))

                elif msg_type == "bet":
                    stake = message.get("stake")
                    slot = int(message.get("slot") or 0)
                    result = await service.place_bet(user_id, display_name, stake, slot)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "cashout":
                    bet_id = message.get("bet_id")
                    slot = message.get("slot")
                    slot_i = int(slot) if slot is not None else None
                    result = await service.cash_out(
                        user_id,
                        str(bet_id) if bet_id else None,
                        slot_i,
                    )
                    await websocket.send_text(json.dumps(result))

                else:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "Unknown message"})
                    )

            except AviatorError as exc:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": exc.message})
                )
            except (KeyError, TypeError, ValueError) as exc:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": str(exc) or "Bad message"})
                )
            except Exception:
                logger.exception("aviator ws handler error")
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Server error"})
                )

    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(user_id, conn_token)
