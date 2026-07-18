"""Authenticated profile history: paginated game + payment lists."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.aviator import wallet as aviator_wallet
from app.bingo import wallet as bingo_wallet
from app.dama import wallet as dama_wallet
from app.lotto import service as lotto_service
from app.models.request_tr import WithdrawRequest
from app.models.wallet_transaction import Deposit
from app.plinko import service as plinko_service

PROFILE_LIMIT = 5
PROFILE_LIMIT_MAX = 20
GAME_KEYS = frozenset({"bingo", "dama", "aviator", "plinko", "lotto"})


def _clamp_limit(limit: int, *, default: int = PROFILE_LIMIT) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, PROFILE_LIMIT_MAX))


def _clamp_offset(offset: int) -> int:
    try:
        value = int(offset)
    except (TypeError, ValueError):
        value = 0
    return max(0, value)


def _page(items: list, total: int, limit: int, offset: int) -> dict:
    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def _mask_account(account_number: str | None) -> str | None:
    """Show only the last 4 digits of a withdraw destination."""
    raw = (account_number or "").strip()
    if not raw:
        return None
    if len(raw) <= 4:
        return "*" * len(raw)
    return f"{'*' * (len(raw) - 4)}{raw[-4:]}"


def list_deposits(db: Session, user_id: UUID, limit: int = PROFILE_LIMIT, offset: int = 0) -> dict:
    safe_limit = _clamp_limit(limit)
    safe_offset = _clamp_offset(offset)
    base = db.query(Deposit).filter(Deposit.user_id == user_id)
    total = base.count()
    rows = (
        base.order_by(Deposit.created_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
    return _page(
        [
            {
                "id": str(row.id),
                "amount": str(row.amount),
                "method": row.method,
                "status": "COMPLETED",
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        total,
        safe_limit,
        safe_offset,
    )


def list_withdrawals(
    db: Session, user_id: UUID, limit: int = PROFILE_LIMIT, offset: int = 0
) -> dict:
    safe_limit = _clamp_limit(limit)
    safe_offset = _clamp_offset(offset)
    base = db.query(WithdrawRequest).filter(WithdrawRequest.user_id == user_id)
    total = base.count()
    rows = (
        base.order_by(WithdrawRequest.created_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
    return _page(
        [
            {
                "id": str(row.id),
                "amount": str(row.amount),
                "fee": str(row.fee),
                "method": row.method,
                "status": row.status,
                "account_masked": _mask_account(row.account_number),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        total,
        safe_limit,
        safe_offset,
    )


def game_history(
    db: Session,
    user_id: UUID,
    game: str,
    limit: int = PROFILE_LIMIT,
    offset: int = 0,
) -> dict:
    """One page of history for a single game title: {items, total, limit, offset}."""
    key = (game or "").strip().lower()
    if key not in GAME_KEYS:
        raise ValueError("game must be bingo, dama, aviator, plinko, or lotto")

    safe_limit = _clamp_limit(limit)
    safe_offset = _clamp_offset(offset)
    uid = str(user_id)

    if key == "bingo":
        raw = bingo_wallet.get_user_history(uid, limit=safe_limit, offset=safe_offset)
        return _page(raw.get("games") or [], raw.get("total") or 0, safe_limit, safe_offset)

    if key == "dama":
        raw = dama_wallet.get_user_history(uid, limit=safe_limit, offset=safe_offset)
        return _page(raw.get("games") or [], raw.get("total") or 0, safe_limit, safe_offset)

    if key == "aviator":
        raw = aviator_wallet.get_user_history(uid, limit=safe_limit, offset=safe_offset)
        return _page(raw.get("bets") or [], raw.get("total") or 0, safe_limit, safe_offset)

    if key == "plinko":
        raw = plinko_service.history(db, user_id, safe_limit, safe_offset)
        return _page(raw.get("items") or [], raw.get("total") or 0, safe_limit, safe_offset)

    raw = lotto_service.history(db, user_id, safe_limit, safe_offset)
    return _page(raw.get("items") or [], raw.get("total") or 0, safe_limit, safe_offset)


def profile_summary(db: Session, user_id: UUID, limit: int = PROFILE_LIMIT) -> dict:
    """Light profile header payload (no per-game history arrays).

    Prefer ``game_history`` / ``list_deposits`` / ``list_withdrawals`` for pages.
    """
    safe_limit = _clamp_limit(limit)
    return {
        "limit": safe_limit,
        "games": sorted(GAME_KEYS),
    }
