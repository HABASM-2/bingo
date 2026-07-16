"""Dama lobby / challenge / match business logic."""

from __future__ import annotations

import asyncio
import time

from app.dama import store
from app.dama import wallet as dama_wallet
from app.dama.ai_session import TURN_TIMEOUT_SECONDS
from app.dama.engine import apply_move, evaluate_outcome, find_legal_move, opposite
from app.dama.manager import hub


class DamaError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _players_payload(players: list[store.OnlinePlayer], viewer_id: str) -> list[dict]:
    return [
        {
            "user_id": p.user_id,
            "display_name": p.display_name,
            "photo_url": p.photo_url,
            "status": p.status,
            "is_self": False,
        }
        for p in players
        if p.user_id != viewer_id
    ]


async def presence_snapshot(viewer_id: str) -> dict:
    players = await store.list_online()
    return {
        "type": "players",
        "players": _players_payload(players, viewer_id),
    }


async def join_lobby(
    user_id: str,
    display_name: str,
    photo_url: str | None,
) -> dict:
    existing = await store.get_online(user_id)
    match_id = existing.match_id if existing and existing.status == "busy" else None
    if not match_id:
        match_id = await store.get_user_match_id(user_id)
        if match_id:
            match = await store.get_match(match_id)
            if match is None or match.status != "playing":
                match_id = None
                await store.clear_user_match(user_id)

    status: store.PresenceStatus = "busy" if match_id else "idle"
    player = store.OnlinePlayer(
        user_id=user_id,
        display_name=display_name,
        photo_url=photo_url,
        status=status,
        match_id=match_id,
    )
    await store.set_online(player)
    await hub.broadcast({"type": "presence", "action": "join", "player": {
        "user_id": player.user_id,
        "display_name": player.display_name,
        "photo_url": player.photo_url,
        "status": player.status,
    }}, exclude=user_id)

    payload: dict = await presence_snapshot(user_id)
    if match_id:
        match = await store.get_match(match_id)
        if match and match.status == "playing":
            payload["resume_match"] = match.public_state(user_id)
    return payload


async def leave_lobby(user_id: str) -> None:
    player = await store.get_online(user_id)
    # Best-effort: if they disconnect while a challenge is pending, free the peer.
    if player and player.status == "challenging":
        # Scan is intentional — challenges are short-TTL and few.
        # Peers get decline via timeout if we miss; presence update still helps.
        player.status = "idle"
        player.match_id = None
        await store.set_online(player)

    # If they leave while a rematch is pending, announce to the partner.
    last_id = await store.get_last_match_id(user_id)
    if last_id:
        match = await store.get_match(last_id)
        if (
            match
            and match.status == "finished"
            and match.rematch_offer_by
            and user_id in (match.red_user_id, match.black_user_id)
        ):
            peer = _peer_id(match, user_id)
            await hub.send(
                peer,
                {
                    "type": "rematch_peer_left",
                    "match_id": match.id,
                    "user_id": user_id,
                    "had_offer": True,
                },
            )
            match.rematch_offer_by = None
            match.rematch_stake = None
            await store.save_match(match)

    await store.remove_online(user_id)
    await hub.broadcast({"type": "presence", "action": "leave", "user_id": user_id})


