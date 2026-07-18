"""Admin-only destructive data retention / database format controls.

Clear-all semantics (format except login credentials)
----------------------------------------------------
Keeps ``users`` identity rows needed for Telegram auth (id, telegram_id,
username, names, language, is_bot, referral codes, flags, etc.) and never
touches ``alembic_version``. Deletes operational game/payment/ledger/audit
history and **zeros every user balance** so the wallet matches a wiped ledger.
Admin and house-bot user rows are retained like any other user.

Games-only (``games_only``)
---------------------------
Deletes Bingo / Dama / Aviator / Plinko / Lotto game entity rows and
game-related ``wallet_transactions`` (types prefixed ``BINGO_``, ``AVIATOR_``,
``PLINKO_``, ``LOTTO_``, ``DAMA_``). Keeps users, balances, deposits,
withdraw/deposit/transfer requests, referral/SMS rows, non-game ledger txs,
and admin audit logs. Flushes Redis game room keys like clear-all.
Confirmation word: ``CLEAR_GAMES``.

Age-based options delete rows with ``created_at`` **older than** the retention
window (recent data is kept). Balances and Redis game rooms are left alone.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.helpers import sanitize
from app.models.admin_audit_log import AdminAuditLog
from app.models.aviator_game import AviatorBet, AviatorRound
from app.models.bingo_game import BingoGame, BingoGameResult
from app.models.dama_game import DamaGame, DamaGameResult
from app.models.lotto_game import (
    LottoReservation,
    LottoReservationRequest,
    LottoRound,
    LottoWinner,
)
from app.models.plinko_game import PlinkoPlay
from app.models.request_tr import DepositRequest, TransferRequest, WithdrawRequest
from app.models.sms_transaction import ReferralReward, SMSTransaction
from app.models.user import User
from app.models.wallet_transaction import Deposit, WalletTransaction

logger = logging.getLogger("app.admin.data_retention")

BATCH_SIZE = 2000
ZERO = Decimal("0.00")

# option -> days retained (None = wipe-all or games-only special path)
RETENTION_OPTIONS: dict[str, int | None] = {
    "all": None,
    "games_only": None,
    "7d": 7,
    "14d": 14,
    "21d": 21,
    "30d": 30,
    "60d": 60,
    "90d": 90,
    "120d": 120,
    "150d": 150,  # ~5 months
}

CONFIRM_ALL = "CLEAR"
CONFIRM_AGE = "DELETE"
CONFIRM_GAMES = "CLEAR_GAMES"

# Game ledger types only — never match DEPOSIT / WITHDRAWAL / ADMIN_* / BONUS / REFERRAL.
GAME_WALLET_TX_PREFIXES = ("BINGO_", "AVIATOR_", "PLINKO_", "LOTTO_", "DAMA_")

# Redis key patterns flushed on clear-all and games-only (runtime rooms / locks).
REDIS_FLUSH_PATTERNS = ("bingo:*", "aviator:*", "dama:*", "lotto:*")


def _is_games_only(option: str) -> bool:
    return option == "games_only"


def _should_flush_redis(option: str) -> bool:
    return option in ("all", "games_only")


def _cutoff_for(option: str) -> datetime | None:
    if _is_games_only(option):
        return None
    days = RETENTION_OPTIONS[option]
    if days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    """``deposits.created_at`` is timezone-naive; coerce aware cutoffs for PG/SQLite."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _confirm_word(option: str) -> str:
    if option == "all":
        return CONFIRM_ALL
    if _is_games_only(option):
        return CONFIRM_GAMES
    return CONFIRM_AGE


def _game_wallet_tx_filter():
    return or_(
        *[
            WalletTransaction.transaction_type.startswith(prefix)
            for prefix in GAME_WALLET_TX_PREFIXES
        ]
    )


def _count(db: Session, model, cutoff: datetime | None, column=None) -> int:
    col = column if column is not None else getattr(model, "created_at", None)
    query = db.query(func.count()).select_from(model)
    if cutoff is not None and col is not None:
        query = query.filter(col < cutoff)
    return int(query.scalar() or 0)


def _count_via_parent(
    db: Session,
    child,
    parent,
    parent_fk,
    parent_created,
    cutoff: datetime | None,
) -> int:
    query = db.query(func.count()).select_from(child).join(parent, parent.id == parent_fk)
    if cutoff is not None:
        query = query.filter(parent_created < cutoff)
    return int(query.scalar() or 0)


