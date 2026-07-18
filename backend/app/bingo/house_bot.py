"""Bingo house bot — backend-driven lobby autofill.

Smart scenario for a fledgling public lobby
-------------------------------------------
The bot is a durable DB user (``is_bot=True``) that joins the configured
public room and gradually reserves cartelas so early players see an occupied
board grid. It is **not** a Telegram client; all actions are server-driven.

Real-player threshold semantics
-------------------------------
``real_selectors`` = distinct **non-bot** user ids that currently hold ≥1 board
in the lobby reservation hash (``bingo:room:{id}:boards``).

* If ``real_selectors <= BINGO_BOT_REAL_PLAYER_THRESHOLD`` (default 20):
  the bot may hold a target of ``randint(min, max)`` boards (15–30) and plays
  as a normal participant when the round locks.
* If ``real_selectors > threshold`` (i.e. ≥21 when threshold=20): the bot
  **starts releasing** its reservations so it is not counted among the busy
  lobby's seated players. New claims are forbidden under pressure.

Connected lobby presence (no boards yet) still wakes the bot so it can start
claiming, but the release rule keys off **board holders**, matching “users
joining with boards / seated for the round.”

Claim timeline
--------------
After each lobby countdown opens (``lobby_ends_at`` set), the bot picks a
target and spreads claims as bursts of 1–3 boards across
``[CLAIM_WINDOW_START_SEC, CLAIM_WINDOW_END_SEC]`` seconds into the window
(default ~1s–35s of the 40s lobby). Intent is Redis-backed so multi-worker
restarts mid-countdown resume the same schedule.

Wallet
------
Stakes debit at round start via the normal ``BINGO_STAKE`` path. When the bot
wallet falls below ``BINGO_BOT_MIN_BALANCE``, house funds are credited with
``BINGO_BOT_TOPUP`` ledger rows (auditable).

Runtime enable flag
-------------------
Admins can toggle reserving at runtime via Redis key ``bingo:bot:enabled``
(``"1"`` / ``"0"``). When the key is missing, ``BINGO_BOT_ENABLED`` is used.
A Redis flush therefore resets to the env default. Each lobby tick re-reads
the flag so toggles apply without a process restart.
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

from app.bingo import redis_store, service, wallet
from app.bingo.redis_store import ReserveResult
from app.bingo.service import BingoError, DEFAULT_ROOM_ID
from app.core.config import settings

logger = logging.getLogger(__name__)

BOT_STATE_KEY = "bingo:bot:{room_id}:state"
BOT_STATE_TTL_SECONDS = 24 * 60 * 60
# Soft lock so only one worker mutates bot intent / performs claims per tick.
BOT_TICK_LOCK_KEY = "bingo:bot:{room_id}:tick"
BOT_TICK_LOCK_TTL_MS = 2500
# Admin runtime toggle. Survives restarts until Redis is flushed.
BOT_ENABLED_KEY = "bingo:bot:enabled"

_cached_bot_id: str | None = None


def _parse_enabled_flag(raw: str | bytes | None) -> bool | None:
    """Return True/False for an explicit Redis value, or None if unset/unknown."""

    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    normalized = text.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


async def get_bot_enabled() -> tuple[bool, Literal["redis", "env"]]:
    """Resolve whether board reserving is active.

    Prefers Redis ``bingo:bot:enabled`` when set; otherwise falls back to
    ``settings.BINGO_BOT_ENABLED``.
    """

    redis = redis_store.get_redis()
    raw = await redis.get(BOT_ENABLED_KEY)
    parsed = _parse_enabled_flag(raw)
    if parsed is None:
        return bool(settings.BINGO_BOT_ENABLED), "env"
    return parsed, "redis"


async def set_bot_enabled(enabled: bool) -> None:
    """Persist the admin runtime toggle in Redis (no TTL — survives restarts)."""

    redis = redis_store.get_redis()
    await redis.set(BOT_ENABLED_KEY, "1" if enabled else "0")


async def clear_bot_enabled_override() -> None:
    """Remove the Redis override so the next read uses the env default."""

    redis = redis_store.get_redis()
    await redis.delete(BOT_ENABLED_KEY)


@dataclass
class BotIntent:
    """Persisted per-lobby-window plan (survives process restart)."""

    round_key: str  # str(lobby_ends_at) — identity of this countdown
    target: int
    # Epoch seconds when each burst should fire, paired with board counts.
    schedule: list[list[float | int]] = field(default_factory=list)
    phase: str = "claiming"  # claiming | holding | releasing | idle
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


def cached_bot_user_id() -> str | None:
    return _cached_bot_id


def _room_allowed(room_id: str) -> bool:
    return room_id == (settings.BINGO_BOT_ROOM_ID or DEFAULT_ROOM_ID)


def build_claim_schedule(
    lobby_started_at: float,
    target: int,
    *,
    window_start: float,
    window_end: float,
    rng: random.Random,
) -> list[tuple[float, int]]:
    """Spread ``target`` claims as 1–3 board bursts inside the claim window."""

    if target <= 0:
        return []

    start = lobby_started_at + window_start
    end = lobby_started_at + max(window_start, window_end)
    if end <= start:
        end = start + 0.5

    remaining = target
    bursts: list[int] = []
    while remaining > 0:
        n = min(remaining, rng.randint(1, 3))
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


def count_real_selectors(board_map: dict[int, str], bot_user_id: str | None) -> int:
    """Distinct non-bot users holding ≥1 board (threshold semantics)."""

    owners = {uid for uid in board_map.values() if uid and uid != bot_user_id}
    return len(owners)


def count_real_connected(room: redis_store.RoomState, bot_user_id: str | None) -> int:
    return sum(
        1
        for uid, player in room.players.items()
        if player.connected and uid != bot_user_id
    )


def bot_held_boards(board_map: dict[int, str], bot_user_id: str) -> list[int]:
    return sorted(bid for bid, uid in board_map.items() if uid == bot_user_id)


def free_board_ids(board_map: dict[int, str], pool_max: int) -> list[int]:
    taken = set(board_map.keys())
    return [bid for bid in range(1, pool_max + 1) if bid not in taken]


async def load_intent(room_id: str) -> BotIntent | None:
    redis = redis_store.get_redis()
    raw = await redis.get(BOT_STATE_KEY.format(room_id=room_id))
    if not raw:
        return None
    try:
        return BotIntent.from_json(raw)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


async def save_intent(room_id: str, intent: BotIntent) -> None:
    redis = redis_store.get_redis()
    await redis.set(
        BOT_STATE_KEY.format(room_id=room_id),
        intent.to_json(),
        ex=BOT_STATE_TTL_SECONDS,
    )


async def clear_intent(room_id: str) -> None:
    redis = redis_store.get_redis()
    await redis.delete(BOT_STATE_KEY.format(room_id=room_id))


async def _acquire_tick_lock(room_id: str, token: str) -> bool:
    redis = redis_store.get_redis()
    return bool(
        await redis.set(
            BOT_TICK_LOCK_KEY.format(room_id=room_id),
            token,
            nx=True,
            px=BOT_TICK_LOCK_TTL_MS,
        )
    )


async def _release_tick_lock(room_id: str, token: str) -> None:
    redis = redis_store.get_redis()
    await redis.eval(
        """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """,
        1,
        BOT_TICK_LOCK_KEY.format(room_id=room_id),
        token,
    )


def ensure_bot_user() -> str:
    """Create or return the durable house-bot user id (sync, DB)."""

    global _cached_bot_id

    if _cached_bot_id is not None:
        return _cached_bot_id

    from app.db.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.is_bot.is_(True))
            .order_by(User.created_at.asc())
            .first()
        )
        if user is None:
            user = (
                db.query(User)
                .filter(User.username == settings.BINGO_BOT_USERNAME)
                .first()
            )

        if user is None:
            user = User(
                telegram_id=settings.BINGO_BOT_TELEGRAM_ID,
                username=settings.BINGO_BOT_USERNAME,
                first_name=settings.BINGO_BOT_DISPLAY_NAME,
                referral_code="BINGOBOT",
                is_bot=True,
                balance=Decimal(settings.BINGO_BOT_INITIAL_BALANCE),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("Created Bingo house bot user id=%s", user.id)
        else:
            dirty = False
            if not user.is_bot:
                user.is_bot = True
                dirty = True
            if user.first_name != settings.BINGO_BOT_DISPLAY_NAME:
                user.first_name = settings.BINGO_BOT_DISPLAY_NAME
                dirty = True
            if dirty:
                db.commit()
                db.refresh(user)

        _cached_bot_id = str(user.id)
        return _cached_bot_id
    finally:
        db.close()


async def ensure_bot_user_async() -> str:
    return await asyncio.to_thread(ensure_bot_user)


async def ensure_bot_funds(bot_user_id: str) -> None:
    await asyncio.to_thread(wallet.ensure_bot_balance, bot_user_id)


async def _ensure_bot_in_room(room_id: str, bot_user_id: str) -> None:
    room = await redis_store.get_room(room_id)
    if room is None:
        return

    if bot_user_id in room.players and room.players[bot_user_id].connected:
        return

    balance = await asyncio.to_thread(wallet.get_balance, bot_user_id)
    await service.join_room(
        room_id,
        bot_user_id,
        settings.BINGO_BOT_DISPLAY_NAME,
        balance,
    )


async def _leave_if_present(room_id: str, bot_user_id: str) -> None:
    room = await redis_store.get_room(room_id)
    if room is None or bot_user_id not in room.players:
        return
    await service.leave_room(room_id, bot_user_id)


async def bot_claim_board(room_id: str, bot_user_id: str, board_id: int) -> int:
    """Claim one board for the bot using the bot's higher per-round cap.

    Returns a ``ReserveResult`` code. Idempotent for already-held boards.
    """

    room = await redis_store.get_room(room_id)
    if room is None:
        raise BingoError("Room not found")
    if room.status != "lobby":
        raise BingoError("Boards can only be picked in the lobby")
    if bot_user_id not in room.players:
        raise BingoError("Bot not in room")

    max_boards = max(settings.BINGO_BOT_MAX_BOARDS, room.max_boards)
    board_map = await redis_store.get_board_map(room_id)
    if board_map.get(board_id) != bot_user_id:
        held = sum(1 for owner in board_map.values() if owner == bot_user_id)
        balance = Decimal(await asyncio.to_thread(wallet.get_balance, bot_user_id))
        price = Decimal(room.board_price)
        needed = price * (held + 1)
        if balance < needed:
            await ensure_bot_funds(bot_user_id)
            balance = Decimal(await asyncio.to_thread(wallet.get_balance, bot_user_id))
            if balance < needed:
                raise BingoError("Bot insufficient balance")

    result = await redis_store.reserve_board(
        room_id,
        bot_user_id,
        board_id,
        max_boards,
        settings.BINGO_BOARD_POOL_MAX,
    )

    if result == ReserveResult.CLAIMED:
        await service.broadcast_board_delta(
            room_id,
            action="taken",
            user_id=bot_user_id,
            board_id=board_id,
        )

    return result


async def bot_release_board(room_id: str, bot_user_id: str, board_id: int) -> bool:
    removed = await redis_store.release_board(room_id, bot_user_id, board_id)
    if removed:
        await service.broadcast_board_delta(
            room_id,
            action="released",
            user_id=bot_user_id,
            board_id=board_id,
        )
    return removed


async def bot_release_all(room_id: str, bot_user_id: str) -> list[int]:
    board_map = await redis_store.get_board_map(room_id)
    held = bot_held_boards(board_map, bot_user_id)
    if not held:
        return []
    await redis_store.release_all_boards(room_id, bot_user_id)
    await service.broadcast_board_delta(
        room_id,
        action="released_all",
        user_id=bot_user_id,
        board_ids=held,
    )
    return held


def _pick_target(rng: random.Random, free_count: int) -> int:
    lo = max(0, settings.BINGO_BOT_MIN_BOARDS)
    hi = max(lo, settings.BINGO_BOT_MAX_BOARDS)
    if free_count <= 0:
        return 0
    target = rng.randint(lo, hi)
    return min(target, free_count)


async def _start_round_plan(
    room_id: str,
    lobby_ends_at: float,
    board_map: dict[int, str],
    bot_user_id: str,
) -> BotIntent:
    lobby_started = lobby_ends_at - settings.BINGO_LOBBY_SECONDS
    seed = int(lobby_ends_at * 1000) ^ (hash(room_id) & 0xFFFF)
    rng = random.Random(seed)

    free = free_board_ids(board_map, settings.BINGO_BOARD_POOL_MAX)
    # Leave headroom so real players can still pick when the lobby is warming.
    reserved_headroom = min(30, max(5, len(free) // 10))
    usable = max(0, len(free) - reserved_headroom)
    target = _pick_target(rng, usable)

    schedule = build_claim_schedule(
        lobby_started,
        target,
        window_start=settings.BINGO_BOT_CLAIM_WINDOW_START_SEC,
        window_end=min(
            settings.BINGO_BOT_CLAIM_WINDOW_END_SEC,
            max(1.0, settings.BINGO_LOBBY_SECONDS - 3),
        ),
        rng=rng,
    )

    intent = BotIntent(
        round_key=str(lobby_ends_at),
        target=target,
        schedule=[[at, count] for at, count in schedule],
        phase="claiming" if target > 0 else "idle",
        seed=seed,
    )
    await save_intent(room_id, intent)
    return intent


async def _claim_due_bursts(
    room_id: str,
    bot_user_id: str,
    intent: BotIntent,
    board_map: dict[int, str],
    now: float,
    rng: random.Random,
) -> BotIntent:
    if not intent.schedule:
        intent.phase = "holding"
        await save_intent(room_id, intent)
        return intent

    due: list[tuple[float, int]] = []
    remaining: list[list[float | int]] = []
    for at, count in intent.schedule:
        if float(at) <= now:
            due.append((float(at), int(count)))
        else:
            remaining.append([at, count])

    if not due:
        return intent

    held = bot_held_boards(board_map, bot_user_id)
    need = max(0, intent.target - len(held))
    free = free_board_ids(board_map, settings.BINGO_BOARD_POOL_MAX)
    rng.shuffle(free)

    claimed = 0
    for _at, burst in due:
        if claimed >= need:
            break
        take = min(burst, need - claimed, len(free))
        for _ in range(take):
            if not free:
                break
            board_id = free.pop()
            try:
                code = await bot_claim_board(room_id, bot_user_id, board_id)
            except BingoError:
                continue
            if code in (ReserveResult.CLAIMED, ReserveResult.ALREADY_MINE):
                claimed += 1
                board_map[board_id] = bot_user_id
            elif code == ReserveResult.TAKEN:
                continue
            else:
                break

    intent.schedule = remaining
    if not intent.schedule:
        intent.phase = "holding"
    await save_intent(room_id, intent)
    return intent


async def _release_surplus(
    room_id: str,
    bot_user_id: str,
    board_map: dict[int, str],
    *,
    all_boards: bool,
    seconds_left: float,
    rng: random.Random,
) -> None:
    held = bot_held_boards(board_map, bot_user_id)
    if not held:
        return

    if all_boards or seconds_left <= 5:
        await bot_release_all(room_id, bot_user_id)
        return

    # Gradual release under pressure: 2–4 boards per tick.
    n = min(len(held), rng.randint(2, 4))
    rng.shuffle(held)
    for board_id in held[:n]:
        await bot_release_board(room_id, bot_user_id, board_id)


async def _tick_when_disabled(room_id: str) -> None:
    """Stop new claims; release lobby boards; leave mid-round seats alone."""

    try:
        bot_user_id = await ensure_bot_user_async()
    except Exception:
        # Without a bot identity we cannot drain reservations.
        await clear_intent(room_id)
        return

    room = await redis_store.get_room(room_id)
    if room is None:
        await clear_intent(room_id)
        return

    if room.status != "lobby":
        # Locked into a round: finish as a normal participant, then stay inactive.
        await clear_intent(room_id)
        return

    board_map = await redis_store.get_board_map(room_id)
    held = bot_held_boards(board_map, bot_user_id)
    if held:
        await bot_release_all(room_id, bot_user_id)
    if bot_user_id in room.players:
        await _leave_if_present(room_id, bot_user_id)
    await clear_intent(room_id)


async def tick_room(room_id: str, *, now: float | None = None) -> None:
    """Advance bot claim/release for one lobby tick (leader-safe).

    Re-reads the Redis/env enable flag every call so admin toggles apply on
    the next lobby tick without a restart.
    """

    if not _room_allowed(room_id):
        return

    enabled, _source = await get_bot_enabled()

    token = f"{time.time_ns()}"
    if not await _acquire_tick_lock(room_id, token):
        return

    try:
        if not enabled:
            await _tick_when_disabled(room_id)
            return
        await _tick_room_locked(room_id, now=now)
    finally:
        await _release_tick_lock(room_id, token)


async def _tick_room_locked(room_id: str, *, now: float | None = None) -> None:
    bot_user_id = await ensure_bot_user_async()
    room = await redis_store.get_room(room_id)
    if room is None:
        return

    clock = time.time() if now is None else now
    real_connected = count_real_connected(room, bot_user_id)

    # No real humans: release any boards and leave so the lobby can idle
    # without solo bot rounds burning house stake.
    if real_connected == 0:
        if bot_user_id in room.players:
            await bot_release_all(room_id, bot_user_id)
            await _leave_if_present(room_id, bot_user_id)
        await clear_intent(room_id)
        return

    if room.status != "lobby" or room.lobby_ends_at is None:
        # Mid-call / finished: bot is a normal participant if it held boards
        # at lock; do not claim or release. Clear lobby intent for next cycle.
        if room.status != "lobby":
            await clear_intent(room_id)
        return

    await ensure_bot_funds(bot_user_id)
    await _ensure_bot_in_room(room_id, bot_user_id)

    board_map = await redis_store.get_board_map(room_id)
    real_selectors = count_real_selectors(board_map, bot_user_id)
    threshold = settings.BINGO_BOT_REAL_PLAYER_THRESHOLD
    seconds_left = max(0.0, room.lobby_ends_at - clock)
    rng = random.Random(int(clock * 10) ^ (hash(bot_user_id) & 0xFFFF))

    intent = await load_intent(room_id)
    round_key = str(room.lobby_ends_at)
    if intent is None or intent.round_key != round_key:
        intent = await _start_round_plan(
            room_id, room.lobby_ends_at, board_map, bot_user_id
        )

    # Over threshold: stop claiming and release (gradual, then flush near lock).
    if real_selectors > threshold:
        intent.phase = "releasing"
        intent.schedule = []
        await save_intent(room_id, intent)
        await _release_surplus(
            room_id,
            bot_user_id,
            board_map,
            all_boards=False,
            seconds_left=seconds_left,
            rng=rng,
        )
        return

    # Never take more boards when free capacity is tight relative to demand.
    free = free_board_ids(board_map, settings.BINGO_BOARD_POOL_MAX)
    if len(free) < 10 and real_selectors >= max(5, threshold // 4):
        intent.phase = "holding"
        intent.schedule = []
        await save_intent(room_id, intent)
        return

    if intent.phase in {"claiming", "holding"} and intent.schedule:
        await _claim_due_bursts(
            room_id, bot_user_id, intent, board_map, clock, rng
        )
