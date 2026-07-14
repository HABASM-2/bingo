"""High-level Bingo game actions.

This is the single place that mutates room state, so both the WebSocket
dispatcher (``app.bingo.ws``) and the room lifecycle loop
(``app.bingo.game_loop``) go through the same code path and can never
disagree about the rules. Every mutation acquires ``redis_store.room_lock``
and broadcasts the resulting change via the connection manager (which fans
out through Redis Pub/Sub to every backend instance).

The Ethiopian lobby model: players pick up to ``max_boards`` cartela ids
(1..``BINGO_BOARD_POOL_MAX``) during a shared 40s countdown. When the
countdown expires the round starts, each selected board is charged
``board_price`` ETB, deterministic cartelas are generated, and the ball
draw begins. The winner takes the whole derash (prize pool); after a short
winner splash the room resets to a fresh lobby.
"""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from decimal import ROUND_DOWN, Decimal

from app.bingo import cards as cards_module
from app.bingo import redis_store, wallet
from app.bingo.manager import ORIGIN_FIELD, manager
from app.bingo.patterns import DEFAULT_PATTERNS, Pattern
from app.bingo.redis_store import CardState, PlayerState, RoomState, get_room, room_lock, save_room
from app.bingo.validator import find_winning_pattern
from app.core.config import settings


class BingoError(Exception):
    """Raised for expected, user-facing failures (bad selection, ...)."""


# The whole app runs one continuously-cycling public lobby (lobby -> game ->
# winner -> lobby). Everyone shares this single fixed room id so that two
# players who open the Mini App independently always join the *same* room and
# see each other's countdown, board locks, balls and winners.
DEFAULT_ROOM_ID = "default"
DEFAULT_ROOM_NAME = "Ethiopian Bingo"


async def get_or_create_default_room() -> RoomState:
    """Atomically fetch (or create on first use) the shared public lobby."""

    return await redis_store.get_or_create_room(
        DEFAULT_ROOM_ID,
        DEFAULT_ROOM_NAME,
        settings.BINGO_DEFAULT_ENTRY_FEE,
    )


_GAME_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"


def _new_game_id() -> str:
    body = "".join(secrets.choice(_GAME_ID_ALPHABET) for _ in range(6))

    return f"MB{body}"


def _seconds_left(room: RoomState) -> int:
    if room.status != "lobby" or room.lobby_ends_at is None:
        return 0

    return max(0, math.ceil(room.lobby_ends_at - time.time()))


def _card_out(card: CardState) -> dict:
    return {
        "card_id": card.card_id,
        "numbers": card.numbers,
        "marks": card.marks,
    }


def _player_out(player: PlayerState) -> dict:
    return {
        "user_id": player.user_id,
        "display_name": player.display_name,
        "cards_count": player.cards_count,
        "connected": player.connected,
        "is_host": player.is_host,
    }


def room_summary(room: RoomState) -> dict:
    return {
        "room_id": room.room_id,
        "name": room.name,
        "status": room.status,
        "player_count": room.connected_player_count(),
        "max_cards_per_player": room.max_cards_per_player,
        "entry_fee": room.entry_fee,
        "drawn_count": len(room.drawn),
        "current_ball": room.current_ball,
    }


def _hydrate_lobby_selections(room: RoomState, board_map: dict[int, str]) -> None:
    """Rebuild ``room.selections`` (and each player's ``cards_count``) from the
    authoritative Redis boards hash. Selections are no longer persisted in the
    room JSON during the lobby - the hash is the source of truth - so any
    snapshot destined for a client must be hydrated first."""

    selections: dict[str, list[int]] = {}

    for board_id, uid in board_map.items():
        selections.setdefault(uid, []).append(board_id)

    for boards in selections.values():
        boards.sort()

    room.selections = selections

    for uid, player in room.players.items():
        player.cards_count = len(selections.get(uid, []))


async def load_room_for_client(room_id: str) -> RoomState | None:
    """Load a room and, while it's in the lobby, hydrate live board
    selections from the reservation hash so the snapshot is accurate."""

    room = await get_room(room_id)

    if room is None:
        return None

    if room.status == "lobby":
        board_map = await redis_store.get_board_map(room_id)
        _hydrate_lobby_selections(room, board_map)

    return room