async def send_challenge(from_user_id: str, to_user_id: str, stake_raw) -> dict:
    if from_user_id == to_user_id:
        raise DamaError("You cannot challenge yourself")

    try:
        stake = dama_wallet.parse_stake(stake_raw)
    except ValueError as exc:
        raise DamaError(str(exc)) from exc

    me = await store.get_online(from_user_id)
    them = await store.get_online(to_user_id)
    if me is None:
        raise DamaError("You are offline")
    if them is None:
        raise DamaError("Player is offline")
    if me.status != "idle":
        raise DamaError("Finish your current game first")
    if them.status != "idle":
        raise DamaError("That player is busy")

    my_bal = await asyncio.to_thread(dama_wallet.get_balance, from_user_id)
    their_bal = await asyncio.to_thread(dama_wallet.get_balance, to_user_id)
    if my_bal is None or float(my_bal) < float(stake):
        raise DamaError("Insufficient balance for this stake")
    if their_bal is None or float(their_bal) < float(stake):
        raise DamaError("Opponent cannot afford this stake")

    challenge = store.Challenge(
        id=store.new_challenge_id(),
        from_user_id=from_user_id,
        from_name=me.display_name,
        to_user_id=to_user_id,
        to_name=them.display_name,
        stake=str(stake),
    )
    await store.save_challenge(challenge)

    me.status = "challenging"
    await store.set_online(me)
    them.status = "challenging"
    await store.set_online(them)

    await hub.send(
        to_user_id,
        {
            "type": "challenge_incoming",
            "challenge": challenge.to_dict(),
        },
    )
    await hub.broadcast(
        {
            "type": "presence",
            "action": "update",
            "player": {
                "user_id": me.user_id,
                "display_name": me.display_name,
                "photo_url": me.photo_url,
                "status": me.status,
            },
        }
    )
    await hub.broadcast(
        {
            "type": "presence",
            "action": "update",
            "player": {
                "user_id": them.user_id,
                "display_name": them.display_name,
                "photo_url": them.photo_url,
                "status": them.status,
            },
        }
    )

    return {
        "type": "challenge_sent",
        "challenge": challenge.to_dict(),
    }


async def _reset_idle(*user_ids: str) -> None:
    for uid in user_ids:
        player = await store.get_online(uid)
        if not player:
            continue
        if player.status == "busy" and player.match_id:
            continue
        player.status = "idle"
        player.match_id = None
        await store.set_online(player)
        await hub.broadcast(
            {
                "type": "presence",
                "action": "update",
                "player": {
                    "user_id": player.user_id,
                    "display_name": player.display_name,
                    "photo_url": player.photo_url,
                    "status": player.status,
                },
            }
        )


async def decline_challenge(user_id: str, challenge_id: str) -> dict:
    challenge = await store.get_challenge(challenge_id)
    if challenge is None:
        raise DamaError("Challenge expired")
    if user_id not in (challenge.from_user_id, challenge.to_user_id):
        raise DamaError("Not your challenge")

    await store.delete_challenge(challenge_id)
    await _reset_idle(challenge.from_user_id, challenge.to_user_id)

    other = (
        challenge.to_user_id
        if user_id == challenge.from_user_id
        else challenge.from_user_id
    )
    await hub.send(
        other,
        {
            "type": "challenge_declined",
            "challenge_id": challenge_id,
            "by_user_id": user_id,
        },
    )
    return {"type": "challenge_declined", "challenge_id": challenge_id}


async def cancel_challenge(user_id: str, challenge_id: str) -> dict:
    return await decline_challenge(user_id, challenge_id)


async def accept_challenge(user_id: str, challenge_id: str) -> dict:
    challenge = await store.get_challenge(challenge_id)
    if challenge is None:
        raise DamaError("Challenge expired")
    if user_id != challenge.to_user_id:
        raise DamaError("Only the challenged player can accept")

    from_p = await store.get_online(challenge.from_user_id)
    to_p = await store.get_online(challenge.to_user_id)
    if from_p is None or to_p is None:
        await store.delete_challenge(challenge_id)
        await _reset_idle(challenge.from_user_id, challenge.to_user_id)
        raise DamaError("A player went offline")

    try:
        stake = dama_wallet.parse_stake(challenge.stake)
    except ValueError as exc:
        await store.delete_challenge(challenge_id)
        await _reset_idle(challenge.from_user_id, challenge.to_user_id)
        raise DamaError(str(exc)) from exc

    await store.delete_challenge(challenge_id)

    # Pre-create match id so the Postgres row can reference it.
    match_id = store.new_match_id()
    try:
        money = await asyncio.to_thread(
            dama_wallet.start_online_game,
            red_user_id=challenge.from_user_id,
            black_user_id=challenge.to_user_id,
            stake=stake,
            match_id=match_id,
        )
    except ValueError as exc:
        await _reset_idle(challenge.from_user_id, challenge.to_user_id)
        raise DamaError(str(exc)) from exc

    match = store.create_match(
        red_user_id=challenge.from_user_id,
        red_name=challenge.from_name,
        black_user_id=challenge.to_user_id,
        black_name=challenge.to_name,
        stake=money["stake"],
        pot=money["pot"],
        system_fee=money["system_fee"],
        prize_pool=money["prize_pool"],
        game_code=money["game_code"],
        match_id=match_id,
    )
    await store.save_match(match)

    for player, side_match_id in (
        (from_p, match.id),
        (to_p, match.id),
    ):
        player.status = "busy"
        player.match_id = side_match_id
        await store.set_online(player)
        await hub.broadcast(
            {
                "type": "presence",
                "action": "update",
                "player": {
                    "user_id": player.user_id,
                    "display_name": player.display_name,
                    "photo_url": player.photo_url,
                    "status": player.status,
                },
            }
        )

    for uid in (match.red_user_id, match.black_user_id):
        payload = match.public_state(uid) | {"type": "match_start"}
        if money.get("balances", {}).get(uid):
            payload["balance"] = money["balances"][uid]
        await hub.send(uid, payload)

    return match.public_state(user_id) | {
        "type": "match_start",
        "balance": money.get("balances", {}).get(user_id),
    }


