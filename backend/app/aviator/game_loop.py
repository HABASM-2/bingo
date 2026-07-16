"""Global Aviator round loop — one shared game for all players."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.aviator import store
from app.aviator.crash import START_MULT, generate_crash_point
from app.aviator import service

logger = logging.getLogger(__name__)

BETTING_SECONDS = 5.0
# Keep the crash result readable before opening the single 5-second countdown.
CRASHED_SECONDS = 2.0
TICK_INTERVAL = 0.12
LEADER_KEY = "aviator:round:leader"
LEADER_TTL_MS = 8000

_loop_task: asyncio.Task | None = None
_leader_id = uuid.uuid4().hex


async def _try_acquire_leader() -> bool:
    from app.bingo.redis_store import get_redis

    redis = get_redis()
    ok = await redis.set(LEADER_KEY, _leader_id, nx=True, px=LEADER_TTL_MS)
    return bool(ok)


async def _renew_leader() -> bool:
    from app.bingo.redis_store import get_redis

    redis = get_redis()
    val = await redis.get(LEADER_KEY)
    if val != _leader_id:
        return False
    await redis.pexpire(LEADER_KEY, LEADER_TTL_MS)
    return True


async def _run_loop() -> None:
    if not await _try_acquire_leader():
        logger.info("aviator loop: another instance is leader")
        return

    logger.info("aviator loop started")
    try:
        while True:
            if not await _renew_leader():
                break

            rnd = await store.create_round(BETTING_SECONDS)
            await service.broadcast_phase(rnd)

            # Betting window
            while _betting_left(rnd) > 0:
                if not await _renew_leader():
                    return
                await asyncio.sleep(0.25)
                rnd = await store.get_current_round()
                if rnd is None:
                    break

            rnd = await store.get_current_round()
            if rnd is None:
                continue

            crash = generate_crash_point()
            rnd.phase = "flying"
            rnd.crash_multiplier = crash
            rnd.flying_started_at = time.time()
            store.recalc_totals(rnd)
            await store.save_round(rnd)
            await service.broadcast_phase(rnd, START_MULT)

            # Flying until crash
            while True:
                if not await _renew_leader():
                    return
                rnd = await store.get_current_round()
                if rnd is None or rnd.phase != "flying":
                    break
                mult = service.current_multiplier(rnd)
                await service.broadcast_tick(rnd)
                if mult >= crash:
                    break
                await asyncio.sleep(TICK_INTERVAL)

            rnd = await store.get_current_round()
            if rnd is None:
                continue

            if rnd.phase == "flying":
                rnd.phase = "crashed"
                await store.save_round(rnd)
                await service.settle_round(rnd)
                await service.broadcast_phase(rnd, crash)

            await asyncio.sleep(CRASHED_SECONDS)
    except asyncio.CancelledError:
        logger.info("aviator loop cancelled")
        raise
    except Exception:
        logger.exception("aviator loop error")
    finally:
        from app.bingo.redis_store import get_redis

        redis = get_redis()
        val = await redis.get(LEADER_KEY)
        if val == _leader_id:
            await redis.delete(LEADER_KEY)


def _betting_left(rnd: store.LiveRound) -> float:
    if rnd.betting_ends_at is None:
        return 0.0
    return max(0.0, rnd.betting_ends_at - time.time())


def ensure_game_loop() -> None:
    global _loop_task
    if _loop_task is not None and not _loop_task.done():
        return
    _loop_task = asyncio.create_task(_run_loop())


async def stop_game_loop() -> None:
    global _loop_task
    if _loop_task is not None and not _loop_task.done():
        _loop_task.cancel()
        try:
            await _loop_task
        except asyncio.CancelledError:
            pass
    _loop_task = None
