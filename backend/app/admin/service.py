"""Admin queries and atomic wallet/payment mutations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, literal, or_, union, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.helpers import mask_account, sanitize
from app.models.admin_audit_log import AdminAuditLog
from app.models.aviator_game import AviatorBet, AviatorRound
from app.models.bingo_game import BingoGame, BingoGameResult
from app.models.dama_game import DamaGame, DamaGameResult
from app.models.lotto_game import LottoReservation, LottoRound, LottoWinner
from app.models.plinko_game import PlinkoPlay
from app.models.request_tr import WithdrawRequest
from app.models.user import User
from app.models.wallet_transaction import Deposit, WalletTransaction

ZERO = Decimal("0.00")


def money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _audit(
    db: Session,
    admin: User,
    *,
    action: str,
    target_type: str,
    target_id,
    reason: str | None,
    before: dict | None,
    after: dict | None,
    request_id: uuid.UUID,
) -> AdminAuditLog:
    row = AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        reason=reason,
        before_data=sanitize(before),
        after_data=sanitize(after),
        request_id=request_id,
    )
    db.add(row)
    return row


def _existing_request(db: Session, admin: User, request_id: uuid.UUID):
    row = db.query(AdminAuditLog).filter(
        AdminAuditLog.request_id == request_id
    ).first()
    if row and row.admin_user_id != admin.id:
        raise HTTPException(409, "Request id is already in use")
    return row


def _between(column, start: datetime | None, end: datetime | None):
    clauses = []
    if start:
        clauses.append(column >= start)
    if end:
        clauses.append(column <= end)
    return and_(*clauses) if clauses else literal(True)


def game_summary(db: Session, start: datetime | None, end: datetime | None) -> dict:
    bingo = db.query(
        func.coalesce(func.sum(BingoGameResult.stake_amount), 0),
        func.coalesce(func.sum(BingoGameResult.amount_won), 0),
        func.count(func.distinct(BingoGameResult.user_id)),
        func.count(func.distinct(BingoGameResult.game_id)),
    ).join(BingoGame, BingoGame.id == BingoGameResult.game_id).filter(
        _between(BingoGame.created_at, start, end)
    ).one()
    bingo_fee = db.query(func.coalesce(func.sum(BingoGame.system_fee), 0)).filter(
        _between(BingoGame.created_at, start, end)
    ).scalar()

    dama = db.query(
        func.coalesce(func.sum(DamaGameResult.stake_amount), 0),
        func.coalesce(func.sum(DamaGameResult.amount_won), 0),
        func.count(func.distinct(DamaGameResult.user_id)),
        func.count(func.distinct(DamaGameResult.game_id)),
    ).join(DamaGame, DamaGame.id == DamaGameResult.game_id).filter(
        _between(DamaGame.created_at, start, end)
    ).one()
    dama_fee = db.query(func.coalesce(func.sum(DamaGame.system_fee), 0)).filter(
        _between(DamaGame.created_at, start, end)
    ).scalar()

    aviator = db.query(
        func.coalesce(func.sum(AviatorBet.stake), 0),
        func.coalesce(func.sum(AviatorBet.amount_won), 0),
        func.count(func.distinct(AviatorBet.user_id)),
        func.count(func.distinct(AviatorBet.round_id)),
    ).join(AviatorRound, AviatorRound.id == AviatorBet.round_id).filter(
        _between(AviatorRound.created_at, start, end)
    ).one()
    aviator_fee = db.query(func.coalesce(func.sum(AviatorRound.system_fee), 0)).filter(
        _between(AviatorRound.created_at, start, end)
    ).scalar()

    plinko = db.query(
        func.coalesce(func.sum(PlinkoPlay.stake), 0),
        func.coalesce(func.sum(PlinkoPlay.payout), 0),
        func.count(func.distinct(PlinkoPlay.user_id)),
        func.count(PlinkoPlay.id),
    ).filter(
        PlinkoPlay.is_demo.is_(False),
        _between(PlinkoPlay.created_at, start, end),
    ).one()

    lotto = db.query(
        func.coalesce(func.sum(LottoReservation.stake), 0),
        func.count(func.distinct(LottoReservation.user_id)),
        func.count(func.distinct(LottoReservation.round_id)),
    ).filter(_between(LottoReservation.created_at, start, end)).one()
    lotto_payout = db.query(func.coalesce(func.sum(LottoWinner.prize), 0)).filter(
        _between(LottoWinner.created_at, start, end)
    ).scalar()
    lotto_fee = db.query(func.coalesce(func.sum(LottoRound.reserve_amount), 0)).filter(
        LottoRound.status == "completed",
        _between(LottoRound.created_at, start, end),
    ).scalar()

    raw = {
        "bingo": (bingo[0], bingo[1], bingo[2], bingo[3], bingo_fee),
        "dama": (dama[0], dama[1], dama[2], dama[3], dama_fee),
        "aviator": (aviator[0], aviator[1], aviator[2], aviator[3], aviator_fee),
        "plinko": (plinko[0], plinko[1], plinko[2], plinko[3], ZERO),
        "lotto": (lotto[0], lotto_payout, lotto[1], lotto[2], lotto_fee),
    }
    games = []
    total_stake = total_payout = total_fee = ZERO
    for name, (stake, payout, players, rounds, fee) in raw.items():
        stake_d, payout_d, fee_d = Decimal(stake or 0), Decimal(payout or 0), Decimal(fee or 0)
        total_stake += stake_d
        total_payout += payout_d
        total_fee += fee_d
        games.append({
            "game": name,
            "turnover": money(stake_d),
            "payouts": money(payout_d),
            "ggr": money(stake_d - payout_d),
            "explicit_system_fee": money(fee_d),
            "unique_players": int(players or 0),
            "rounds_or_plays": int(rounds or 0),
        })
    return {
        "turnover": money(total_stake),
        "payouts": money(total_payout),
        "ggr": money(total_stake - total_payout),
        "explicit_system_revenue": money(total_fee),
        "activity_label": "database activity in selected range",
        "games": games,
    }


def _active_user_count(
    db: Session, start: datetime | None, end: datetime | None
) -> int:
    """COUNT DISTINCT via SQL UNION — avoids loading all user ids into memory."""
    parts = [
        db.query(BingoGameResult.user_id.label("uid"))
        .join(BingoGame, BingoGame.id == BingoGameResult.game_id)
        .filter(_between(BingoGame.created_at, start, end)),
        db.query(DamaGameResult.user_id.label("uid"))
        .join(DamaGame, DamaGame.id == DamaGameResult.game_id)
        .filter(_between(DamaGame.created_at, start, end)),
        db.query(AviatorBet.user_id.label("uid"))
        .join(AviatorRound, AviatorRound.id == AviatorBet.round_id)
        .filter(_between(AviatorRound.created_at, start, end)),
        db.query(PlinkoPlay.user_id.label("uid")).filter(
            PlinkoPlay.is_demo.is_(False),
            _between(PlinkoPlay.created_at, start, end),
        ),
        db.query(LottoReservation.user_id.label("uid")).filter(
            _between(LottoReservation.created_at, start, end)
        ),
    ]
    combined = union(*[part.distinct() for part in parts]).subquery()
    return db.query(func.count()).select_from(combined).scalar() or 0


def dashboard(db: Session, start: datetime | None, end: datetime | None) -> dict:
    total_users = db.query(func.count(User.id)).scalar() or 0
    new_users = db.query(func.count(User.id)).filter(
        _between(User.created_at, start, end)
    ).scalar() or 0
    liabilities = db.query(func.coalesce(func.sum(User.balance), 0)).scalar()
    deposits = db.query(
        func.count(Deposit.id), func.coalesce(func.sum(Deposit.amount), 0)
    ).filter(_between(Deposit.created_at, start, end)).one()
    withdrawals = db.query(
        WithdrawRequest.status,
        func.count(WithdrawRequest.id),
        func.coalesce(func.sum(WithdrawRequest.amount), 0),
    ).filter(_between(WithdrawRequest.created_at, start, end)).group_by(
        WithdrawRequest.status
    ).all()
    withdrawal_map = {
        status.casefold(): {"count": count, "amount": money(amount)}
        for status, count, amount in withdrawals
    }
    # Action queue: all-time pending (not range-scoped) so ops never miss older items.
    pending_all = db.query(
        func.count(WithdrawRequest.id),
        func.coalesce(func.sum(WithdrawRequest.amount), 0),
    ).filter(WithdrawRequest.status == "PENDING").one()
    games = game_summary(db, start, end)
    return {
        "from": start.isoformat() if start else None,
        "to": end.isoformat() if end else None,
        "total_users": total_users,
        "new_users": new_users,
        "active_users": _active_user_count(db, start, end),
        "active_users_definition": "unique users with persisted game activity in range",
        "wallet_liabilities": money(liabilities),
        "deposits": {
            "pending_count": 0,
            "pending_amount": money(0),
            "approved_count": int(deposits[0]),
            "approved_amount": money(deposits[1]),
            "workflow": "SMS-verified deposits are completed immediately",
        },
        "withdrawals": {
            "pending": withdrawal_map.get("pending", {"count": 0, "amount": money(0)}),
            "approved": withdrawal_map.get("approved", {"count": 0, "amount": money(0)}),
            "rejected": withdrawal_map.get("rejected", {"count": 0, "amount": money(0)}),
        },
        "action_queue": {
            "pending_withdrawals": {
                "count": int(pending_all[0] or 0),
                "amount": money(pending_all[1]),
            },
        },
        **games,
    }


def list_users(
    db: Session, search: str | None, status: str | None, limit: int, offset: int, sort: str
) -> dict:
    deposit_total = db.query(
        Deposit.user_id.label("uid"), func.sum(Deposit.amount).label("total")
    ).group_by(Deposit.user_id).subquery()
    withdraw_total = db.query(
        WithdrawRequest.user_id.label("uid"),
        func.sum(WithdrawRequest.amount).label("total"),
    ).filter(WithdrawRequest.status == "APPROVED").group_by(
        WithdrawRequest.user_id
    ).subquery()
    game_counts = [
        db.query(func.count(model.id)).filter(model.user_id == User.id).correlate(User).scalar_subquery()
        for model in (BingoGameResult, DamaGameResult, AviatorBet, PlinkoPlay, LottoReservation)
    ]
    games_played = game_counts[0]
    for count in game_counts[1:]:
        games_played = games_played + count
    query = db.query(
        User,
        func.coalesce(deposit_total.c.total, 0),
        func.coalesce(withdraw_total.c.total, 0),
        games_played.label("games_played"),
    ).outerjoin(deposit_total, deposit_total.c.uid == User.id).outerjoin(
        withdraw_total, withdraw_total.c.uid == User.id
    )
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(or_(
            User.username.ilike(needle),
            User.first_name.ilike(needle),
            User.last_name.ilike(needle),
            cast(User.telegram_id, String).ilike(needle),
        ))
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))
    total = query.count()
    ordering = {
        "balance_desc": User.balance.desc(),
        "balance_asc": User.balance.asc(),
        "joined_asc": User.created_at.asc(),
        "activity_desc": User.last_seen_at.desc(),
    }.get(sort, User.created_at.desc())
    rows = query.order_by(ordering).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{
            "id": str(user.id),
            "telegram_id": str(user.telegram_id),
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "balance": money(user.balance),
            "joined_at": user.created_at,
            "last_activity_at": user.last_seen_at,
            "games_played": int(games),
            "deposit_total": money(deposited),
            "withdraw_total": money(withdrawn),
            "status": "active" if user.is_active else "inactive",
        } for user, deposited, withdrawn, games in rows],
    }


def user_detail(db: Session, user_id: uuid.UUID) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    ledger = db.query(WalletTransaction).filter(
        WalletTransaction.user_id == user.id
    ).order_by(WalletTransaction.created_at.desc()).limit(30).all()
    deposits = db.query(Deposit).filter(Deposit.user_id == user.id).order_by(
        Deposit.created_at.desc()
    ).limit(20).all()
    withdrawals = db.query(WithdrawRequest).filter(
        WithdrawRequest.user_id == user.id
    ).order_by(WithdrawRequest.created_at.desc()).limit(20).all()
    stats = {}
    for name, model, stake_col, payout_col in (
        ("bingo", BingoGameResult, BingoGameResult.stake_amount, BingoGameResult.amount_won),
        ("dama", DamaGameResult, DamaGameResult.stake_amount, DamaGameResult.amount_won),
        ("aviator", AviatorBet, AviatorBet.stake, AviatorBet.amount_won),
        ("plinko", PlinkoPlay, PlinkoPlay.stake, PlinkoPlay.payout),
    ):
        count, stake, payout = db.query(
            func.count(model.id), func.coalesce(func.sum(stake_col), 0),
            func.coalesce(func.sum(payout_col), 0),
        ).filter(model.user_id == user.id).one()
        stats[name] = {"plays": count, "turnover": money(stake), "payouts": money(payout)}
    count, stake = db.query(
        func.count(LottoReservation.id), func.coalesce(func.sum(LottoReservation.stake), 0)
    ).filter(LottoReservation.user_id == user.id).one()
    payout = db.query(func.coalesce(func.sum(LottoWinner.prize), 0)).filter(
        LottoWinner.user_id == user.id
    ).scalar()
    stats["lotto"] = {"plays": count, "turnover": money(stake), "payouts": money(payout)}
    return {
        "profile": {
            "id": str(user.id), "telegram_id": str(user.telegram_id),
            "username": user.username, "first_name": user.first_name,
            "last_name": user.last_name, "balance": money(user.balance),
            "status": "active" if user.is_active else "inactive",
            "joined_at": user.created_at, "last_activity_at": user.last_seen_at,
        },
        "game_stats": stats,
        "ledger": [{
            "id": str(tx.id), "type": tx.transaction_type, "amount": money(tx.amount),
            "balance_before": money(tx.balance_before), "balance_after": money(tx.balance_after),
            "description": tx.description, "created_at": tx.created_at,
        } for tx in ledger],
        "deposits": [{
            "id": str(row.id), "amount": money(row.amount), "method": row.method,
            "status": "COMPLETED", "created_at": row.created_at,
        } for row in deposits],
        "withdrawals": [{
            "id": str(row.id), "amount": money(row.amount), "fee": money(row.fee),
            "method": row.method, "account_name": row.account_name,
            "account_number": row.account_number, "status": row.status,
            "created_at": row.created_at, "processed_at": row.processed_at,
        } for row in withdrawals],
    }


def adjust_balance(
    db: Session, admin: User, user_id: uuid.UUID, amount: Decimal,
    reason: str, request_id: uuid.UUID,
) -> dict:
    if user_id == admin.id:
        raise HTTPException(403, "Administrators cannot adjust their own balance")
    existing = _existing_request(db, admin, request_id)
    if existing:
        if existing.action != "balance.adjust" or existing.target_id != str(user_id):
            raise HTTPException(409, "Request id was used for a different operation")
        target = db.query(User).filter(User.id == user_id).first()
        return {"idempotent": True, "balance": money(target.balance if target else 0)}
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(404, "User not found")
    before = Decimal(user.balance)
    after = before + amount
    if after < 0:
        raise HTTPException(409, "Adjustment would make balance negative")
    user.balance = after
    db.add(WalletTransaction(
        user_id=user.id, transaction_type="ADMIN_ADJUSTMENT", amount=amount,
        balance_before=before, balance_after=after, status="COMPLETED",
        reference_type="ADMIN_ADJUSTMENT", reference_id=request_id,
        description=f"Admin adjustment: {reason[:180]}",
    ))
    _audit(
        db, admin, action="balance.adjust", target_type="user", target_id=user.id,
        reason=reason, before={"balance": before}, after={"balance": after, "amount": amount},
        request_id=request_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_request(db, admin, request_id)
        if existing:
            if existing.action != "balance.adjust" or existing.target_id != str(user_id):
                raise HTTPException(409, "Request id was used for a different operation")
            target = db.query(User).filter(User.id == user_id).first()
            return {"idempotent": True, "balance": money(target.balance if target else 0)}
        raise
    return {"idempotent": False, "balance": money(after)}


def _mask_reference(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) <= 6:
        return text
    return f"{text[:3]}…{text[-3:]}"


def list_deposits(
    db: Session,
    status: str | None,
    limit: int,
    offset: int,
    *,
    search: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    """Completed SMS-verified deposits from the `deposits` ledger table.

    There is no pending deposit workflow — funds credit immediately on verify.
    """
    normalized = (status or "all").casefold()
    workflow = "SMS-verified deposits are credited immediately; there is no pending queue"
    if normalized == "pending":
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "workflow": workflow,
            "pending_supported": False,
            "items": [],
        }
    if normalized not in {"completed", "approved", "all"}:
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "workflow": workflow,
            "pending_supported": False,
            "items": [],
        }

    query = db.query(Deposit, User).join(User, User.id == Deposit.user_id)
    if start or end:
        query = query.filter(_between(Deposit.created_at, start, end))
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(or_(
            User.username.ilike(needle),
            User.first_name.ilike(needle),
            User.last_name.ilike(needle),
            cast(User.telegram_id, String).ilike(needle),
            Deposit.sms_transaction_id.ilike(needle),
            Deposit.method.ilike(needle),
        ))
    total = query.count()
    rows = query.order_by(Deposit.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "workflow": workflow,
        "pending_supported": False,
        "items": [{
            "id": str(row.id),
            "user_id": str(user.id),
            "username": user.username,
            "name": f"{user.first_name} {user.last_name or ''}".strip(),
            "amount": money(row.amount),
            "method": row.method,
            "provider": row.method,
            "status": "COMPLETED",
            "reference": _mask_reference(row.sms_transaction_id),
            "created_at": row.created_at,
            "completed_at": row.created_at,
        } for row, user in rows],
    }


def list_withdrawals(
    db: Session, status: str | None, limit: int, offset: int
) -> dict:
    query = db.query(WithdrawRequest, User).join(User, User.id == WithdrawRequest.user_id)
    if status and status.casefold() != "all":
        query = query.filter(WithdrawRequest.status == status.upper())
    total = query.count()
    rows = query.order_by(WithdrawRequest.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [{
            "id": str(row.id), "user_id": str(user.id), "username": user.username,
            "name": f"{user.first_name} {user.last_name or ''}".strip(),
            "amount": money(row.amount), "fee": money(row.fee), "method": row.method,
            "account_name": row.account_name, "account_number_masked": mask_account(row.account_number),
            "status": row.status, "created_at": row.created_at, "processed_at": row.processed_at,
        } for row, user in rows],
    }


def decide_withdrawal(
    db: Session, admin: User, withdrawal_id: uuid.UUID, approve: bool,
    reason: str | None, request_id: uuid.UUID,
) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing:
        expected_action = "withdrawal.approve" if approve else "withdrawal.reject"
        if existing.action != expected_action or existing.target_id != str(withdrawal_id):
            raise HTTPException(409, "Request id was used for a different operation")
        row = db.query(WithdrawRequest).filter(WithdrawRequest.id == withdrawal_id).first()
        return {
            "idempotent": True,
            "status": row.status if row else "UNKNOWN",
            "notify": None,
        }
    row = db.query(WithdrawRequest).filter(
        WithdrawRequest.id == withdrawal_id
    ).with_for_update().first()
    if not row:
        raise HTTPException(404, "Withdrawal not found")
    if row.status != "PENDING":
        raise HTTPException(409, f"Withdrawal is already {row.status.lower()}")
    before = {"status": row.status, "amount": row.amount}
    now = datetime.now().astimezone()
    owner = db.query(User).filter(User.id == row.user_id).with_for_update().one()
    balance_after = money(owner.balance)
    if approve:
        balance_before = Decimal(owner.balance)
        debit = Decimal(row.amount) + Decimal(row.fee or 0)
        if balance_before < debit:
            raise HTTPException(409, "User no longer has sufficient balance")
        owner.balance = balance_before - debit
        balance_after = money(owner.balance)
        db.add(WalletTransaction(
            user_id=owner.id, transaction_type="WITHDRAWAL", amount=-debit,
            balance_before=balance_before, balance_after=owner.balance, status="COMPLETED",
            reference_type="WITHDRAWAL", reference_id=row.id,
            description=f"Approved {row.method} withdrawal",
        ))
        row.status = "APPROVED"
        action = "withdrawal.approve"
    else:
        row.status = "REJECTED"
        action = "withdrawal.reject"
    row.processed_at = now
    _audit(
        db, admin, action=action, target_type="withdrawal", target_id=row.id,
        reason=reason, before=before, after={"status": row.status},
        request_id=request_id,
    )
    db.commit()
    return {
        "idempotent": False,
        "status": row.status,
        "notify": {
            "telegram_id": int(owner.telegram_id),
            "language_code": owner.language_code,
            "approved": approve,
            "amount": money(row.amount),
            "withdrawal_id": str(row.id),
            "balance": balance_after if approve else None,
            "reason": reason,
        },
    }


def game_players(
    db: Session, game: str, start: datetime | None, end: datetime | None,
    limit: int, offset: int,
) -> dict:
    mapping = {
        "bingo": (BingoGameResult, BingoGame, BingoGameResult.game_id, BingoGame.created_at,
                  BingoGameResult.stake_amount, BingoGameResult.amount_won),
        "dama": (DamaGameResult, DamaGame, DamaGameResult.game_id, DamaGame.created_at,
                 DamaGameResult.stake_amount, DamaGameResult.amount_won),
        "aviator": (AviatorBet, AviatorRound, AviatorBet.round_id, AviatorRound.created_at,
                    AviatorBet.stake, AviatorBet.amount_won),
        "lotto": (LottoReservation, LottoRound, LottoReservation.round_id, LottoReservation.created_at,
                  LottoReservation.stake, literal(0)),
    }
    if game == "plinko":
        model, timestamp, stake, payout = PlinkoPlay, PlinkoPlay.created_at, PlinkoPlay.stake, PlinkoPlay.payout
        query = db.query(
            User.id, User.username, User.first_name, func.count(model.id),
            func.sum(stake), func.sum(payout), func.max(timestamp),
        ).join(model, model.user_id == User.id).filter(
            model.is_demo.is_(False), _between(timestamp, start, end)
        ).group_by(User.id, User.username, User.first_name)
    elif game in mapping:
        model, parent, parent_fk, timestamp, stake, payout = mapping[game]
        query = db.query(
            User.id, User.username, User.first_name, func.count(model.id),
            func.sum(stake), func.sum(payout), func.max(timestamp),
        ).join(model, model.user_id == User.id).join(parent, parent.id == parent_fk).filter(
            _between(timestamp, start, end)
        ).group_by(User.id, User.username, User.first_name)
    else:
        raise HTTPException(404, "Unknown game")
    total = query.count()
    rows = query.order_by(func.sum(stake).desc()).offset(offset).limit(limit).all()
    return {
        "game": game, "total": total, "limit": limit, "offset": offset,
        "activity_label": "persisted activity in selected range",
        "items": [{
            "user_id": str(uid), "username": username, "first_name": first_name,
            "plays": plays, "turnover": money(turnover), "payouts": money(payouts),
            "last_played_at": last_played,
        } for uid, username, first_name, plays, turnover, payouts, last_played in rows],
    }


def audit_feed(db: Session, limit: int, offset: int) -> dict:
    query = db.query(AdminAuditLog, User).join(User, User.id == AdminAuditLog.admin_user_id)
    total = query.count()
    rows = query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [{
            "id": str(row.id), "admin_user_id": str(user.id), "admin_username": user.username,
            "action": row.action, "target_type": row.target_type, "target_id": row.target_id,
            "reason": row.reason, "before": row.before_data, "after": row.after_data,
            "request_id": str(row.request_id) if row.request_id else None,
            "created_at": row.created_at,
        } for row, user in rows],
    }