async def apply_player_move(user_id: str, match_id: str, from_sq: int, to_sq: int) -> dict:
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "playing":
        raise DamaError("Match is over")

    if user_id == match.red_user_id:
        my_side = "red"
    elif user_id == match.black_user_id:
        my_side = "black"
    else:
        raise DamaError("Not your match")

    if match.turn != my_side:
        raise DamaError("Not your turn")

    move = find_legal_move(match.board, my_side, from_sq, to_sq)
    if move is None:
        raise DamaError("Illegal move")

    match.board = apply_move(match.board, move)
    match.last_move = move
    match.turn = opposite(my_side)
    match.ply_count += 1
    if move.get("captures"):
        match.quiet_plies = 0
    else:
        match.quiet_plies += 1
    match.draw_offer_by = None
    match.turn_deadline = time.time() + TURN_TIMEOUT_SECONDS

    outcome = evaluate_outcome(match.board, match.turn)
    if outcome is not None:
        match.status = "finished"
        match.winner = outcome

    await store.save_match(match)

    for uid in (match.red_user_id, match.black_user_id):
        await hub.send(
            uid,
            {
                "type": "move_applied",
                "match_id": match.id,
                "move": move,
                "board": match.board,
                "turn": match.turn,
                "status": match.status,
                "winner": match.winner,
                "stake": match.stake,
                "prize_pool": match.prize_pool,
                "ply_count": match.ply_count,
                "quiet_plies": match.quiet_plies,
                "draw_eligible": match.draw_eligible(),
                "draw_offer_by": match.draw_offer_by,
                "turn_deadline": match.turn_deadline,
            },
        )

    if match.status == "finished":
        await _settle_and_finish(match)

    return {"type": "ok"}


async def claim_timeout(user_id: str, match_id: str) -> dict:
    """Either player may finalize after the side-to-move turn deadline."""
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "playing":
        raise DamaError("Match is over")
    if user_id not in (match.red_user_id, match.black_user_id):
        raise DamaError("Not your match")

    if not match.turn_deadline or time.time() < match.turn_deadline:
        raise DamaError("Turn time remaining")

    winner_side = "black" if match.turn == "red" else "red"

    match.winner = winner_side
    match.status = "finished"
    await store.save_match(match)
    await _settle_and_finish(match, reason="timeout")
    return {"type": "ok", "reason": "timeout"}


async def resign(user_id: str, match_id: str) -> dict:
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "playing":
        raise DamaError("Match is over")

    if user_id == match.red_user_id:
        match.winner = "black"
    elif user_id == match.black_user_id:
        match.winner = "red"
    else:
        raise DamaError("Not your match")

    match.status = "finished"
    await store.save_match(match)
    await _settle_and_finish(match)
    return {"type": "ok"}


def _peer_id(match: store.MatchState, user_id: str) -> str:
    if user_id == match.red_user_id:
        return match.black_user_id
    if user_id == match.black_user_id:
        return match.red_user_id
    raise DamaError("Not your match")


