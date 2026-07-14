"""Redis-backed room/player/card state.

All Bingo game state lives in Redis (never Postgres) since the rest of the
app's database access is synchronous. Rooms are stored as a single JSON blob
per room - state is tiny (a handful of players, up to
``settings.BINGO_MAX_CARDS`` cards each, 75 numbers) so read-modify-write
under a short-lived distributed lock (``room_lock``) is simple and correct
across multiple backend instances, without needing per-field Redis
operations.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field

from redis.asyncio import Redis

from app.bingo.cards import CardGrid, empty_marks
from app.core.config import settings

ROOM_KEY = "bingo:room:{room_id}"
ROOM_LOCK_KEY = "bingo:room:{room_id}:lock"
ROOMS_INDEX_KEY = "bingo:rooms"
# Authoritative lobby board ownership: Redis hash of board_id -> user_id. This
# is the single source of truth for "who holds cartela N" during the lobby, so
# claims are atomic (a Lua script) instead of funnelling every tap through the
# coarse room lock.
BOARDS_KEY = "bingo:room:{room_id}:boards"
# Fixed-window rate limiter counter per user+action.
RATE_KEY = "bingo:rl:{user_id}:{action}"

ROOM_LOCK_TTL_MS = 4000
ROOM_LOCK_RETRY_DELAY_SECONDS = 0.02
ROOM_LOCK_MAX_WAIT_SECONDS = 3.0

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

# Atomically claim a board only if it is free (or already held by this user)
# and the user is still under their per-round board cap. Returns:
#   1  -> newly claimed
#   0  -> already held by this user (idempotent no-op)
#  -1  -> taken by another player
#  -2  -> board id out of range
#  -3  -> user already at their max board count
_RESERVE_BOARD_SCRIPT = """
local board = ARGV[1]
local uid = ARGV[2]
local maxb = tonumber(ARGV[3])
local pool = tonumber(ARGV[4])
local bnum = tonumber(board)
if bnum == nil or bnum < 1 or bnum > pool then
    return -2
end
local owner = redis.call('hget', KEYS[1], board)
if owner then
    if owner == uid then
        return 0
    end
    return -1
end
local held = 0
local all = redis.call('hvals', KEYS[1])
for i = 1, #all do
    if all[i] == uid then
        held = held + 1
    end
end
if held >= maxb then
    return -3
end
redis.call('hset', KEYS[1], board, uid)
return 1
"""

# Release a single board only if the requesting user actually owns it.
_RELEASE_BOARD_SCRIPT = """
if redis.call('hget', KEYS[1], ARGV[1]) == ARGV[2] then
    return redis.call('hdel', KEYS[1], ARGV[1])
end
return 0
"""

# Drop every board currently held by a user (deselect-all / cleanup).
_RELEASE_ALL_BOARDS_SCRIPT = """
local uid = ARGV[1]
local all = redis.call('hgetall', KEYS[1])
local removed = 0
for i = 1, #all, 2 do
    if all[i + 1] == uid then
        redis.call('hdel', KEYS[1], all[i])
        removed = removed + 1
    end
end
return removed
"""

# Fixed-window token bucket: increment the counter, set its TTL on first hit,
# and report whether the caller is still within the allowance. Returns 1 when
# the action is allowed, 0 when the limit is exceeded for the window.
_RATE_LIMIT_SCRIPT = """
local count = redis.call('incr', KEYS[1])
if count == 1 then
    redis.call('pexpire', KEYS[1], ARGV[1])
end
if count > tonumber(ARGV[2]) then
    return 0
end
return 1
"""

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client

    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )

    return _redis_client


async def close_redis() -> None:
    global _redis_client

    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


@asynccontextmanager
async def room_lock(room_id: str):
    """Short-lived distributed mutex guarding read-modify-write of a room's
    JSON blob, so concurrent joins/draws/claims across instances don't race."""

    redis = get_redis()
    key = ROOM_LOCK_KEY.format(room_id=room_id)
    token = uuid.uuid4().hex

    deadline = time.monotonic() + ROOM_LOCK_MAX_WAIT_SECONDS
    acquired = False

    while time.monotonic() < deadline:
        acquired = bool(
            await redis.set(key, token, nx=True, px=ROOM_LOCK_TTL_MS)
        )

        if acquired:
            break

        await asyncio.sleep(ROOM_LOCK_RETRY_DELAY_SECONDS)

    if not acquired:
        raise TimeoutError(f"Could not acquire lock for bingo room {room_id}")

    try:
        yield
    finally:
        await redis.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)


