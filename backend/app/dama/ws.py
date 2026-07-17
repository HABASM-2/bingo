"""WebSocket endpoint for online Dama lobby, challenges, and matches."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.dama import service
from app.dama.manager import hub
from app.dama.service import DamaError
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


@router.websocket("/ws/dama")
async def dama_ws(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4401)
        return

    user = await asyncio.to_thread(_authenticate, token)
    if user is None:
        await websocket.close(code=4401)
        return

    user_id = str(user.id)
    display_name = _display_name(user)
    photo_url = getattr(user, "photo_url", None)

    await websocket.accept()
    conn_token = await hub.connect(user_id, display_name, websocket)

    try:
        snapshot = await service.join_lobby(user_id, display_name, photo_url)
        await websocket.send_text(json.dumps(snapshot))

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

                elif msg_type == "list_players":
                    await websocket.send_text(
                        json.dumps(await service.presence_snapshot(user_id))
                    )

                elif msg_type == "challenge":
                    to_user_id = str(message.get("to_user_id") or "")
                    stake = message.get("stake", "10")
                    result = await service.send_challenge(user_id, to_user_id, stake)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "accept_challenge":
                    challenge_id = str(message.get("challenge_id") or "")
                    result = await service.accept_challenge(user_id, challenge_id)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "decline_challenge":
                    challenge_id = str(message.get("challenge_id") or "")
                    result = await service.decline_challenge(user_id, challenge_id)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "cancel_challenge":
                    challenge_id = str(message.get("challenge_id") or "")
                    result = await service.cancel_challenge(user_id, challenge_id)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "move":
                    match_id = str(message.get("match_id") or "")
                    from_sq = int(message["from"])
                    to_sq = int(message["to"])
                    await service.apply_player_move(user_id, match_id, from_sq, to_sq)

                elif msg_type == "resign":
                    match_id = str(message.get("match_id") or "")
                    await service.resign(user_id, match_id)

                elif msg_type == "offer_draw":
                    match_id = str(message.get("match_id") or "")
                    result = await service.offer_draw(user_id, match_id)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "accept_draw":
                    match_id = str(message.get("match_id") or "")
                    await service.accept_draw(user_id, match_id)

                elif msg_type == "decline_draw":
                    match_id = str(message.get("match_id") or "")
                    result = await service.decline_draw(user_id, match_id)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "claim_timeout":
                    match_id = str(message.get("match_id") or "")
                    await service.claim_timeout(user_id, match_id)

                elif msg_type == "offer_rematch":
                    match_id = str(message.get("match_id") or "")
                    stake = message.get("stake")
                    result = await service.offer_rematch(user_id, match_id, stake)
                    await websocket.send_text(json.dumps(result))

                elif msg_type == "accept_rematch":
                    match_id = str(message.get("match_id") or "")
                    stake = message.get("stake")
                    result = await service.accept_rematch(user_id, match_id, stake)
                    await websocket.send_text(json.dumps(result))

                else:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "Unknown message"})
                    )

            except DamaError as exc:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": exc.message})
                )
            except (KeyError, TypeError, ValueError):
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Bad message"})
                )
            except Exception:
                logger.exception("dama ws handler error")
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Server error"})
                )

    except WebSocketDisconnect:
        pass
    finally:
        removed = await hub.disconnect(user_id, conn_token)
        if removed:
            await service.leave_lobby(user_id)