async def sync_player_balance(
    room_id: str,
    user_id: str,
    balance: str,
) -> RoomState | None:
    """Re-lock a player's displayed wallet onto the authoritative Postgres
    balance (used on join/refresh so deposits made outside the game, or a
    stale cached value, are reflected immediately)."""

    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            return None

        player = room.players.get(user_id)

        if player is not None and player.balance != balance:
            player.balance = balance
            await save_room(room)

    return await load_room_for_client(room_id)


def room_state_message(room: RoomState, user_id: str) -> dict:
    """Personalized room snapshot: the recipient's own boards/cards +
    balance, plus the public roster and round metadata."""

    player = room.players.get(user_id)
    own_cards = [
        _card_out(card)
        for card in room.cards.values()
        if card.user_id == user_id
    ]
    # Stable order matching lobby board numbers so the UI never shuffles.
    own_cards.sort(
        key=lambda c: int(c["card_id"]) if str(c["card_id"]).isdigit() else 0
    )

    # Live lobby economics: while players are still picking, the "derash" (pot)
    # and player count shown must be the *projected* values from the current
    # selections so everyone watches them grow in real time. Once the round
    # starts these are frozen to the amounts actually staked.
    total_selected = room.total_selected_boards()
    selectors = sum(1 for boards in room.selections.values() if boards)
    projected_derash = str(Decimal(room.board_price) * total_selected)

    if room.status == "lobby":
        derash_display = projected_derash
        players_display = selectors
        my_boards = list(room.selections.get(user_id, []))
        taken_boards = room.taken_boards()
    else:
        # During the active / finished round the source of truth is ``cards``,
        # not lobby reservations (the boards hash was cleared at kickoff).
        derash_display = room.derash
        players_display = room.round_players
        my_boards = [
            int(card.card_id)
            for card in room.cards.values()
            if card.user_id == user_id and str(card.card_id).isdigit()
        ]
        my_boards.sort()
        taken_boards = sorted(
            int(card.card_id)
            for card in room.cards.values()
            if str(card.card_id).isdigit()
        )

    message = {
        "type": "room_state",
        "room_id": room.room_id,
        "name": room.name,
        "status": room.status,
        "players": [_player_out(p) for p in room.players.values()],
        "cards": own_cards,
        "drawn": room.drawn,
        "current_ball": room.current_ball,
        "entry_fee": room.entry_fee,
        "player_balance": player.balance if player else "0",
        "max_cards_per_player": room.max_cards_per_player,
        # Ethiopian lobby / round fields
        "board_price": room.board_price,
        "max_boards": room.max_boards,
        "board_pool_max": settings.BINGO_BOARD_POOL_MAX,
        "my_boards": my_boards,
        "taken_boards": taken_boards,
        "seconds_left": _seconds_left(room),
        # Absolute countdown deadline so clients can interpolate locally and
        # never show a frozen number between ticks.
        "lobby_ends_at": room.lobby_ends_at if room.status == "lobby" else None,
        "server_now": time.time(),
        "game_id": room.game_id,
        "derash": derash_display,
        "projected_derash": projected_derash,
        "player_count": room.connected_player_count(),
        "players_in_round": players_display,
        "selected_boards_count": total_selected,
        "call_count": len(room.drawn),
    }

    # Winner metadata is only consumed by the client while the round is in its
    # finished (winner-splash) phase, so we omit it otherwise to keep the
    # hot-path lobby/in-progress snapshots lean.
    if room.status == "finished":
        message.update({
            "winner": room.winner_id,
            "winner_name": room.winner_name,
            "winning_pattern": room.winning_pattern,
            "winning_card_id": room.winning_card_id,
            "winners": room.winners,
            "derash_share": room.derash_share,
        })

    return message


async def _broadcast_player_count(room: RoomState) -> None:
    await manager.broadcast(room.room_id, {
        "type": "player_count",
        "count": room.connected_player_count(),
    })


