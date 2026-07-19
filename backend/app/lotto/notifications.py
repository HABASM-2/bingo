"""Lotto pre-draw Telegram / in-app notifications.

Fire-and-forget: failures are logged and never roll back settlement.
Idempotent via Redis SET NX (in-memory fallback when Redis is unavailable).

Winner results: Telegram only (no in-app winner toasts).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.bot import notify as bot_notify
from app.db.database import SessionLocal
from app.lotto import service
from app.lotto.manager import hub as lotto_hub
from app.models.lotto_game import LottoReservation, LottoRound, LottoWinner
from app.models.user import User

logger = logging.getLogger(__name__)

NOTIFY_TTL_SECONDS = 60 * 60 * 6
_claimed_local: set[str] = set()

_RANK_SHORT = {1: "1st", 2: "2nd", 3: "3rd"}


def _pre_draw_key(round_id: str) -> str:
    return f"lotto:notify:pre_draw:{round_id}"


def _winners_key(round_id: str) -> str:
    return f"lotto:notify:winners:{round_id}"


async def claim_once(key: str) -> bool:
    """Return True the first time ``key`` is claimed; False thereafter."""
    try:
        from app.bingo.redis_store import get_redis

        redis = get_redis()
        return bool(await redis.set(key, "1", nx=True, ex=NOTIFY_TTL_SECONDS))
    except Exception:
        if key in _claimed_local:
            return False
        _claimed_local.add(key)
        return True


def reset_local_claims() -> None:
    """Test helper — clear in-memory idempotency keys."""
    _claimed_local.clear()


def real_stakers_by_user(
    db: Session, round_id: UUID
) -> dict[UUID, tuple[User, list[int]]]:
    """Map real (non-bot) staker users → (user, sorted reserved numbers)."""
    rows = (
        db.query(LottoReservation, User)
        .join(User, User.id == LottoReservation.user_id)
        .filter(LottoReservation.round_id == round_id)
        .order_by(LottoReservation.number)
        .all()
    )
    by_user: dict[UUID, tuple[User, list[int]]] = {}
    numbers: dict[UUID, list[int]] = defaultdict(list)
    for reservation, user in rows:
        if user.is_bot:
            continue
        numbers[user.id].append(int(reservation.number))
        by_user[user.id] = (user, numbers[user.id])
    for user_id, (_, held) in by_user.items():
        by_user[user_id] = (by_user[user_id][0], sorted(held))
    return by_user


def real_winners(
    db: Session, round_id: UUID
) -> list[tuple[LottoWinner, User, LottoRound]]:
    """Winning rows for non-bot users, ordered by rank."""
    round_ = db.query(LottoRound).filter(LottoRound.id == round_id).one_or_none()
    if round_ is None:
        return []
    rows = (
        db.query(LottoWinner, User)
        .join(User, User.id == LottoWinner.user_id)
        .filter(LottoWinner.round_id == round_id)
        .order_by(LottoWinner.rank)
        .all()
    )
    return [(winner, user, round_) for winner, user in rows if not user.is_bot]


def winner_display_name(user: User, *, round_code: str, reservation: LottoReservation | None = None) -> str:
    """Public-facing name; bots get dummy labels (admin stays Bright Bot)."""
    if reservation is not None:
        return service._resolve_display_name(reservation, user, round_code=round_code)
    if user.is_bot:
        from app.bingo.dummy_names import pick_dummy_name

        return pick_dummy_name(round_code, str(user.id))
    return user.first_name or user.username or f"Player {str(user.id)[:6]}"


def format_results_summary(
    winners: list[tuple[LottoWinner, User]],
    *,
    round_code: str,
    reservations_by_number: dict[int, LottoReservation] | None = None,
) -> str:
    """Compact ``1st: Name — 150.00 ETB; 2nd: …`` listing for broadcasts."""
    parts: list[str] = []
    for winner, user in winners:
        rank_label = _RANK_SHORT.get(int(winner.rank), str(winner.rank))
        reservation = (
            reservations_by_number.get(int(winner.number))
            if reservations_by_number
            else None
        )
        name = winner_display_name(
            user, round_code=round_code, reservation=reservation
        )
        prize = Decimal(winner.prize).quantize(service.MONEY)
        parts.append(f"{rank_label}: {name} — {prize} ETB")
    return "; ".join(parts)


def winner_rows_ordered(
    db: Session, round_id: UUID
) -> list[tuple[LottoWinner, User]]:
    """All prize ranks (bots included), ordered by rank."""
    return (
        db.query(LottoWinner, User)
        .join(User, User.id == LottoWinner.user_id)
        .filter(LottoWinner.round_id == round_id)
        .order_by(LottoWinner.rank)
        .all()
    )


async def deliver_in_app_notice(user_id: str, message: dict) -> bool:
    """Push a personal notice through hubs that may still be open off Lotto."""
    delivered = False
    try:
        from app.bingo.manager import manager as bingo_manager

        if await bingo_manager.send_to_user(user_id, message):
            delivered = True
    except Exception:
        logger.exception("Bingo in-app lotto notice failed user_id=%s", user_id)

    for label, sender in (
        ("dama", _try_dama_send),
        ("aviator", _try_aviator_send),
    ):
        try:
            if await sender(user_id, message):
                delivered = True
        except Exception:
            logger.exception(
                "%s in-app lotto notice failed user_id=%s", label, user_id
            )
    return delivered


async def _try_dama_send(user_id: str, message: dict) -> bool:
    from app.dama.manager import hub as dama_hub

    if not dama_hub.is_connected(user_id):
        return False
    return bool(await dama_hub.send(user_id, message))


async def _try_aviator_send(user_id: str, message: dict) -> bool:
    from app.aviator.manager import hub as aviator_hub

    return bool(await aviator_hub.send(user_id, message))


def schedule_pre_draw(round_id: str | UUID) -> None:
    """Fire-and-forget from sync request handlers."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        notify_pre_draw(str(round_id)),
        name=f"lotto-pre-draw-{round_id}",
    )