def _count_game_wallet_txs(db: Session, cutoff: datetime | None) -> int:
    query = db.query(func.count()).select_from(WalletTransaction).filter(
        _game_wallet_tx_filter()
    )
    if cutoff is not None:
        query = query.filter(WalletTransaction.created_at < cutoff)
    return int(query.scalar() or 0)


def _empty_payment_counts() -> dict[str, int]:
    return {
        "deposits": 0,
        "deposit_requests": 0,
        "withdraw_requests": 0,
        "transfer_requests": 0,
        "referral_rewards": 0,
        "sms_transactions": 0,
        "admin_audit_logs": 0,
    }


def _game_entity_counts(db: Session, cutoff: datetime | None) -> dict[str, int]:
    return {
        "lotto_winners": _count(db, LottoWinner, cutoff),
        "lotto_reservation_requests": _count(db, LottoReservationRequest, cutoff),
        "lotto_reservations": _count(db, LottoReservation, cutoff),
        "lotto_rounds": _count(db, LottoRound, cutoff),
        "bingo_game_results": _count_via_parent(
            db, BingoGameResult, BingoGame, BingoGameResult.game_id,
            BingoGame.created_at, cutoff,
        ) if cutoff else _count(db, BingoGameResult, None),
        "bingo_games": _count(db, BingoGame, cutoff),
        "dama_game_results": _count_via_parent(
            db, DamaGameResult, DamaGame, DamaGameResult.game_id,
            DamaGame.created_at, cutoff,
        ) if cutoff else _count(db, DamaGameResult, None),
        "dama_games": _count(db, DamaGame, cutoff),
        "aviator_bets": _count_via_parent(
            db, AviatorBet, AviatorRound, AviatorBet.round_id,
            AviatorRound.created_at, cutoff,
        ) if cutoff else _count(db, AviatorBet, None),
        "aviator_rounds": _count(db, AviatorRound, cutoff),
        "plinko_plays": _count(db, PlinkoPlay, cutoff),
        "wallet_transactions": _count_game_wallet_txs(db, cutoff),
    }


def preview_purge(db: Session, option: str) -> dict:
    if option not in RETENTION_OPTIONS:
        raise HTTPException(422, "Unknown retention option")

    if _is_games_only(option):
        counts = {**_game_entity_counts(db, None), **_empty_payment_counts()}
        # Prefer explicit game-ledger count (already in _game_entity_counts).
        users_kept = int(db.query(func.count()).select_from(User).scalar() or 0)
        return {
            "option": option,
            "cutoff": None,
            "confirmation_required": _confirm_word(option),
            "keeps_users": True,
            "keeps_payments": True,
            "zeros_balances": False,
            "flushes_redis_game_keys": True,
            "users_kept": users_kept,
            "balances_to_zero": 0,
            "counts": counts,
            "total_rows": sum(counts.values()),
        }

    cutoff = _cutoff_for(option)
    counts = {
        **_game_entity_counts(db, cutoff),
        "deposits": _count(db, Deposit, _as_naive_utc(cutoff)),
        "deposit_requests": _count(db, DepositRequest, cutoff),
        "withdraw_requests": _count(db, WithdrawRequest, cutoff),
        "transfer_requests": _count(db, TransferRequest, cutoff),
        "referral_rewards": _count(db, ReferralReward, cutoff),
        "sms_transactions": _count(db, SMSTransaction, cutoff),
        # Age / clear-all: all ledger rows in window (not only game types).
        "wallet_transactions": _count(db, WalletTransaction, cutoff),
        "admin_audit_logs": _count(db, AdminAuditLog, cutoff),
    }
    users_kept = int(db.query(func.count()).select_from(User).scalar() or 0)
    balances_to_zero = users_kept if option == "all" else 0
    return {
        "option": option,
        "cutoff": cutoff.isoformat() if cutoff else None,
        "confirmation_required": _confirm_word(option),
        "keeps_users": True,
        "keeps_payments": False,
        "zeros_balances": option == "all",
        "flushes_redis_game_keys": option == "all",
        "users_kept": users_kept,
        "balances_to_zero": balances_to_zero,
        "counts": counts,
        "total_rows": sum(counts.values()),
    }


def _batched_delete_ids(
    db: Session,
    model,
    id_query,
    *,
    batch_size: int = BATCH_SIZE,
) -> int:
    deleted = 0
    while True:
        ids = [row[0] for row in id_query.limit(batch_size).all()]
        if not ids:
            break
        count = (
            db.query(model)
            .filter(model.id.in_(ids))
            .delete(synchronize_session=False)
        )
        deleted += int(count or 0)
        db.flush()
    return deleted


