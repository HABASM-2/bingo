"""Global Aviator round loop — one shared game for all players.

A Redis leader lock ensures only one backend process advances the round.
Followers stay in a continuous retry loop so leadership can fail over when
the previous owner dies or releases the lock.
"""

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
FOLLOWER_POLL_SECONDS = 1.0

_RENEW_LEADER_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""

_RELEASE_LEADER_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

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
    result = await redis.eval(
        _RENEW_LEADER_SCRIPT, 1, LEADER_KEY, _leader_id, LEADER_TTL_MS
    )
    return bool(result)


async def _release_leader() -> None:
    from app.bingo.redis_store import get_redis

    redis = get_redis()
    await redis.eval(_RELEASE_LEADER_SCRIPT, 1, LEADER_KEY, _leader_id)


async def _run_as_leader() -> None:
    logger.info("aviator loop started (leader)")
    while True:
        if not await _renew_leader():
            logger.info("aviator loop lost leadership")
            return

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


async def _run_loop() -> None:
    """Acquire leadership with continuous failover; never exit on contention."""
    try:
        while True:
            if not await _try_acquire_leader():
                await asyncio.sleep(FOLLOWER_POLL_SECONDS)
                continue

            try:
                await _run_as_leader()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("aviator loop error")
            finally:
                await _release_leader()

            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        logger.info("aviator loop cancelled")
        await _release_leader()
        raise


def _betting_left(rnd: store.LiveRound) -> float:
    if rnd.betting_ends_at is None:
        return 0.0
    return max(0.0, rnd.betting_ends_at - time.time())


def ensure_game_loop() -> None:
    global _loop_task
    if _loop_task is not None and not _loop_task.done():
        return
    _loop_task = asyncio.create_task(_run_loop(), name="aviator-game-loop")


async def stop_game_loop() -> None:
    global _loop_task
    if _loop_task is not None and not _loop_task.done():
        _loop_task.cancel()
        try:
            await _loop_task
        except asyncio.CancelledError:
            pass
    _loop_task = None
