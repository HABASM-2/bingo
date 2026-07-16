"""AI mid-game session blobs in Redis (resume after leaving Dama tab)."""

from __future__ import annotations

import json
import time
from typing import Any

from app.bingo.redis_store import get_redis
from app.dama.engine import create_initial_board

AI_SESSION_KEY = "dama:ai_session:{user_id}"
AI_SESSION_TTL_SECONDS = 20 * 60
TURN_TIMEOUT_SECONDS = 120


async def save_ai_session(user_id: str, payload: dict[str, Any]) -> None:
    redis = get_redis()
    payload = {**payload, "updated_at": time.time()}
    await redis.set(
        AI_SESSION_KEY.format(user_id=user_id),
        json.dumps(payload),
        ex=AI_SESSION_TTL_SECONDS,
    )


async def get_ai_session(user_id: str) -> dict[str, Any] | None:
    redis = get_redis()
    raw = await redis.get(AI_SESSION_KEY.format(user_id=user_id))
    if not raw:
        return None
    return json.loads(raw)


async def clear_ai_session(user_id: str) -> None:
    redis = get_redis()
    await redis.delete(AI_SESSION_KEY.format(user_id=user_id))


def new_ai_session(
    *,
    game_code: str,
    stake: str,
    pot: str,
    system_fee: str,
    prize_pool: str,
) -> dict[str, Any]:
    now = time.time()
    return {
        "game_code": game_code,
        "stake": stake,
        "pot": pot,
        "system_fee": system_fee,
        "prize_pool": prize_pool,
        "board": create_initial_board(),
        "turn": "red",
        "ply_count": 0,
        "quiet_plies": 0,
        "status": "playing",
        "winner": None,
        "turn_deadline": now + TURN_TIMEOUT_SECONDS,
        "created_at": now,
        "updated_at": now,
    }