@dataclass
class PlayerState:
    user_id: str
    display_name: str
    cards_count: int = 0
    balance: str = "0"
    connected: bool = True
    is_host: bool = False
    joined_at: float = field(default_factory=time.time)


@dataclass
class CardState:
    card_id: str
    user_id: str
    numbers: CardGrid
    marks: list[list[bool]] = field(default_factory=empty_marks)


@dataclass
class RoomState:
    room_id: str
    name: str
    status: str = "lobby"  # lobby | in_progress | finished
    entry_fee: str = "0"
    max_cards_per_player: int = 2
    host_id: str | None = None
    players: dict[str, PlayerState] = field(default_factory=dict)
    cards: dict[str, CardState] = field(default_factory=dict)
    drawn: list[int] = field(default_factory=list)
    current_ball: int | None = None
    winner_id: str | None = None
    winner_name: str | None = None
    winning_pattern: str | None = None
    winning_card_id: str | None = None
    created_at: float = field(default_factory=time.time)

    # --- Ethiopian lobby / staking round state ---
    board_price: str = "10"
    max_boards: int = 2
    # user_id -> list of selected board ids (1..400), lobby phase only.
    selections: dict[str, list[int]] = field(default_factory=dict)
    lobby_ends_at: float | None = None
    game_id: str | None = None
    derash: str = "0"
    round_players: int = 0
    prize_awarded: bool = False
    # Co-winners settled on the same drawn ball. Each entry:
    # {"user_id", "name", "card_id", "pattern"}. The single winner_* fields
    # above mirror the first entry for backwards compatibility.
    winners: list[dict] = field(default_factory=list)
    # Per-board share of the derash when the prize is split across boards.
    derash_share: str = "0"

    def connected_player_count(self) -> int:
        return sum(1 for p in self.players.values() if p.connected)

    def taken_boards(self) -> list[int]:
        taken: list[int] = []

        for boards in self.selections.values():
            taken.extend(boards)

        return taken

    def total_selected_boards(self) -> int:
        return sum(len(boards) for boards in self.selections.values())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "RoomState":
        data = json.loads(raw)

        players = {
            user_id: PlayerState(**player)
            for user_id, player in data.get("players", {}).items()
        }

        cards = {
            card_id: CardState(**card)
            for card_id, card in data.get("cards", {}).items()
        }

        data["players"] = players
        data["cards"] = cards

        return cls(**data)


def _room_key(room_id: str) -> str:
    return ROOM_KEY.format(room_id=room_id)


async def get_room(room_id: str) -> RoomState | None:
    redis = get_redis()
    raw = await redis.get(_room_key(room_id))

    if raw is None:
        return None

    return RoomState.from_json(raw)


async def save_room(room: RoomState) -> None:
    redis = get_redis()
    await redis.set(_room_key(room.room_id), room.to_json())


async def create_room(
    name: str,
    entry_fee: str = "0",
    max_cards_per_player: int | None = None,
) -> RoomState:
    max_boards = max_cards_per_player or settings.BINGO_MAX_BOARDS

    room = RoomState(
        room_id=uuid.uuid4().hex[:10],
        name=name,
        entry_fee=entry_fee,
        max_cards_per_player=max_boards,
        board_price=settings.BINGO_BOARD_PRICE,
        max_boards=max_boards,
    )

    redis = get_redis()

    await redis.set(_room_key(room.room_id), room.to_json())
    await redis.sadd(ROOMS_INDEX_KEY, room.room_id)

    return room