async def broadcast_room_sync(room_id: str) -> None:
    """Ask every backend instance to push a fresh, personalized
    ``room_state`` to each of its locally-connected sockets in this room."""

    await manager.broadcast(room_id, {"type": "_room_sync"})


async def dispatch_pubsub_event(room_id: str, message: dict) -> None:
    # Messages this instance published already got delivered to its local
    # sockets inline by ``manager.broadcast``; ignore the Redis echo so we
    # don't send them twice. Events originating on *other* instances have a
    # different (or absent) origin and are delivered normally.
    if message.pop(ORIGIN_FIELD, None) == manager.instance_id:
        return

    if message.get("type") == "_room_sync":
        local_user_ids = manager.local_user_ids(room_id)

        if not local_user_ids:
            return

        room = await load_room_for_client(room_id)

        if room is None:
            return

        # Personalize once per local socket, but fan the sends out concurrently
        # so a slow/backpressured client can't stall the rest of the room.
        await asyncio.gather(
            *(
                manager.send_personal(room_id, user_id, room_state_message(room, user_id))
                for user_id in local_user_ids
            ),
            return_exceptions=True,
        )

        return

    await manager.deliver_local(room_id, message)


async def join_room(
    room_id: str,
    user_id: str,
    display_name: str,
    balance: str,
) -> RoomState:
    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            raise BingoError("Room not found")

        player = room.players.get(user_id)

        if player is None:
            player = PlayerState(
                user_id=user_id,
                display_name=display_name,
                balance=balance,
                is_host=len(room.players) == 0,
            )
            room.players[user_id] = player
        else:
            player.connected = True
            player.display_name = display_name
            player.balance = balance

        # Kick off the shared lobby countdown as soon as someone is present.
        # Crucially this only ever *sets* a missing deadline - it is never reset
        # when a second (or third) player joins mid-countdown, so newcomers slot
        # into the same shared countdown instead of restarting it.
        if room.status == "lobby" and room.lobby_ends_at is None:
            room.lobby_ends_at = time.time() + settings.BINGO_LOBBY_SECONDS

        await save_room(room)

    # Fan out both the lightweight count and a full personalized snapshot so
    # every already-connected client immediately reflects the new player (count,
    # roster) without waiting for the next lobby tick.
    await _broadcast_player_count(room)
    await broadcast_room_sync(room_id)

    return room


async def leave_room(room_id: str, user_id: str) -> RoomState | None:
    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            return None

        player = room.players.get(user_id)

        if player is None:
            return room

        player.connected = False

        await save_room(room)

    await _broadcast_player_count(room)

    return room


# ---------------------------------------------------------------------------
# Board selection (lobby)
# ---------------------------------------------------------------------------

