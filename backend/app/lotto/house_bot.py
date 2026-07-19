"""Lotto house bot — gradual number autofill for open stake rooms.

Mirrors Bingo's Bright Bot pattern: same durable ``is_bot`` user, Redis-backed
enable + min/max reserve range, leader-safe tick lock, organic claim schedule,
and release under real-player pressure.

Real-player threshold
---------------------
``real_holders`` = distinct **non-bot** users holding ≥1 number in the open
round. When ``real_holders >= LOTTO_BOT_REAL_PLAYER_THRESHOLD`` (default 15),
the bot stops claiming and gradually releases its numbers (wallet refund via
``LOTTO_BOT_RELEASE``). Release only works while status is ``open``; once
countdown/draw starts the bot stays as a normal participant and can win.

Reserve range
-------------
Each open round plans ``target = randint(reserve_min, reserve_max)`` free
numbers (clamped 1–25, min≤max). Claims spread as 1–2 number bursts across the
claim window. All four stake rooms are managed independently with the same
config.

Multi-worker
------------
Ticks run from the Lotto game-loop leader (or admin disable force). Per-stake
Redis tick locks prevent overlapping mutations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from app.bingo import house_bot as bingo_bot
from app.bingo import redis_store
from app.core.config import settings
from app.lotto import service

logger = logging.getLogger(__name__)

BOT_ENABLED_KEY = "lotto:bot:enabled"
BOT_RESERVE_MIN_KEY = "lotto:bot:reserve_min"
BOT_RESERVE_MAX_KEY = "lotto:bot:reserve_max"
BOT_STATE_KEY = "lotto:bot:{stake}:state"
BOT_TICK_LOCK_KEY = "lotto:bot:{stake}:tick"
BOT_STATE_TTL_SECONDS = 24 * 60 * 60
BOT_TICK_LOCK_TTL_MS = 2500

RESERVE_MIN_BOUND = 1
RESERVE_MAX_BOUND = 25

_RELEASE_TICK_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def clamp_reserve(value: int) -> int:
    return max(RESERVE_MIN_BOUND, min(RESERVE_MAX_BOUND, int(value)))


def normalize_reserve_range(lo: int, hi: int) -> tuple[int, int]:
    a = clamp_reserve(lo)
    b = clamp_reserve(hi)
    if a > b:
        a, b = b, a
    return a, b


def default_reserve_range() -> tuple[int, int]:
    return normalize_reserve_range(
        settings.LOTTO_BOT_RESERVE_MIN,
        settings.LOTTO_BOT_RESERVE_MAX,
    )


def _parse_enabled_flag(raw: str | bytes | None) -> bool | None:
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    normalized = text.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _stake_key(stake: Decimal | str | float | int) -> str:
    return str(Decimal(str(stake)).quantize(service.MONEY))


async def get_bot_enabled() -> tuple[bool, Literal["redis", "env"]]:
    redis = redis_store.get_redis()
    raw = await redis.get(BOT_ENABLED_KEY)
    parsed = _parse_enabled_flag(raw)
    if parsed is None:
        return bool(settings.LOTTO_BOT_ENABLED), "env"
    return parsed, "redis"


async def set_bot_enabled(enabled: bool) -> None:
    redis = redis_store.get_redis()
    await redis.set(BOT_ENABLED_KEY, "1" if enabled else "0")


async def get_bot_reserve_range() -> tuple[int, int, Literal["redis", "default"]]:
    redis = redis_store.get_redis()
    raw_min = await redis.get(BOT_RESERVE_MIN_KEY)
    raw_max = await redis.get(BOT_RESERVE_MAX_KEY)
    if raw_min is not None and raw_max is not None:
        try:
            text_min = raw_min.decode() if isinstance(raw_min, (bytes, bytearray)) else str(raw_min)
            text_max = raw_max.decode() if isinstance(raw_max, (bytes, bytearray)) else str(raw_max)
            return (*normalize_reserve_range(int(text_min.strip()), int(text_max.strip())), "redis")
        except (TypeError, ValueError):
            pass
    if raw_min is not None or raw_max is not None:
        try:
            default_lo, default_hi = default_reserve_range()
            lo = (
                clamp_reserve(int(
                    (raw_min.decode() if isinstance(raw_min, (bytes, bytearray)) else str(raw_min)).strip()
                ))
                if raw_min is not None
                else default_lo
            )
            hi = (
                clamp_reserve(int(
                    (raw_max.decode() if isinstance(raw_max, (bytes, bytearray)) else str(raw_max)).strip()
                ))
                if raw_max is not None
                else default_hi
            )
            return (*normalize_reserve_range(lo, hi), "redis")
        except (TypeError, ValueError):
            pass
    lo, hi = default_reserve_range()
    return lo, hi, "default"


async def set_bot_reserve_range(reserve_min: int, reserve_max: int) -> tuple[int, int]:
    lo, hi = normalize_reserve_range(reserve_min, reserve_max)
    redis = redis_store.get_redis()
    await redis.set(BOT_RESERVE_MIN_KEY, str(lo))
    await redis.set(BOT_RESERVE_MAX_KEY, str(hi))
    return lo, hi


@dataclass
class BotIntent:
    round_key: str
    target: int
    schedule: list[list[float | int]] = field(default_factory=list)
    phase: str = "claiming"
    seed: int = 0

    def to_json(self) -> str:
        return json.dumps({
            "round_key": self.round_key,
            "target": self.target,
            "schedule": self.schedule,
            "phase": self.phase,
            "seed": self.seed,
        })

    @classmethod
    def from_json(cls, raw: str) -> "BotIntent":
        data = json.loads(raw)
        return cls(
            round_key=str(data["round_key"]),
            target=int(data["target"]),
            schedule=[list(item) for item in data.get("schedule", [])],
            phase=str(data.get("phase", "claiming")),
            seed=int(data.get("seed", 0)),
        )


async def load_intent(stake_key: str) -> BotIntent | None:
    redis = redis_store.get_redis()
    raw = await redis.get(BOT_STATE_KEY.format(stake=stake_key))
    if not raw:
        return None
    try:
        text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        return BotIntent.from_json(text)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


async def save_intent(stake_key: str, intent: BotIntent) -> None:
    redis = redis_store.get_redis()
    await redis.set(
        BOT_STATE_KEY.format(stake=stake_key),
        intent.to_json(),
        ex=BOT_STATE_TTL_SECONDS,
    )


async def clear_intent(stake_key: str) -> None:
    redis = redis_store.get_redis()
    await redis.delete(BOT_STATE_KEY.format(stake=stake_key))


async def _acquire_tick_lock(stake_key: str, token: str) -> bool:
    redis = redis_store.get_redis()
    return bool(
        await redis.set(
            BOT_TICK_LOCK_KEY.format(stake=stake_key),
            token,
            nx=True,
            px=BOT_TICK_LOCK_TTL_MS,
        )
    )


async def _release_tick_lock(stake_key: str, token: str) -> None:
    redis = redis_store.get_redis()
    await redis.eval(
        _RELEASE_TICK_LOCK_SCRIPT,
        1,
        BOT_TICK_LOCK_KEY.format(stake=stake_key),
        token,
    )


def build_claim_schedule(
    started_at: float,
    target: int,
    *,
    window_start: float,
    window_end: float,
    rng: random.Random,
) -> list[tuple[float, int]]:
    """Spread ``target`` claims as 1–2 number bursts inside the claim window."""

    if target <= 0:
        return []

    start = started_at + window_start
    end = started_at + max(window_start, window_end)
    if end <= start:
        end = start + 0.5

    remaining = target
    bursts: list[int] = []
    while remaining > 0:
        n = min(remaining, rng.randint(1, 2))
        bursts.append(n)
        remaining -= n

    span = end - start
    n_bursts = len(bursts)
    schedule: list[tuple[float, int]] = []
    for i, count in enumerate(bursts):
        base = start + span * ((i + 0.5) / n_bursts)
        jitter = (span / n_bursts) * 0.35 * (rng.random() - 0.5)
        at = max(start, min(end, base + jitter))
        schedule.append((at, count))

    schedule.sort(key=lambda item: item[0])
    return schedule


def _pick_target(
    free_count: int,
    reserve_min: int,
    reserve_max: int,
    rng: random.Random,
) -> int:
    lo, hi = normalize_reserve_range(reserve_min, reserve_max)
    if free_count <= 0:
        return 0
    # Leave headroom so reals can always find numbers.
    usable = max(0, free_count - 2)
    if usable <= 0:
        return 0
    hi = min(hi, usable)
    lo = min(lo, hi)
    if hi <= 0:
        return 0
    return rng.randint(lo, hi)


def _round_stats(db, round_, bot_user_id: UUID) -> tuple[list[int], list[int], int]:
    """Return (free numbers, bot held numbers, distinct real holders)."""
    from app.models.lotto_game import LottoReservation

    held_rows = (
        db.query(LottoReservation)
        .filter(LottoReservation.round_id == round_.id)
        .all()
    )
    occupied = {row.number: row.user_id for row in held_rows}
    free = [n for n in range(1, service.CAPACITY + 1) if n not in occupied]
    bot_held = sorted(n for n, uid in occupied.items() if uid == bot_user_id)
    real_holders = len({uid for uid in occupied.values() if uid != bot_user_id})
    return free, bot_held, real_holders


def _claim_numbers_sync(
    *,
    stake: Decimal,
    bot_user_id: str,
    numbers: list[int],
) -> dict | None:
    from app.bingo import wallet
    from app.db.database import SessionLocal

    if not numbers:
        return None
    db = SessionLocal()
    try:
        wallet.ensure_bot_balance(bot_user_id)
        result = service.reserve(
            db,
            user_id=UUID(bot_user_id),
            raw_stake=stake,
            raw_numbers=numbers,
            request_id=uuid4(),
        )
        return result.get("round")
    except service.LottoError as exc:
        logger.debug("Lotto bot claim skipped: %s", exc)
        return None
    finally:
        db.close()


def _release_numbers_sync(
    *,
    round_id: UUID,
    bot_user_id: str,
    numbers: list[int] | None,
) -> dict | None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        result = service.release_bot_numbers(
            db,
            round_id=round_id,
            bot_user_id=UUID(bot_user_id),
            numbers=numbers,
        )
        return result.get("round")
    except service.LottoError as exc:
        logger.debug("Lotto bot release skipped: %s", exc)
        return None
    finally:
        db.close()


def _inspect_open_round(stake: Decimal, bot_user_id: str) -> dict | None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        round_ = service.current_round(db, stake)
        if round_.status != "open":
            return {
                "status": round_.status,
                "round_id": str(round_.id),
                "open": False,
            }
        free, bot_held, real_holders = _round_stats(db, round_, UUID(bot_user_id))
        return {
            "status": round_.status,
            "round_id": str(round_.id),
            "round_uuid": round_.id,
            "open": True,
            "free": free,
            "bot_held": bot_held,
            "real_holders": real_holders,
            "occupied": service.CAPACITY - len(free),
        }
    finally:
        db.close()


async def _start_round_plan(
    stake_key: str,
    round_id: str,
    free_count: int,
    reserve_min: int,
    reserve_max: int,
    now: float,
) -> BotIntent:
    seed = int(now * 1000) ^ (hash(round_id) & 0xFFFF)
    rng = random.Random(seed)
    target = _pick_target(free_count, reserve_min, reserve_max, rng)
    schedule = build_claim_schedule(
        now,
        target,
        window_start=settings.LOTTO_BOT_CLAIM_WINDOW_START_SEC,
        window_end=settings.LOTTO_BOT_CLAIM_WINDOW_END_SEC,
        rng=rng,
    )
    intent = BotIntent(
        round_key=round_id,
        target=target,
        schedule=[[at, count] for at, count in schedule],
        phase="claiming" if target > 0 else "idle",
        seed=seed,
    )
    await save_intent(stake_key, intent)
    return intent


async def tick_stake(
    stake: Decimal,
    *,
    now: float | None = None,
    force: bool = False,
) -> dict | None:
    """Advance bot claim/release for one stake room. Returns room snapshot if changed."""

    enabled, _source = await get_bot_enabled()
    if not enabled and not force:
        # Still drain when admin just disabled (force=True from update).
        pass

    stake_key = _stake_key(stake)
    token = f"{time.time_ns()}"
    if not await _acquire_tick_lock(stake_key, token):
        return None

    try:
        bot_user_id = await bingo_bot.ensure_bot_user_async()
        clock = time.time() if now is None else now
        info = await asyncio.to_thread(_inspect_open_round, stake, bot_user_id)

        if info is None or not info.get("open"):
            await clear_intent(stake_key)
            return None

        reserve_min, reserve_max, _ = await get_bot_reserve_range()
        free: list[int] = list(info["free"])
        bot_held: list[int] = list(info["bot_held"])
        real_holders = int(info["real_holders"])
        round_id = str(info["round_id"])
        round_uuid: UUID = info["round_uuid"]
        threshold = settings.LOTTO_BOT_REAL_PLAYER_THRESHOLD

        if not enabled:
            await clear_intent(stake_key)
            if bot_held:
                return await asyncio.to_thread(
                    _release_numbers_sync,
                    round_id=round_uuid,
                    bot_user_id=bot_user_id,
                    numbers=None,
                )
            return None

        if real_holders >= threshold:
            intent = await load_intent(stake_key)
            if intent:
                intent.phase = "releasing"
                intent.schedule = []
                await save_intent(stake_key, intent)
            if not bot_held:
                return None
            rng = random.Random(int(clock * 10) ^ (hash(stake_key) & 0xFFFF))
            take = min(len(bot_held), rng.randint(1, 3))
            rng.shuffle(bot_held)
            return await asyncio.to_thread(
                _release_numbers_sync,
                round_id=round_uuid,
                bot_user_id=bot_user_id,
                numbers=bot_held[:take],
            )

        intent = await load_intent(stake_key)
        if intent is None or intent.round_key != round_id:
            intent = await _start_round_plan(
                stake_key,
                round_id,
                len(free),
                reserve_min,
                reserve_max,
                clock,
            )

        # Tight capacity: hold.
        if len(free) < 3 and real_holders >= max(3, threshold // 5):
            intent.phase = "holding"
            intent.schedule = []
            await save_intent(stake_key, intent)
            return None

        if intent.phase not in {"claiming", "holding"} or not intent.schedule:
            return None

        due: list[tuple[float, int]] = []
        remaining: list[list[float | int]] = []
        for at, count in intent.schedule:
            if float(at) <= clock:
                due.append((float(at), int(count)))
            else:
                remaining.append([at, count])

        if not due:
            return None

        need = max(0, intent.target - len(bot_held))
        if need <= 0:
            intent.schedule = []
            intent.phase = "holding"
            await save_intent(stake_key, intent)
            return None

        rng = random.Random(intent.seed ^ int(clock))
        pool = list(free)
        rng.shuffle(pool)
        to_claim: list[int] = []
        for _at, burst in due:
            if len(to_claim) >= need:
                break
            take = min(burst, need - len(to_claim), len(pool))
            while take > 0 and pool:
                num = pool.pop()
                if num not in to_claim:
                    to_claim.append(num)
                    take -= 1
                else:
                    take -= 1  # already counted; skip duplicate

        intent.schedule = remaining
        if not intent.schedule:
            intent.phase = "holding"
        await save_intent(stake_key, intent)

        if not to_claim:
            return None

        await bingo_bot.ensure_bot_funds(bot_user_id)
        return await asyncio.to_thread(
            _claim_numbers_sync,
            stake=stake,
            bot_user_id=bot_user_id,
            numbers=to_claim,
        )
    finally:
        await _release_tick_lock(stake_key, token)


async def tick_all(*, now: float | None = None, force: bool = False) -> list[dict]:
    """Tick every stake room. Returns changed room snapshots for broadcast."""

    changed: list[dict] = []
    for stake in service.STAKES:
        try:
            room = await tick_stake(stake, now=now, force=force)
            if room is not None:
                changed.append(room)
        except Exception:
            logger.exception("Lotto bot tick failed for stake=%s", stake)
    return changed


async def bot_status() -> dict:
    """Admin status payload across all stake rooms."""

    enabled, source = await get_bot_enabled()
    reserve_min, reserve_max, reserve_source = await get_bot_reserve_range()
    numbers_held = 0
    rooms: list[dict] = []
    bot_user_id = bingo_bot.cached_bot_user_id()
    if bot_user_id:
        try:
            for stake in service.STAKES:
                info = await asyncio.to_thread(_inspect_open_round, stake, bot_user_id)
                if info and info.get("open"):
                    held = len(info.get("bot_held") or [])
                    numbers_held += held
                    rooms.append({
                        "stake": _stake_key(stake),
                        "round_id": info.get("round_id"),
                        "numbers_held": held,
                        "real_holders": info.get("real_holders", 0),
                        "occupied": info.get("occupied", 0),
                    })
        except Exception:
            rooms = []

    if enabled:
        status = "active"
    elif numbers_held > 0:
        status = "draining"
    else:
        status = "inactive"

    return {
        "enabled": enabled,
        "source": source,
        "reserve_min": reserve_min,
        "reserve_max": reserve_max,
        "reserve_source": reserve_source,
        "allowed_min": RESERVE_MIN_BOUND,
        "allowed_max": RESERVE_MAX_BOUND,
        "numbers_held": numbers_held,
        "real_player_threshold": settings.LOTTO_BOT_REAL_PLAYER_THRESHOLD,
        "status": status,
        "rooms": rooms,
    }