async def get_or_create_room(
    room_id: str,
    name: str,
    entry_fee: str = "0",
    max_cards_per_player: int | None = None,
) -> RoomState:
    """Return the room with ``room_id``, creating it atomically if missing.

    This is the join path for the shared public lobby: every player must land
    in the *same* room. A plain "list rooms, else create" from the client
    races (two clients that both find no room each create their own and end up
    in separate rooms that never sync), so creation is funnelled through the
    per-room distributed lock with a double-check inside the critical section.
    """

    room = await get_room(room_id)

    if room is not None:
        return room

    max_boards = max_cards_per_player or settings.BINGO_MAX_BOARDS

    async with room_lock(room_id):
        # Re-check inside the lock: another instance/request may have created
        # the room while we were waiting to acquire it.
        room = await get_room(room_id)

        if room is not None:
            return room

        room = RoomState(
            room_id=room_id,
            name=name,
            entry_fee=entry_fee,
            max_cards_per_player=max_boards,
            board_price=settings.BINGO_BOARD_PRICE,
            max_boards=max_boards,
        )

        redis = get_redis()

        await redis.set(_room_key(room.room_id), room.to_json())
        await redis.sadd(ROOMS_INDEX_KEY, room.room_id)

        return room


async def list_rooms() -> list[RoomState]:
    redis = get_redis()
    room_ids = await redis.smembers(ROOMS_INDEX_KEY)

    if not room_ids:
        return []

    keys = [_room_key(room_id) for room_id in room_ids]
    raw_rooms = await redis.mget(keys)

    rooms: list[RoomState] = []
    missing_ids: list[str] = []

    for room_id, raw in zip(room_ids, raw_rooms):
        if raw is None:
            missing_ids.append(room_id)
            continue

        rooms.append(RoomState.from_json(raw))

    if missing_ids:
        await redis.srem(ROOMS_INDEX_KEY, *missing_ids)

    rooms.sort(key=lambda r: r.created_at)

    return rooms


async def delete_room(room_id: str) -> None:
    redis = get_redis()

    await redis.delete(_room_key(room_id))
    await redis.srem(ROOMS_INDEX_KEY, room_id)
    await redis.delete(_boards_key(room_id))


# ---------------------------------------------------------------------------
# Atomic lobby board reservation (no room lock -> high concurrency)
# ---------------------------------------------------------------------------

def _boards_key(room_id: str) -> str:
    return BOARDS_KEY.format(room_id=room_id)


class ReserveResult:
    CLAIMED = 1
    ALREADY_MINE = 0
    TAKEN = -1
    OUT_OF_RANGE = -2
    AT_MAX = -3


async def reserve_board(
    room_id: str,
    user_id: str,
    board_id: int,
    max_boards: int,
    pool_max: int,
) -> int:
    """Atomically claim ``board_id`` for ``user_id`` iff it is free and the
    user is under ``max_boards``. See ``ReserveResult`` for return codes."""

    redis = get_redis()
    result = await redis.eval(
        _RESERVE_BOARD_SCRIPT,
        1,
        _boards_key(room_id),
        str(board_id),
        user_id,
        str(max_boards),
        str(pool_max),
    )

    return int(result)


async def release_board(room_id: str, user_id: str, board_id: int) -> bool:
    redis = get_redis()
    removed = await redis.eval(
        _RELEASE_BOARD_SCRIPT,
        1,
        _boards_key(room_id),
        str(board_id),
        user_id,
    )

    return bool(removed)


async def release_all_boards(room_id: str, user_id: str) -> int:
    redis = get_redis()
    removed = await redis.eval(
        _RELEASE_ALL_BOARDS_SCRIPT,
        1,
        _boards_key(room_id),
        user_id,
    )

    return int(removed)


async def get_board_map(room_id: str) -> dict[int, str]:
    """Current lobby ownership: board_id -> user_id."""

    redis = get_redis()
    raw = await redis.hgetall(_boards_key(room_id))

    return {int(board_id): user_id for board_id, user_id in raw.items()}


async def clear_boards(room_id: str) -> None:
    redis = get_redis()
    await redis.delete(_boards_key(room_id))


async def check_rate_limit(
    user_id: str,
    action: str,
    limit: int,
    window_ms: int,
) -> bool:
    """Fixed-window limiter. Returns True while the user is within their
    allowance for ``action``, False once they've exceeded it this window."""

    redis = get_redis()
    key = RATE_KEY.format(user_id=user_id, action=action)
    allowed = await redis.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        str(window_ms),
        str(limit),
    )

    return bool(allowed)