def _delete_model(
    db: Session,
    model,
    cutoff: datetime | None,
    *,
    column=None,
) -> int:
    col = column if column is not None else getattr(model, "created_at", None)
    if cutoff is None:
        id_query = db.query(model.id)
    else:
        if col is None:
            raise RuntimeError(f"{model.__tablename__} has no created_at for age purge")
        id_query = db.query(model.id).filter(col < cutoff)
    return _batched_delete_ids(db, model, id_query)


def _delete_children_by_parent_age(
    db: Session,
    child,
    parent,
    parent_fk_col,
    parent_created,
    cutoff: datetime | None,
) -> int:
    if cutoff is None:
        return _delete_model(db, child, None)
    id_query = (
        db.query(child.id)
        .join(parent, parent.id == parent_fk_col)
        .filter(parent_created < cutoff)
    )
    return _batched_delete_ids(db, child, id_query)


def _delete_game_wallet_txs(db: Session, cutoff: datetime | None) -> int:
    id_query = db.query(WalletTransaction.id).filter(_game_wallet_tx_filter())
    if cutoff is not None:
        id_query = id_query.filter(WalletTransaction.created_at < cutoff)
    return _batched_delete_ids(db, WalletTransaction, id_query)


def _purge_game_tables(db: Session) -> dict[str, int]:
    """Delete all game entity rows + game-only ledger txs. No payments/users."""
    counts: dict[str, int] = {}

    counts["lotto_winners"] = _delete_model(db, LottoWinner, None)
    counts["lotto_reservation_requests"] = _delete_model(
        db, LottoReservationRequest, None
    )
    counts["lotto_reservations"] = _delete_model(db, LottoReservation, None)
    counts["lotto_rounds"] = _delete_model(db, LottoRound, None)

    counts["bingo_game_results"] = _delete_model(db, BingoGameResult, None)
    counts["bingo_games"] = _delete_model(db, BingoGame, None)

    counts["dama_game_results"] = _delete_model(db, DamaGameResult, None)
    counts["dama_games"] = _delete_model(db, DamaGame, None)

    counts["aviator_bets"] = _delete_model(db, AviatorBet, None)
    counts["aviator_rounds"] = _delete_model(db, AviatorRound, None)

    counts["plinko_plays"] = _delete_model(db, PlinkoPlay, None)

    counts["wallet_transactions"] = _delete_game_wallet_txs(db, None)

    counts.update(_empty_payment_counts())
    return counts


def _purge_tables(db: Session, cutoff: datetime | None) -> dict[str, int]:
    """Delete operational rows in FK-safe order. Does not touch ``users``."""
    counts: dict[str, int] = {}

    # Lotto rows that FK wallet_transactions must go before the ledger.
    counts["lotto_winners"] = _delete_model(db, LottoWinner, cutoff)
    counts["lotto_reservation_requests"] = _delete_model(
        db, LottoReservationRequest, cutoff
    )
    counts["lotto_reservations"] = _delete_model(db, LottoReservation, cutoff)
    counts["lotto_rounds"] = _delete_model(db, LottoRound, cutoff)

    counts["bingo_game_results"] = _delete_children_by_parent_age(
        db, BingoGameResult, BingoGame, BingoGameResult.game_id,
        BingoGame.created_at, cutoff,
    )
    counts["bingo_games"] = _delete_model(db, BingoGame, cutoff)

    counts["dama_game_results"] = _delete_children_by_parent_age(
        db, DamaGameResult, DamaGame, DamaGameResult.game_id,
        DamaGame.created_at, cutoff,
    )
    counts["dama_games"] = _delete_model(db, DamaGame, cutoff)

    counts["aviator_bets"] = _delete_children_by_parent_age(
        db, AviatorBet, AviatorRound, AviatorBet.round_id,
        AviatorRound.created_at, cutoff,
    )
    counts["aviator_rounds"] = _delete_model(db, AviatorRound, cutoff)

    counts["plinko_plays"] = _delete_model(db, PlinkoPlay, cutoff)

    counts["deposits"] = _delete_model(db, Deposit, _as_naive_utc(cutoff))
    counts["deposit_requests"] = _delete_model(db, DepositRequest, cutoff)
    counts["withdraw_requests"] = _delete_model(db, WithdrawRequest, cutoff)
    counts["transfer_requests"] = _delete_model(db, TransferRequest, cutoff)
    counts["referral_rewards"] = _delete_model(db, ReferralReward, cutoff)
    counts["sms_transactions"] = _delete_model(db, SMSTransaction, cutoff)

    counts["wallet_transactions"] = _delete_model(db, WalletTransaction, cutoff)

    # Age purge: drop old audits. Clear-all: drop all audits; caller writes one new.
    counts["admin_audit_logs"] = _delete_model(db, AdminAuditLog, cutoff)

    return counts