async def offer_draw(user_id: str, match_id: str) -> dict:
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "playing":
        raise DamaError("Match is over")
    if user_id not in (match.red_user_id, match.black_user_id):
        raise DamaError("Not your match")
    if not match.draw_eligible():
        raise DamaError("Draw is only available in long or stuck games")

    peer = _peer_id(match, user_id)

    # If the opponent already offered, accepting is the agreement.
    if match.draw_offer_by and match.draw_offer_by == peer:
        return await accept_draw(user_id, match_id)

    if match.draw_offer_by == user_id:
        return {"type": "draw_offered", "match_id": match.id, "by_user_id": user_id}

    match.draw_offer_by = user_id
    await store.save_match(match)

    await hub.send(
        peer,
        {
            "type": "draw_offered",
            "match_id": match.id,
            "by_user_id": user_id,
            "draw_eligible": True,
        },
    )
    await hub.send(
        user_id,
        {
            "type": "draw_offered",
            "match_id": match.id,
            "by_user_id": user_id,
            "draw_eligible": True,
        },
    )
    return {"type": "draw_offered", "match_id": match.id, "by_user_id": user_id}


async def accept_draw(user_id: str, match_id: str) -> dict:
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "playing":
        raise DamaError("Match is over")
    if user_id not in (match.red_user_id, match.black_user_id):
        raise DamaError("Not your match")
    if not match.draw_offer_by or match.draw_offer_by == user_id:
        raise DamaError("No draw offer to accept")

    match.winner = "draw"
    match.status = "finished"
    match.draw_offer_by = None
    await store.save_match(match)
    await _settle_and_finish(match)
    return {"type": "ok"}


async def decline_draw(user_id: str, match_id: str) -> dict:
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "playing":
        raise DamaError("Match is over")
    if user_id not in (match.red_user_id, match.black_user_id):
        raise DamaError("Not your match")
    if not match.draw_offer_by or match.draw_offer_by == user_id:
        raise DamaError("No draw offer to decline")

    offerer = match.draw_offer_by
    match.draw_offer_by = None
    await store.save_match(match)

    for uid in (match.red_user_id, match.black_user_id):
        await hub.send(
            uid,
            {
                "type": "draw_declined",
                "match_id": match.id,
                "by_user_id": user_id,
                "was_offered_by": offerer,
            },
        )
    return {"type": "draw_declined", "match_id": match.id}


async def offer_rematch(user_id: str, match_id: str, stake_raw=None) -> dict:
    match = await store.get_match(match_id)
    if match is None:
        raise DamaError("Match not found")
    if match.status != "finished":
        raise DamaError("Rematch is available after the game ends")
    if user_id not in (match.red_user_id, match.black_user_id):
        raise DamaError("Not your match")

    try:
        stake = dama_wallet.parse_stake(stake_raw if stake_raw is not None else match.stake)
    except ValueError as exc:
        raise DamaError(str(exc)) from exc

    peer = _peer_id(match, user_id)
    stake_s = str(stake)

    # Peer already offered the same stake → accepting is agreement.
    if (
        match.rematch_offer_by
        and match.rematch_offer_by == peer
        and (match.rematch_stake or match.stake) == stake_s
    ):
        return await accept_rematch(user_id, match_id, stake_s)

    match.rematch_offer_by = user_id
    match.rematch_stake = stake_s
    await store.save_match(match)

    peer_online = hub.is_connected(peer)
    delivered = await hub.send(
        peer,
        {
            "type": "rematch_offered",
            "match_id": match.id,
            "by_user_id": user_id,
            "stake": stake_s,
        },
    )
    # Echo to offerer so their UI updates even if they missed the broadcast path.
    await hub.send(
        user_id,
        {
            "type": "rematch_offered",
            "match_id": match.id,
            "by_user_id": user_id,
            "stake": stake_s,
            "peer_online": peer_online,
            "delivered": delivered,
        },
    )

    if not peer_online or not delivered:
        await hub.send(
            user_id,
            {
                "type": "rematch_peer_left",
                "match_id": match.id,
                "user_id": peer,
                "had_offer": True,
                "reason": "offline",
            },
        )

    return {
        "type": "rematch_offered",
        "match_id": match.id,
        "stake": stake_s,
        "peer_online": peer_online,
        "delivered": delivered,
    }


