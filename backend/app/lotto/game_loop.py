"""Recovery-safe Lotto countdown, draw, reveal, and rollover loop.

Only one backend process runs the poller (Redis leader lock). Followers idle
and retry so leadership can fail over. Snapshots are computed on a deadline
schedule rather than a blind full DB rebuild every 250ms when nothing is due.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import timedelta

from app.db.database import SessionLocal
from app.lotto import service
from app.lotto.manager import hub
from app.models.lotto_game import LottoWinner
from app.models.user import User

logger = logging.getLogger(__name__)

LEADER_KEY = "lotto:loop:leader"
LEADER_TTL_MS = 8000
FOLLOWER_POLL_SECONDS = 1.0
ACTIVE_POLL_SECONDS = 0.25
IDLE_POLL_SECONDS = 1.0
FINGERPRINT_MAX = 64

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

_task: asyncio.Task | None = None
_leader_id = uuid.uuid4().hex
_last_fingerprint: dict[str, tuple[str, int, int]] = {}


def _prune_fingerprints(active_ids: set[str]) -> None:
    stale = [rid for rid in _last_fingerprint if rid not in active_ids]
    for rid in stale:
        _last_fingerprint.pop(rid, None)
    if len(_last_fingerprint) > FINGERPRINT_MAX:
        # Drop oldest arbitrary extras if somehow still oversized.
        overflow = len(_last_fingerprint) - FINGERPRINT_MAX
        for rid in list(_last_fingerprint.keys())[:overflow]:
            _last_fingerprint.pop(rid, None)


def _next_deadline_seconds(db) -> float | None:
    """Soonest countdown/draw deadline across recoverable rounds, if any."""
    now = service.utcnow()
    soonest: float | None = None
    for round_ in service.recoverable_rounds(db):
        deadline = None
        if round_.status == "countdown" and round_.draw_scheduled_at:
            deadline = round_.draw_scheduled_at
        elif round_.status == "drawing" and round_.drawing_started_at:
            deadline = round_.drawing_started_at + timedelta(
                seconds=service.DRAW_COMPLETE_SECONDS
            )
        if deadline is None:
            continue
        delta = (deadline - now).total_seconds()
        if soonest is None or delta < soonest:
            soonest = delta
    return soonest


def _process() -> tuple[list[dict], dict[str, str], float, list[str], list[str]]:
    db = SessionLocal()
    try:
        service.ensure_rooms(db)
        changed: list[dict] = []
        wallet_updates: dict[str, str] = {}
        pre_draw_ids: list[str] = []
        winner_ids: list[str] = []
        for round_ in service.recoverable_rounds(db):
            if round_.status == "countdown":
                if service.settle_due_round(db, round_.id):
                    winner_ids.append(str(round_.id))
                    paid_users = (
                        db.query(User)
                        .join(LottoWinner, LottoWinner.user_id == User.id)
                        .filter(LottoWinner.round_id == round_.id)
                        .distinct()
                        .all()
                    )
                    wallet_updates.update(
                        {str(user.id): str(user.balance) for user in paid_users}
                    )
            elif round_.status == "drawing":
                if service.complete_due_round(db, round_.id):
                    completed = (
                        db.query(type(round_)).filter(type(round_).id == round_.id).one()
                    )
                    changed.append(service.serialize_round(db, completed))

        snap = service.snapshot(db)
        active_ids: set[str] = set()
        for room in snap["rooms"]:
            active_ids.add(room["id"])
            fingerprint = (room["status"], len(room["winners"]), int(room.get("occupied") or 0))
            previous = _last_fingerprint.get(room["id"])
            if fingerprint != previous:
                _last_fingerprint[room["id"]] = fingerprint
                changed.append(room)
                # Entering countdown (room just filled) → pre-draw notices.
                if room["status"] == "countdown" and (
                    previous is None or previous[0] != "countdown"
                ):
                    pre_draw_ids.append(room["id"])
        _prune_fingerprints(active_ids)

        deadline = _next_deadline_seconds(db)
        if deadline is None:
            sleep_for = IDLE_POLL_SECONDS
        else:
            # Poll tightly near deadlines; ease off when the next event is far.
            sleep_for = ACTIVE_POLL_SECONDS if deadline <= 2.0 else min(
                IDLE_POLL_SECONDS, max(ACTIVE_POLL_SECONDS, deadline / 2)
            )
        return changed, wallet_updates, sleep_for, pre_draw_ids, winner_ids
    finally:
        db.close()


async def _try_acquire_leader() -> bool:
    from app.bingo.redis_store import get_redis

    redis = get_redis()
    return bool(await redis.set(LEADER_KEY, _leader_id, nx=True, px=LEADER_TTL_MS))


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
    logger.info("lotto loop started (leader)")
    last_renew = 0.0
    while True:
        now = time.monotonic()
        if now - last_renew > 3.0:
            if not await _renew_leader():
                logger.info("lotto loop lost leadership")
                return
            last_renew = now

        try:
            changed, wallet_updates, sleep_for, pre_draw_ids, winner_ids = (
                await asyncio.to_thread(_process)
            )
            try:
                from app.lotto import house_bot as lotto_house_bot

                bot_rooms = await lotto_house_bot.tick_all()
                if bot_rooms:
                    # Merge bot-driven room updates into the broadcast set.
                    by_id = {room["id"]: room for room in changed}
                    for room in bot_rooms:
                        by_id[room["id"]] = room
                        # Bot may be the reservation that fills the room.
                        if room.get("status") == "countdown":
                            pre_draw_ids.append(room["id"])
                    changed = list(by_id.values())
            except Exception:
                logger.exception("Lotto house bot tick failed")
            if changed:
                await hub.broadcast(
                    {
                        "type": "rooms_updated",
                        "server_time": service.utcnow().isoformat(),
                        "rooms": changed,
                    }
                )
            for user_id, balance in wallet_updates.items():
                await hub.send_user(
                    user_id, {"type": "wallet", "balance": balance}
                )
            if pre_draw_ids or winner_ids:
                from app.lotto import notifications as lotto_notify

                for round_id in dict.fromkeys(pre_draw_ids):
                    lotto_notify.schedule_pre_draw(round_id)
                for round_id in dict.fromkeys(winner_ids):
                    lotto_notify.schedule_winners(round_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Lotto recovery/draw loop failed")
            sleep_for = ACTIVE_POLL_SECONDS

        await asyncio.sleep(sleep_for)


async def _run() -> None:
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
                logger.exception("Lotto leader loop crashed")
            finally:
                await _release_leader()
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        logger.info("lotto loop cancelled")
        await _release_leader()
        raise


def ensure_game_loop() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run(), name="lotto-game-loop")


async def stop_game_loop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