async def _flush_redis_game_keys() -> int:
    """Best-effort scan/delete of bingo/aviator/dama/lotto Redis keys."""
    try:
        from app.bingo.redis_store import get_redis

        redis = get_redis()
        deleted = 0
        for pattern in REDIS_FLUSH_PATTERNS:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=200)
                if keys:
                    deleted += int(await redis.delete(*keys))
                if cursor == 0:
                    break
        return deleted
    except Exception:
        logger.exception("Redis game-key flush failed during retention purge")
        return 0


def _existing_purge(db: Session, admin: User, request_id: uuid.UUID) -> AdminAuditLog | None:
    row = (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.request_id == request_id)
        .first()
    )
    if row and row.admin_user_id != admin.id:
        raise HTTPException(409, "Request id is already in use")
    return row


async def run_purge(
    db: Session,
    admin: User,
    *,
    option: str,
    confirmation: str,
    reason: str,
    request_id: uuid.UUID,
) -> dict:
    if option not in RETENTION_OPTIONS:
        raise HTTPException(422, "Unknown retention option")
    expected = _confirm_word(option)
    if (confirmation or "").strip() != expected:
        raise HTTPException(422, f"Confirmation must be exactly '{expected}'")
    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < 3:
        raise HTTPException(422, "A purge reason is required")

    existing = _existing_purge(db, admin, request_id)
    if existing:
        if existing.action != "data.purge":
            raise HTTPException(409, "Request id was used for a different operation")
        after = existing.after_data or {}
        return {
            "idempotent": True,
            "option": after.get("option", option),
            "deleted": after.get("deleted", {}),
            "balances_zeroed": after.get("balances_zeroed", 0),
            "redis_keys_deleted": after.get("redis_keys_deleted", 0),
            "users_kept": after.get("users_kept"),
        }

    cutoff = _cutoff_for(option)
    users_before = int(db.query(func.count()).select_from(User).scalar() or 0)

    if _is_games_only(option):
        deleted = _purge_game_tables(db)
    else:
        deleted = _purge_tables(db, cutoff)

    balances_zeroed = 0
    if option == "all":
        # Format DB except login credentials: wipe financial state with history.
        balances_zeroed = int(
            db.query(User).update(
                {User.balance: ZERO},
                synchronize_session=False,
            )
            or 0
        )
        db.flush()

    users_after = int(db.query(func.count()).select_from(User).scalar() or 0)
    if users_after != users_before:
        db.rollback()
        raise HTTPException(500, "Purge aborted: user row count changed unexpectedly")

    flush_redis = _should_flush_redis(option)
    audit_after: dict[str, Any] = {
        "option": option,
        "cutoff": cutoff.isoformat() if cutoff else None,
        "deleted": deleted,
        "balances_zeroed": balances_zeroed,
        "redis_keys_deleted": 0,
        "users_kept": users_after,
        "flushed_redis": flush_redis,
        "keeps_payments": _is_games_only(option),
    }
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="data.purge",
            target_type="database",
            target_id=option,
            reason=cleaned_reason,
            before_data=sanitize({"users": users_before}),
            after_data=sanitize(audit_after),
            request_id=request_id,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_purge(db, admin, request_id)
        if existing and existing.action == "data.purge":
            after = existing.after_data or {}
            return {
                "idempotent": True,
                "option": after.get("option", option),
                "deleted": after.get("deleted", {}),
                "balances_zeroed": after.get("balances_zeroed", 0),
                "redis_keys_deleted": after.get("redis_keys_deleted", 0),
                "users_kept": after.get("users_kept"),
            }
        raise

    redis_deleted = 0
    if flush_redis:
        redis_deleted = await _flush_redis_game_keys()
        if redis_deleted:
            row = (
                db.query(AdminAuditLog)
                .filter(AdminAuditLog.request_id == request_id)
                .first()
            )
            if row and isinstance(row.after_data, dict):
                updated = dict(row.after_data)
                updated["redis_keys_deleted"] = redis_deleted
                row.after_data = sanitize(updated)
                db.commit()

    return {
        "idempotent": False,
        "option": option,
        "deleted": deleted,
        "balances_zeroed": balances_zeroed,
        "redis_keys_deleted": redis_deleted,
        "users_kept": users_after,
        "cutoff": cutoff.isoformat() if cutoff else None,
    }