async def select_board(room_id: str, user_id: str, board_id: int) -> None:
    """Claim a cartela for this round. The claim itself is a single atomic
    Redis Lua op (``reserve_board``) so two players can never end up holding
    the same board even under heavy concurrent tapping, and no coarse room
    lock is taken on the hot path."""

    room = await get_room(room_id)

    if room is None:
        raise BingoError("Room not found")

    if room.status != "lobby":
        raise BingoError("Boards can only be picked in the lobby")

    if user_id not in room.players:
        raise BingoError("Join the room first")

    # Affordability gate: balance must cover stake * (current boards + 1).
    # Reject before the Redis claim so an empty wallet can't lock a seat.
    board_map = await redis_store.get_board_map(room_id)
    if board_map.get(board_id) != user_id:
        held = sum(1 for owner in board_map.values() if owner == user_id)
        balance = Decimal(await asyncio.to_thread(wallet.get_balance, user_id))
        price = Decimal(room.board_price)
        needed = price * (held + 1)

        if balance < needed:
            if balance < price:
                raise BingoError(
                    f"Insufficient balance — you need {price} ETB to pick a board"
                )
            affordable = int(balance // price) if price > 0 else 0
            raise BingoError(
                f"Insufficient balance — you can only afford {affordable} board(s)"
            )

    result = await redis_store.reserve_board(
        room_id,
        user_id,
        board_id,
        room.max_boards,
        settings.BINGO_BOARD_POOL_MAX,
    )

    if result == redis_store.ReserveResult.OUT_OF_RANGE:
        raise BingoError("Invalid board number")

    if result == redis_store.ReserveResult.TAKEN:
        raise BingoError("Board already taken")

    if result == redis_store.ReserveResult.AT_MAX:
        raise BingoError(f"Max {room.max_boards} boards per player")

    # result is CLAIMED (1) or ALREADY_MINE (0): both are success. Only bother
    # broadcasting when something actually changed.
    if result == redis_store.ReserveResult.CLAIMED:
        await service_broadcast_lobby(room_id)


async def deselect_board(room_id: str, user_id: str, board_id: int) -> None:
    room = await get_room(room_id)

    if room is None:
        raise BingoError("Room not found")

    if room.status != "lobby":
        raise BingoError("Boards can only be changed in the lobby")

    removed = await redis_store.release_board(room_id, user_id, board_id)

    if removed:
        await service_broadcast_lobby(room_id)


async def deselect_all(room_id: str, user_id: str) -> None:
    room = await get_room(room_id)

    if room is None:
        raise BingoError("Room not found")

    if room.status != "lobby":
        raise BingoError("Boards can only be changed in the lobby")

    removed = await redis_store.release_all_boards(room_id, user_id)

    if removed:
        await service_broadcast_lobby(room_id)


async def service_broadcast_lobby(room_id: str) -> None:
    """Push updated selections/taken boards to everyone in the lobby."""

    await broadcast_room_sync(room_id)


# ---------------------------------------------------------------------------
# Round lifecycle
# ---------------------------------------------------------------------------

async def start_round(room_id: str) -> tuple[RoomState | None, bool]:
    """Countdown reached zero. If any boards are selected, charge stakes,
    build deterministic cartelas, and enter the active game. Returns
    (room, started)."""

    # Snapshot the authoritative board ownership up front (outside the lock -
    # the hash is its own atomic store).
    board_map = await redis_store.get_board_map(room_id)

    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            return None, False

        if room.status != "lobby":
            return room, False

        if not board_map:
            # Nobody's playing - restart the countdown for the next round.
            room.lobby_ends_at = time.time() + settings.BINGO_LOBBY_SECONDS
            await save_room(room)
            return room, False

        # Snapshot who wants to play, their boards, and how much they owe.
        board_price = Decimal(room.board_price)
        plan: dict[str, list[int]] = {}
        for board_id, uid in board_map.items():
            plan.setdefault(uid, []).append(board_id)
        for boards in plan.values():
            boards.sort()
        charges: dict[str, Decimal] = {
            uid: board_price * len(boards) for uid, boards in plan.items()
        }

    game_id = _new_game_id()

    # DB stake deduction happens off the event loop (sync SQLAlchemy).
    paid = await asyncio.to_thread(wallet.charge_stakes, charges, game_id)

    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            return None, False

        if room.status != "lobby":
            return room, False

        room.cards = {}
        total_boards = 0
        unpaid_user_ids: list[str] = []

        for uid, boards in plan.items():
            if uid not in paid or not boards:
                # Unpaid (insufficient balance) - drop from this round.
                room.selections[uid] = []
                player = room.players.get(uid)
                if player is not None:
                    player.cards_count = 0
                unpaid_user_ids.append(uid)
                continue

            room.selections[uid] = boards
            player = room.players.get(uid)
            if player is not None:
                player.balance = paid[uid]
                player.cards_count = len(boards)

            for board_id in boards:
                card = CardState(
                    card_id=str(board_id),
                    user_id=uid,
                    numbers=cards_module.generate_card_for_board(board_id),
                    marks=cards_module.empty_marks(),
                )
                room.cards[card.card_id] = card
                total_boards += 1

        # Boards have been consumed into cartelas (or dropped): the lobby
        # reservation hash is no longer authoritative for this round.
        await redis_store.clear_boards(room_id)

        if total_boards == 0:
            # Everyone failed to pay - back to lobby.
            room.selections = {}
            room.lobby_ends_at = time.time() + settings.BINGO_LOBBY_SECONDS
            await save_room(room)
            return room, False

        room.status = "in_progress"
        room.game_id = game_id
        room.derash = str(board_price * total_boards)
        # "Players" in the active game means total *staked boards*, not unique
        # users: one player holding two cards counts as two.
        room.round_players = total_boards
        # Snapshot the paying roster for the durable history record below.
        record_participants = {
            uid: len(boards)
            for uid, boards in room.selections.items()
            if boards
        }
        record_derash = Decimal(room.derash)
        room.drawn = []
        room.current_ball = None
        room.winner_id = None
        room.winner_name = None
        room.winning_pattern = None
        room.winning_card_id = None
        room.winners = []
        room.derash_share = "0"
        room.prize_awarded = False
        room.lobby_ends_at = None

        await save_room(room)

    # Durably record the round for history/tracking (best-effort, off-loop).
    await asyncio.to_thread(
        wallet.record_round_start,
        game_id,
        room_id,
        board_price,
        record_participants,
        record_derash,
    )

    # Tell unpaid selectors why they are spectators this round (everyone else
    # gets their cartelas via the following room_sync in the game loop).
    for uid in unpaid_user_ids:
        await manager.send_personal(room_id, uid, {
            "type": "toast",
            "message": "Insufficient balance — watching this round. Please wait until it finishes.",
        })

    return room, True


async def reset_to_lobby(room_id: str) -> RoomState | None:
    """Tear down a finished round and open a fresh lobby countdown."""

    await redis_store.clear_boards(room_id)

    abandoned_game_id: str | None = None

    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            return None

        # A round torn down straight from in_progress (all players left) never
        # settled a winner - close out its history record as no-winner.
        if room.status == "in_progress" and room.game_id:
            abandoned_game_id = room.game_id

        room.status = "lobby"
        room.selections = {}
        room.cards = {}
        room.drawn = []
        room.current_ball = None
        room.winner_id = None
        room.winner_name = None
        room.winning_pattern = None
        room.winning_card_id = None
        room.winners = []
        room.derash_share = "0"
        room.game_id = None
        room.derash = "0"
        room.round_players = 0
        room.prize_awarded = False
        room.lobby_ends_at = time.time() + settings.BINGO_LOBBY_SECONDS

        for player in room.players.values():
            player.cards_count = 0

        await save_room(room)

    if abandoned_game_id:
        await asyncio.to_thread(wallet.record_round_abandoned, abandoned_game_id)

    await broadcast_room_sync(room_id)

    return room


def _split_derash(derash: Decimal, parts: int) -> Decimal:
    """Equal share of the derash across ``parts`` winners, floored to whole
    cents. Any rounding remainder is handed to the first winner by the caller
    so the full prize pool is always paid out."""

    if parts <= 0:
        return Decimal("0")

    return (derash / parts).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


async def _settle_winners(
    room_id: str,
    patterns: tuple[Pattern, ...] = DEFAULT_PATTERNS,
) -> tuple[RoomState | None, bool]:
    """Finish the round if any board wins on the numbers drawn so far.

    Every active cartela is checked against ``patterns``. If several boards
    complete on the same drawn ball, every distinct winning *player* shares the
    derash equally (co-winners split 50/50, 1/3 each, ... — not per-board).
    A single ``game_over`` broadcast carries the full winner-board list.
    """

    plan: dict[str, Decimal] = {}
    game_id = ""
    room_snapshot: RoomState | None = None

    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None or room.status != "in_progress":
            return room, False

        drawn_numbers = set(room.drawn)

        winning: list[tuple[CardState, Pattern]] = []
        for card in room.cards.values():
            pattern = find_winning_pattern(card.numbers, drawn_numbers, patterns)
            if pattern is not None:
                winning.append((card, pattern))

        if not winning:
            return room, False

        # Deterministic order (by board id) so the UI / first-winner
        # remainder assignment is stable across instances.
        winning.sort(
            key=lambda cp: int(cp[0].card_id) if cp[0].card_id.isdigit() else 0
        )

        # Equal split among unique winning players (not per board).
        winner_user_ids: list[str] = []
        for card, _pattern in winning:
            if card.user_id not in winner_user_ids:
                winner_user_ids.append(card.user_id)

        num_winners = len(winner_user_ids)
        derash = Decimal(room.derash)
        share = _split_derash(derash, num_winners)
        remainder = derash - share * num_winners

        for idx, uid in enumerate(winner_user_ids):
            amount = share + (remainder if idx == 0 else Decimal("0"))
            plan[uid] = amount

        winners_meta: list[dict] = []
        for card, pattern in winning:
            player = room.players.get(card.user_id)
            winners_meta.append({
                "user_id": card.user_id,
                "name": player.display_name if player else "Winner",
                "card_id": card.card_id,
                "pattern": pattern.name,
            })

        first_card, first_pattern = winning[0]

        room.status = "finished"
        room.winners = winners_meta
        room.winner_id = first_card.user_id
        room.winner_name = winners_meta[0]["name"]
        room.winning_pattern = first_pattern.name
        room.winning_card_id = first_card.card_id
        room.derash_share = str(share)
        game_id = room.game_id or ""

        await save_room(room)
        room_snapshot = room

    if plan:
        new_balances = await asyncio.to_thread(wallet.award_prizes, plan, game_id)

        if new_balances:
            async with room_lock(room_id):
                room2 = await get_room(room_id)
                if room2 is not None:
                    for uid, balance in new_balances.items():
                        player = room2.players.get(uid)
                        if player is not None:
                            player.balance = balance
                    room2.prize_awarded = True
                    await save_room(room2)
                    room_snapshot = room2

    # Stamp the finished round + winner amounts onto the history record.
    if game_id:
        await asyncio.to_thread(
            wallet.record_round_finish,
            game_id,
            plan,
            room_snapshot.winning_pattern if room_snapshot else None,
            len(room_snapshot.winners) if room_snapshot else len(plan),
        )

    if room_snapshot is None:
        return None, False

    await manager.broadcast(room_id, {
        "type": "game_over",
        "winner": room_snapshot.winner_id,
        "winner_name": room_snapshot.winner_name,
        "pattern": room_snapshot.winning_pattern,
        "winning_card_id": room_snapshot.winning_card_id,
        "derash": room_snapshot.derash,
        "derash_share": room_snapshot.derash_share,
        "winners": room_snapshot.winners,
        "winner_count": len(room_snapshot.winners),
    })

    await broadcast_room_sync(room_id)

    return room_snapshot, True


async def auto_detect_winners(
    room_id: str,
    patterns: tuple[Pattern, ...] = DEFAULT_PATTERNS,
) -> tuple[RoomState | None, bool]:
    """Server-side auto-claim: called after every ball so a completed card
    ends the game immediately, without waiting for a manual BINGO click."""

    return await _settle_winners(room_id, patterns)


async def claim_bingo(
    room_id: str,
    user_id: str,
    card_id: str,
    patterns: tuple[Pattern, ...] = DEFAULT_PATTERNS,
) -> tuple[bool, Pattern | None, RoomState]:
    """Manual BINGO claim. Validates the claimed card, then settles *all*
    winning boards on the current drawn ball so co-winners split the derash."""

    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            raise BingoError("Room not found")

        if room.status != "in_progress":
            return False, None, room

        card = room.cards.get(card_id)

        if card is None or card.user_id != user_id:
            raise BingoError("Invalid card")

        drawn_numbers = set(room.drawn)
        pattern = find_winning_pattern(card.numbers, drawn_numbers, patterns)

        if pattern is None:
            return False, None, room

    settled_room, _ = await _settle_winners(room_id, patterns)

    return True, pattern, settled_room or room


async def finish_without_winner(room_id: str) -> RoomState | None:
    async with room_lock(room_id):
        room = await get_room(room_id)

        if room is None:
            return None

        room.status = "finished"
        game_id = room.game_id

        await save_room(room)

    if game_id:
        await asyncio.to_thread(wallet.record_round_abandoned, game_id)

    await manager.broadcast(room_id, {
        "type": "game_over",
        "winner": None,
        "winner_name": None,
        "pattern": None,
        "winning_card_id": None,
        "derash": room.derash,
    })

    return room