def schedule_winners(round_id: str | UUID) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        notify_winners(str(round_id)),
        name=f"lotto-winners-{round_id}",
    )


async def notify_pre_draw(round_id: str) -> None:
    """Telegram + in-app about-to-draw for real stakers not on the Lotto tab."""
    if not await claim_once(_pre_draw_key(round_id)):
        return

    payloads: list[tuple[User, list[int], str]] = []
    stake = "0.00"
    seconds = service.COUNTDOWN_SECONDS
    db = SessionLocal()
    try:
        try:
            rid = UUID(str(round_id))
        except ValueError:
            return
        round_ = db.query(LottoRound).filter(LottoRound.id == rid).one_or_none()
        if round_ is None or round_.status not in ("countdown", "drawing"):
            return
        stake = str(Decimal(round_.room_stake).quantize(service.MONEY))
        for user_id, (user, numbers) in real_stakers_by_user(db, rid).items():
            uid = str(user_id)
            if lotto_hub.is_connected(uid):
                continue
            payloads.append((user, numbers, uid))
    finally:
        db.close()

    if not payloads:
        return

    notice = {
        "type": "lotto_notice",
        "kind": "pre_draw",
        "round_id": str(round_id),
        "stake": stake,
        "seconds": seconds,
    }
    for user, numbers, uid in payloads:
        try:
            await deliver_in_app_notice(uid, notice)
        except Exception:
            logger.exception("In-app pre-draw notice failed user_id=%s", uid)
        if not user.telegram_id:
            continue
        try:
            await bot_notify.notify_lotto_pre_draw(
                telegram_id=int(user.telegram_id),
                language_code=user.language_code,
                stake=stake,
                seconds=seconds,
                numbers=numbers,
            )
        except Exception:
            logger.exception(
                "Telegram pre-draw notify failed telegram_id=%s",
                user.telegram_id,
            )


async def notify_winners(round_id: str) -> None:
    """Broadcast results summary via Telegram to every real staker.

    Idempotent per round. Skips bots. Bot winners appear under public dummy
    names in the summary. In-app winner toasts are intentionally not sent —
    winners are already announced in Telegram and on the Lotto UI.
    """
    if not await claim_once(_winners_key(round_id)):
        return

    stake = "0.00"
    round_code = "—"
    summary = ""
    stakers: list[tuple[User, str]] = []
    db = SessionLocal()
    try:
        try:
            rid = UUID(str(round_id))
        except ValueError:
            return
        round_ = db.query(LottoRound).filter(LottoRound.id == rid).one_or_none()
        if round_ is None:
            return
        rows = winner_rows_ordered(db, rid)
        if len(rows) < 3:
            return
        stake = str(Decimal(round_.room_stake).quantize(service.MONEY))
        round_code = round_.round_code
        reservations_by_number = {
            int(row.number): row
            for row in db.query(LottoReservation)
            .filter(LottoReservation.round_id == rid)
            .all()
        }
        summary = format_results_summary(
            rows,
            round_code=round_code,
            reservations_by_number=reservations_by_number,
        )
        for user_id, (user, _) in real_stakers_by_user(db, rid).items():
            stakers.append((user, str(user_id)))
    finally:
        db.close()

    if not stakers or not summary:
        return

    for user, _uid in stakers:
        if not user.telegram_id:
            continue
        try:
            await bot_notify.notify_lotto_results(
                telegram_id=int(user.telegram_id),
                language_code=user.language_code,
                stake=stake,
                round_code=round_code,
                summary=summary,
            )
        except Exception:
            logger.exception(
                "Telegram results notify failed telegram_id=%s",
                user.telegram_id,
            )
