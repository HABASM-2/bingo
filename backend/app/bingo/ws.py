"""WebSocket endpoint for live Bingo gameplay.

Auth: JWT passed as ``?token=`` (browsers can't set custom headers on the
WebSocket handshake), decoded with the same ``decode_access_token`` used by
the REST API. The handler loop itself only ever parses JSON and delegates
to ``app.bingo.service`` - no heavy work (Redis I/O, validation) happens
inline beyond what those calls already need.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.bingo import game_loop, redis_store, service, wallet
from app.bingo.manager import manager
from app.bingo.service import BingoError
from app.core.config import settings
from app.db.database import SessionLocal
from app.core.security import decode_access_token
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

RECEIVE_TIMEOUT_SECONDS = 60


def _parse_board_id(raw) -> int:
    """Accept plain ints (and int-valued floats from quirky JSON codecs)."""

    if isinstance(raw, bool):
        raise BingoError("Invalid board id")

    if isinstance(raw, int):
        return raw

    if isinstance(raw, float) and raw.is_integer():
        return int(raw)

    raise BingoError("Invalid board id")


async def _allow(user_id: str, action: str, limit: int, window_ms: int) -> bool:
    """Server-side abuse throttle. Returns False when the caller is over the
    limit; the WS dispatcher converts that into a user-visible error toast."""

    try:
        return await redis_store.check_rate_limit(user_id, action, limit, window_ms)
    except Exception:
        # Never let a limiter hiccup take down gameplay - fail open.
        return True


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


@router.websocket("/ws/bingo/{room_id}")
async def bingo_ws(websocket: WebSocket, room_id: str, token: str | None = None):
    if not token:
        await websocket.close(code=4401)
        return

    user = await asyncio.to_thread(_authenticate, token)

    if user is None:
        await websocket.close(code=4401)
        return

    room = await redis_store.get_room(room_id)

    if room is None:
        await websocket.close(code=4404)
        return

    user_id = str(user.id)
    display_name = _display_name(user)

    await websocket.accept()
    conn_token = await manager.connect(room_id, user_id, display_name, websocket)

    try:
        # Always pull the live Postgres balance (not a possibly-stale ORM attr
        # from the closed auth session) so each user's lobby wallet is theirs.
        balance = await asyncio.to_thread(wallet.get_balance, user_id)
        await service.join_room(room_id, user_id, display_name, balance)
        # Make sure the lobby/game lifecycle loop is running for this room.
        game_loop.ensure_game_loop(room_id)
        room = await service.load_room_for_client(room_id)
        if room is not None:
            await manager.send_personal(room_id, user_id, service.room_state_message(room, user_id))
    except BingoError as exc:
        await manager.send_personal(room_id, user_id, {"type": "error", "message": str(exc)})

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=RECEIVE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # No traffic (not even a ping) - treat as a dead connection.
                break

            manager.touch(room_id, user_id)
            await _dispatch(room_id, user_id, raw)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("bingo websocket error for room %s user %s", room_id, user_id)
    finally:
        # Only mark the player disconnected if *this* socket was the live one.
        # A socket that was already replaced by a newer connection (same user
        # reopening the app) must not flip the still-connected player to
        # disconnected - doing so used to drop the room's connected count to 0
        # and freeze/reset the shared lobby countdown.
        removed_current = await manager.disconnect(room_id, user_id, conn_token)

        if removed_current:
            try:
                await service.leave_room(room_id, user_id)
            except BingoError:
                pass


async def _dispatch(room_id: str, user_id: str, raw: str) -> None:
    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        await manager.send_personal(room_id, user_id, {"type": "error", "message": "Invalid message"})
        return

    if not isinstance(message, dict):
        await manager.send_personal(room_id, user_id, {"type": "error", "message": "Invalid message"})
        return

    message_type = message.get("type")

    try:
        if message_type == "join":
            # Refresh from the authoritative DB balance so the wallet shown on
            # (re)join / manual refresh reflects deposits & prior stakes/wins.
            balance = await asyncio.to_thread(wallet.get_balance, user_id)
            room = await service.sync_player_balance(room_id, user_id, balance)
            if room is not None:
                game_loop.ensure_game_loop(room_id)
                await manager.send_personal(room_id, user_id, service.room_state_message(room, user_id))

        elif message_type == "select_board":
            board_id = _parse_board_id(message.get("board_id"))

            if not await _allow(user_id, "board", settings.BINGO_RATE_SELECT_MAX, settings.BINGO_RATE_SELECT_WINDOW_MS):
                await manager.send_personal(room_id, user_id, {
                    "type": "error",
                    "message": "Too many board taps - slow down a bit",
                })
                return

            await service.select_board(room_id, user_id, board_id)

        elif message_type == "deselect_board":
            board_id = _parse_board_id(message.get("board_id"))

            if not await _allow(user_id, "board", settings.BINGO_RATE_SELECT_MAX, settings.BINGO_RATE_SELECT_WINDOW_MS):
                await manager.send_personal(room_id, user_id, {
                    "type": "error",
                    "message": "Too many board taps - slow down a bit",
                })
                return

            await service.deselect_board(room_id, user_id, board_id)

        elif message_type == "deselect_all":
            if not await _allow(user_id, "board", settings.BINGO_RATE_SELECT_MAX, settings.BINGO_RATE_SELECT_WINDOW_MS):
                await manager.send_personal(room_id, user_id, {
                    "type": "error",
                    "message": "Too many board taps - slow down a bit",
                })
                return

            await service.deselect_all(room_id, user_id)

        elif message_type == "claim_bingo":
            card_id = message.get("card_id")

            if not isinstance(card_id, str):
                raise BingoError("Invalid claim payload")

            if not await _allow(user_id, "claim", settings.BINGO_RATE_CLAIM_MAX, settings.BINGO_RATE_CLAIM_WINDOW_MS):
                return

            valid, _pattern, _room = await service.claim_bingo(room_id, user_id, card_id)

            # On a valid claim the room moves to "finished"; the lifecycle
            # loop handles the winner splash and reset to lobby, so the loop
            # is intentionally left running here.
            if not valid:
                await manager.send_personal(room_id, user_id, {
                    "type": "bingo_result",
                    "valid": False,
                    "card_id": card_id,
                    "reason": "No winning pattern yet",
                })

        elif message_type == "ping":
            await manager.send_personal(room_id, user_id, {"type": "pong"})

        else:
            await manager.send_personal(room_id, user_id, {
                "type": "error",
                "message": f"Unknown message type: {message_type}",
            })

    except BingoError as exc:
        await manager.send_personal(room_id, user_id, {"type": "error", "message": str(exc)})
        # Re-push personalized lobby state so optimistic client board picks snap
        # back when a claim was rejected (taken / at-max / not in lobby).
        if message_type in {"select_board", "deselect_board", "deselect_all"}:
            room = await service.load_room_for_client(room_id)
            if room is not None:
                await manager.send_personal(
                    room_id,
                    user_id,
                    service.room_state_message(room, user_id),
                )
