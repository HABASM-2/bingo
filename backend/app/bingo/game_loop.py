"""Per-room lifecycle worker.

One asyncio task runs per active room and drives the whole cycle:

    lobby (shared 40s countdown)
      -> in_progress (draw a ball every few seconds, auto-dab client-side)
      -> finished (winner splash)
      -> lobby (fresh countdown)  ...

A Redis-backed leader lock (renewed each iteration) makes sure that if this
app is ever scaled to multiple instances, only one of them advances a given
room's state / draws balls - every instance still receives the resulting
broadcasts via Pub/Sub, so the loop's owner is invisible to clients.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
import uuid

from app.bingo import redis_store, service
from app.bingo import house_bot
from app.bingo.manager import manager
from app.bingo.redis_store import room_lock
from app.core.config import settings

logger = logging.getLogger(__name__)

ALL_NUMBERS = tuple(range(1, 76))

LEADER_KEY = "bingo:room:{room_id}:draw_leader"
LEADER_TTL_MS = 8000
LEADER_RENEW_INTERVAL_SECONDS = 3.0
IDLE_POLL_SECONDS = 1.0
ABANDON_SECONDS = 20.0
# Short grace before an *empty* lobby's countdown is paused, so a player
# reconnecting (new tab / dropped socket) within a moment doesn't reset the
# shared countdown out from under everyone else.
LOBBY_EMPTY_GRACE_SECONDS = 5.0

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

_room_tasks: dict[str, asyncio.Task] = {}


def ensure_game_loop(room_id: str) -> None:
    """Idempotent: safe to call whenever a room might need a running loop
    (on join, after a manual start, ...)."""

    existing = _room_tasks.get(room_id)

    if existing is not None and not existing.done():
        return

    task = asyncio.create_task(_run_room_loop(room_id))
    _room_tasks[room_id] = task


async def stop_game_loop(room_id: str) -> None:
    task = _room_tasks.pop(room_id, None)

    if task is not None and not task.done():
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


async def stop_all() -> None:
    for room_id in list(_room_tasks.keys()):
        await stop_game_loop(room_id)


async def _try_acquire_leader(room_id: str, token: str) -> bool:
    redis = redis_store.get_redis()
    key = LEADER_KEY.format(room_id=room_id)

    return bool(await redis.set(key, token, nx=True, px=LEADER_TTL_MS))


async def _renew_leader(room_id: str, token: str) -> bool:
    redis = redis_store.get_redis()
    key = LEADER_KEY.format(room_id=room_id)

    result = await redis.eval(_RENEW_LEADER_SCRIPT, 1, key, token, LEADER_TTL_MS)

    return bool(result)


async def _release_leader(room_id: str, token: str) -> None:
    redis = redis_store.get_redis()
    key = LEADER_KEY.format(room_id=room_id)

    await redis.eval(_RELEASE_LEADER_SCRIPT, 1, key, token)


async def _clear_lobby_timer(room_id: str) -> None:
    async with room_lock(room_id):
        room = await redis_store.get_room(room_id)

        if room is not None and room.status == "lobby":
            room.lobby_ends_at = None
            await redis_store.save_room(room)


async def _real_connected_count(room: redis_store.RoomState) -> int:
    """Connected humans only — house bot must not keep an empty lobby alive."""

    bot_id = house_bot.cached_bot_user_id()
    return house_bot.count_real_connected(room, bot_id)


async def _run_room_loop(room_id: str) -> None:
    token = uuid.uuid4().hex
    last_renew = 0.0
    is_leader = False
    empty_since: float | None = None
    lobby_empty_since: float | None = None

    try:
        while True:
            # Every iteration is individually protected: a transient Redis
            # hiccup or a single failed broadcast must never kill the loop
            # (that used to silently stop lobby ticks -> frozen countdown for
            # everyone until the next join happened to restart it).
            try:
                room = await redis_store.get_room(room_id)

                if room is None:
                    return

                real_connected = await _real_connected_count(room)

                if real_connected == 0:
                    # Let the bot release/leave before we treat the lobby as empty.
                    # Always tick so a Redis-disabled bot can still drain boards.
                    if room.status == "lobby":
                        try:
                            await house_bot.tick_room(room_id)
                        except Exception:
                            logger.exception(
                                "bingo house bot tick failed (empty) room=%s", room_id
                            )
                        room = await redis_store.get_room(room_id)
                        if room is None:
                            return
                        real_connected = await _real_connected_count(room)

                if real_connected == 0:
                    if room.status == "lobby":
                        now = time.monotonic()
                        lobby_empty_since = lobby_empty_since or now

                        # Only pause the countdown once the lobby has stayed
                        # empty past the grace window - a quick reconnect keeps
                        # the shared countdown running untouched.
                        if now - lobby_empty_since > LOBBY_EMPTY_GRACE_SECONDS:
                            await _clear_lobby_timer(room_id)
                            return

                        await asyncio.sleep(IDLE_POLL_SECONDS)
                        continue

                    # Give disconnected players a grace window to reconnect
                    # before abandoning an in-progress / finished round.
                    now = time.monotonic()
                    empty_since = empty_since or now

                    if now - empty_since > ABANDON_SECONDS:
                        await service.reset_to_lobby(room_id)
                        return

                    await asyncio.sleep(IDLE_POLL_SECONDS)
                    continue

                empty_since = None
                lobby_empty_since = None

                now = time.monotonic()

                if now - last_renew > LEADER_RENEW_INTERVAL_SECONDS:
                    is_leader = await _renew_leader(room_id, token) or await _try_acquire_leader(room_id, token)
                    last_renew = now

                if not is_leader:
                    await asyncio.sleep(IDLE_POLL_SECONDS)
                    continue

                if room.status == "lobby":
                    await _tick_lobby(room_id, room)
                    await asyncio.sleep(IDLE_POLL_SECONDS)

                elif room.status == "in_progress":
                    delay = random.uniform(
                        settings.BINGO_DRAW_INTERVAL_MIN,
                        settings.BINGO_DRAW_INTERVAL_MAX,
                    )
                    await asyncio.sleep(delay)

                    outcome = await _draw_number(room_id)

                    if outcome == "drawn":
                        # Auto-claim: end the round the instant any board
                        # completes so the winner dialog shows immediately.
                        await service.auto_detect_winners(room_id)
                    elif outcome == "exhausted":
                        await service.finish_without_winner(room_id)

                elif room.status == "finished":
                    await asyncio.sleep(settings.BINGO_WINNER_OVERLAY_SECONDS)
                    await service.reset_to_lobby(room_id)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("bingo room loop iteration error for room %s", room_id)
                await asyncio.sleep(IDLE_POLL_SECONDS)

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("bingo room loop crashed for room %s", room_id)
    finally:
        if is_leader:
            await _release_leader(room_id, token)


async def _tick_lobby(room_id: str, room: redis_store.RoomState) -> None:
    if room.lobby_ends_at is None:
        async with room_lock(room_id):
            fresh = await redis_store.get_room(room_id)
            if fresh is not None and fresh.status == "lobby" and fresh.lobby_ends_at is None:
                fresh.lobby_ends_at = time.time() + settings.BINGO_LOBBY_SECONDS
                await redis_store.save_room(fresh)
                room = fresh

    ends_at = room.lobby_ends_at

    if ends_at is None:
        return

    seconds_left = max(0, math.ceil(ends_at - time.time()))

    # ``lobby_ends_at`` (absolute epoch seconds) lets every client run a smooth
    # local countdown that self-heals: even if a tick is briefly missed the UI
    # keeps ticking down instead of freezing, and re-locks onto the server value
    # on the next tick. ``seconds_left`` stays for older clients.
    await manager.broadcast(room_id, {
        "type": "lobby_tick",
        "seconds_left": seconds_left,
        "lobby_ends_at": ends_at,
        "server_now": time.time(),
    })

    if seconds_left <= 0:
        room_after, started = await service.start_round(room_id)

        if started:
            await service.broadcast_room_sync(room_id)
        else:
            # No paid boards - countdown was reset; nudge clients + tell any
            # would-be players to pick a board.
            if room_after is not None and room_after.total_selected_boards() == 0:
                await manager.broadcast(room_id, {
                    "type": "toast",
                    "message": "Please select at least 1 board to play!",
                })

            await service.broadcast_room_sync(room_id)
        return

    # House bot claims/releases during the open countdown (leader-only path).
    # Tick always runs; house_bot re-reads the Redis/env enable flag each cycle.
    try:
        await house_bot.tick_room(room_id)
    except Exception:
        logger.exception("bingo house bot tick failed room=%s", room_id)


async def _draw_number(room_id: str) -> str:
    """Returns 'drawn', 'exhausted', or 'stopped'."""

    async with room_lock(room_id):
        room = await redis_store.get_room(room_id)

        if room is None or room.status != "in_progress":
            return "stopped"

        remaining = [n for n in ALL_NUMBERS if n not in room.drawn]

        if not remaining:
            return "exhausted"

        number = random.choice(remaining)
        room.drawn.append(number)
        room.current_ball = number

        await redis_store.save_room(room)
        drawn_snapshot = list(room.drawn)

    await manager.broadcast(room_id, {
        "type": "ball",
        "number": number,
        "drawn": drawn_snapshot,
    })

    return "drawn"