async def accept_rematch(user_id: str, match_id: str, stake_raw=None) -> dict:
    old = await store.get_match(match_id)
    if old is None:
        raise DamaError("Match not found")
    if old.status != "finished":
        raise DamaError("Rematch is available after the game ends")
    if user_id not in (old.red_user_id, old.black_user_id):
        raise DamaError("Not your match")
    if not old.rematch_offer_by or old.rematch_offer_by == user_id:
        raise DamaError("No rematch offer to accept")

    try:
        stake = dama_wallet.parse_stake(
            stake_raw if stake_raw is not None else (old.rematch_stake or old.stake)
        )
    except ValueError as exc:
        raise DamaError(str(exc)) from exc

    offered = old.rematch_stake or old.stake
    if str(stake) != str(dama_wallet.parse_stake(offered)):
        raise DamaError("Rematch stake does not match the offer — change and propose again")

    new_match_id = store.new_match_id()
    try:
        money = await asyncio.to_thread(
            dama_wallet.start_online_game,
            red_user_id=old.red_user_id,
            black_user_id=old.black_user_id,
            stake=stake,
            match_id=new_match_id,
        )
    except ValueError as exc:
        raise DamaError(str(exc)) from exc

    match = store.create_match(
        red_user_id=old.red_user_id,
        red_name=old.red_name,
        black_user_id=old.black_user_id,
        black_name=old.black_name,
        stake=money["stake"],
        pot=money["pot"],
        system_fee=money["system_fee"],
        prize_pool=money["prize_pool"],
        game_code=money["game_code"],
        match_id=new_match_id,
    )
    await store.save_match(match)

    for uid in (match.red_user_id, match.black_user_id):
        await store.clear_last_match(uid)
        player = await store.get_online(uid)
        if player:
            player.status = "busy"
            player.match_id = match.id
            await store.set_online(player)

    for uid in (match.red_user_id, match.black_user_id):
        payload = match.public_state(uid) | {"type": "match_start", "rematch": True}
        if money.get("balances", {}).get(uid):
            payload["balance"] = money["balances"][uid]
        await hub.send(uid, payload)

    return match.public_state(user_id) | {"type": "match_start", "rematch": True}


async def _settle_match(match: store.MatchState, reason: str | None = None) -> dict:
    if match.settled:
        return {"ok": True, "already_finished": True, "balances": {}}
    try:
        result = await asyncio.to_thread(
            dama_wallet.settle_online_game,
            match_id=match.id,
            winner_side=match.winner,
            red_user_id=match.red_user_id,
            black_user_id=match.black_user_id,
        )
    except Exception:
        result = {"ok": False, "balances": {}}
    match.settled = True
    await store.save_match(match)

    for uid in (match.red_user_id, match.black_user_id):
        payload = {
            "type": "match_over",
            "match_id": match.id,
            "winner": match.winner,
            "board": match.board,
            "turn": match.turn,
            "status": match.status,
            "stake": match.stake,
            "prize_pool": match.prize_pool,
            "system_fee": match.system_fee,
            "amount_won": result.get("amount_won"),
        }
        if reason:
            payload["reason"] = reason
        elif match.winner == "draw":
            payload["reason"] = "agreed_draw"
        if result.get("balances", {}).get(uid):
            payload["balance"] = result["balances"][uid]
        await hub.send(uid, payload)

    return result


async def _settle_and_finish(match: store.MatchState, reason: str | None = None) -> None:
    await _settle_match(match, reason=reason)
    await _finish_presence(match)


async def _finish_presence(match: store.MatchState) -> None:
    for uid in (match.red_user_id, match.black_user_id):
        await store.clear_user_match(uid)
        await store.set_last_match(uid, match.id)
        player = await store.get_online(uid)
        if not player:
            continue
        player.status = "idle"
        player.match_id = None
        await store.set_online(player)
        await hub.broadcast(
            {
                "type": "presence",
                "action": "update",
                "player": {
                    "user_id": player.user_id,
                    "display_name": player.display_name,
                    "photo_url": player.photo_url,
                    "status": player.status,
                },
            }
        )
