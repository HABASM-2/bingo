"""Admin Maintenance: delete users (separate from data retention).

Safety rules
------------
* Never delete the acting admin, allowlisted admin usernames, or house bots
  (``is_bot=True``). There is no override for these.
* Refuse delete when ``balance != 0`` unless ``force=True`` (force zeros the
  balance then cascades dependents and deletes the user row).
* Single-user delete requires confirmation ``DELETE_USERS``.
* Bulk delete of all non-admin / non-bot users requires ``DELETE_ALL_USERS``.

Cascade
-------
Deletes the user's deposits, payment requests, transfers (as sender or
receiver), referral rewards, game rows, wallet ledger rows, and nulls
``referred_by_id`` on other users who pointed at them. Admin audit logs
authored by the target are reassigned to the acting admin so the FK stays
valid.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.helpers import is_admin, normalize_username, sanitize
from app.models.admin_audit_log import AdminAuditLog
from app.models.aviator_game import AviatorBet
from app.models.bingo_game import BingoGameResult
from app.models.dama_game import DamaGame, DamaGameResult
from app.models.lotto_game import LottoReservation, LottoReservationRequest, LottoWinner
from app.models.plinko_game import PlinkoPlay
from app.models.request_tr import DepositRequest, TransferRequest, WithdrawRequest
from app.models.sms_transaction import ReferralReward
from app.models.user import User
from app.models.wallet_transaction import Deposit, WalletTransaction

ZERO = Decimal("0.00")
CONFIRM_ONE = "DELETE_USERS"
CONFIRM_ALL = "DELETE_ALL_USERS"


def _existing_request(db: Session, admin: User, request_id: uuid.UUID) -> AdminAuditLog | None:
    row = (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.request_id == request_id)
        .first()
    )
    if row and row.admin_user_id != admin.id:
        raise HTTPException(409, "Request id is already in use")
    return row


def _is_protected(db: Session, user: User) -> bool:
    """Admins (super / env / DB allowlist) and house bots cannot be deleted."""
    if user.is_bot:
        return True
    if is_admin(user, db):
        return True
    return False


def resolve_user_query(db: Session, query: str) -> User:
    """Resolve a user by UUID, telegram id, or username (@optional)."""
    from sqlalchemy import func

    raw = (query or "").strip()
    if not raw:
        raise HTTPException(422, "User query is required")

    # UUID
    try:
        uid = uuid.UUID(raw)
        user = db.query(User).filter(User.id == uid).first()
        if user:
            return user
    except ValueError:
        pass

    # Telegram id (integer)
    if raw.lstrip("-").isdigit():
        tg = int(raw)
        user = db.query(User).filter(User.telegram_id == tg).first()
        if user:
            return user

    # Username (case-insensitive, optional leading @)
    needle = normalize_username(raw)
    user = (
        db.query(User)
        .filter(
            or_(
                func.lower(User.username) == needle,
                func.lower(User.username) == f"@{needle}",
            )
        )
        .first()
    )
    if user:
        return user

    raise HTTPException(404, "User not found")


def _delete_user_dependents(db: Session, user: User, *, reassign_admin: User) -> dict[str, int]:
    """Remove or reassign rows that FK to this user. Returns delete counts."""
    uid = user.id
    counts: dict[str, int] = {}

    # Reassign audit authorship so we can delete the user row.
    reassigned = (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.admin_user_id == uid)
        .update(
            {AdminAuditLog.admin_user_id: reassign_admin.id},
            synchronize_session=False,
        )
    )
    counts["admin_audit_logs_reassigned"] = int(reassigned or 0)

    # Null referral pointers at this user.
    cleared_refs = (
        db.query(User)
        .filter(User.referred_by_id == uid)
        .update({User.referred_by_id: None}, synchronize_session=False)
    )
    counts["referred_by_cleared"] = int(cleared_refs or 0)

    # Null optional winner pointer on dama games.
    cleared_winners = (
        db.query(DamaGame)
        .filter(DamaGame.winner_user_id == uid)
        .update({DamaGame.winner_user_id: None}, synchronize_session=False)
    )
    counts["dama_winners_cleared"] = int(cleared_winners or 0)

    def _del(model, *filters) -> int:
        return int(
            db.query(model).filter(*filters).delete(synchronize_session=False) or 0
        )

    counts["bingo_game_results"] = _del(BingoGameResult, BingoGameResult.user_id == uid)
    counts["dama_game_results"] = _del(DamaGameResult, DamaGameResult.user_id == uid)
    counts["aviator_bets"] = _del(AviatorBet, AviatorBet.user_id == uid)
    counts["plinko_plays"] = _del(PlinkoPlay, PlinkoPlay.user_id == uid)
    counts["lotto_winners"] = _del(LottoWinner, LottoWinner.user_id == uid)
    counts["lotto_reservation_requests"] = _del(
        LottoReservationRequest, LottoReservationRequest.user_id == uid
    )
    counts["lotto_reservations"] = _del(LottoReservation, LottoReservation.user_id == uid)

    counts["referral_rewards"] = _del(
        ReferralReward,
        or_(
            ReferralReward.inviter_id == uid,
            ReferralReward.invited_user_id == uid,
        ),
    )

    counts["deposit_requests"] = _del(DepositRequest, DepositRequest.user_id == uid)
    counts["withdraw_requests"] = _del(WithdrawRequest, WithdrawRequest.user_id == uid)
    counts["transfer_requests"] = _del(
        TransferRequest,
        or_(
            TransferRequest.sender_id == uid,
            TransferRequest.receiver_id == uid,
        ),
    )
    counts["deposits"] = _del(Deposit, Deposit.user_id == uid)
    counts["wallet_transactions"] = _del(
        WalletTransaction, WalletTransaction.user_id == uid
    )

    db.flush()
    return counts


def _guard_deletable(db: Session, user: User, actor: User, *, force: bool) -> None:
    if user.id == actor.id:
        raise HTTPException(422, "Cannot delete your own account")
    if _is_protected(db, user):
        raise HTTPException(422, "Cannot delete admin or bot users")
    if user.balance != ZERO and not force:
        raise HTTPException(
            422,
            "User has a non-zero balance; set force=true to zero and delete",
        )


def delete_user_by_query(
    db: Session,
    admin: User,
    *,
    query: str,
    confirmation: str,
    reason: str,
    request_id: uuid.UUID,
    force: bool = False,
) -> dict[str, Any]:
    if (confirmation or "").strip() != CONFIRM_ONE:
        raise HTTPException(422, f"Confirmation must be exactly '{CONFIRM_ONE}'")
    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < 3:
        raise HTTPException(422, "A delete reason is required")

    existing = _existing_request(db, admin, request_id)
    if existing:
        if existing.action != "users.delete":
            raise HTTPException(409, "Request id was used for a different operation")
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    target = resolve_user_query(db, query)
    _guard_deletable(db, target, admin, force=force)

    before = {
        "id": str(target.id),
        "telegram_id": target.telegram_id,
        "username": target.username,
        "balance": str(target.balance),
        "force": force,
    }

    if target.balance != ZERO and force:
        target.balance = ZERO
        db.flush()

    deleted = _delete_user_dependents(db, target, reassign_admin=admin)
    db.delete(target)
    db.flush()

    after: dict[str, Any] = {
        "deleted_user": before,
        "dependents": deleted,
        "mode": "one",
        "force": force,
    }
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="users.delete",
            target_type="user",
            target_id=before["id"],
            reason=cleaned_reason,
            before_data=sanitize(before),
            after_data=sanitize(after),
            request_id=request_id,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_request(db, admin, request_id)
        if existing and existing.action == "users.delete":
            return {"idempotent": True, **(existing.after_data or {})}
        raise

    return {"idempotent": False, **after}


def delete_all_non_protected_users(
    db: Session,
    admin: User,
    *,
    confirmation: str,
    reason: str,
    request_id: uuid.UUID,
    force: bool = False,
) -> dict[str, Any]:
    """Delete every non-admin, non-bot user (extreme). Skips non-zero balance unless force."""
    if (confirmation or "").strip() != CONFIRM_ALL:
        raise HTTPException(422, f"Confirmation must be exactly '{CONFIRM_ALL}'")
    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < 3:
        raise HTTPException(422, "A delete reason is required")

    existing = _existing_request(db, admin, request_id)
    if existing:
        if existing.action != "users.delete_all":
            raise HTTPException(409, "Request id was used for a different operation")
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    candidates = (
        db.query(User)
        .filter(User.is_bot.is_(False))
        .all()
    )
    deleted_ids: list[str] = []
    skipped: list[dict[str, Any]] = []
    dependents_total: dict[str, int] = {}

    for user in candidates:
        if user.id == admin.id or _is_protected(db, user):
            skipped.append({
                "id": str(user.id),
                "username": user.username,
                "reason": "protected",
            })
            continue
        if user.balance != ZERO and not force:
            skipped.append({
                "id": str(user.id),
                "username": user.username,
                "reason": "non_zero_balance",
                "balance": str(user.balance),
            })
            continue
        if user.balance != ZERO and force:
            user.balance = ZERO
            db.flush()
        dep = _delete_user_dependents(db, user, reassign_admin=admin)
        for key, value in dep.items():
            dependents_total[key] = dependents_total.get(key, 0) + value
        deleted_ids.append(str(user.id))
        db.delete(user)
        db.flush()

    after: dict[str, Any] = {
        "mode": "all_non_protected",
        "force": force,
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "skipped": skipped,
        "dependents": dependents_total,
    }
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="users.delete_all",
            target_type="users",
            target_id="all_non_protected",
            reason=cleaned_reason,
            before_data=sanitize({"candidate_count": len(candidates)}),
            after_data=sanitize(after),
            request_id=request_id,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_request(db, admin, request_id)
        if existing and existing.action == "users.delete_all":
            return {"idempotent": True, **(existing.after_data or {})}
        raise

    return {"idempotent": False, **after}
