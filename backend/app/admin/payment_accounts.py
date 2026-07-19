"""Admin CRUD and public listing for house payment accounts."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.helpers import sanitize
from app.models.admin_audit_log import AdminAuditLog
from app.models.payment_account import PaymentAccount
from app.models.user import User

VALID_KINDS = frozenset({"deposit", "withdraw"})


def _existing_request(db: Session, admin: User, request_id: uuid.UUID) -> AdminAuditLog | None:
    row = (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.request_id == request_id)
        .first()
    )
    if row and row.admin_user_id != admin.id:
        raise HTTPException(409, "Request id is already in use")
    return row


def _audit(
    db: Session,
    admin: User,
    *,
    action: str,
    target_id,
    reason: str | None,
    before: dict | None,
    after: dict | None,
    request_id: uuid.UUID,
) -> AdminAuditLog:
    row = AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        target_type="payment_account",
        target_id=str(target_id) if target_id is not None else None,
        reason=reason,
        before_data=sanitize(before),
        after_data=sanitize(after),
        request_id=request_id,
    )
    db.add(row)
    return row


def _serialize(row: PaymentAccount, *, mask: bool = False) -> dict:
    number = row.account_number
    if mask and number and len(number) > 4:
        number = f"{'*' * max(0, len(number) - 4)}{number[-4:]}"
    return {
        "id": str(row.id),
        "kind": row.kind,
        "bank": row.bank,
        "account_name": row.account_name,
        "account_number": number,
        "is_enabled": bool(row.is_enabled),
        "sort_order": int(row.sort_order or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _clean_text(value: str, *, field: str, max_len: int) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(422, f"{field} is required")
    if len(cleaned) > max_len:
        raise HTTPException(422, f"{field} is too long")
    return cleaned


def _normalize_kind(kind: str) -> str:
    normalized = (kind or "").strip().casefold()
    if normalized not in VALID_KINDS:
        raise HTTPException(422, "kind must be deposit or withdraw")
    return normalized


def list_accounts(
    db: Session,
    *,
    kind: str | None = None,
    enabled_only: bool = False,
) -> dict:
    query = db.query(PaymentAccount)
    if kind:
        query = query.filter(PaymentAccount.kind == _normalize_kind(kind))
    if enabled_only:
        query = query.filter(PaymentAccount.is_enabled.is_(True))
    rows = (
        query.order_by(
            PaymentAccount.kind.asc(),
            PaymentAccount.sort_order.asc(),
            PaymentAccount.created_at.asc(),
        )
        .all()
    )
    return {
        "items": [_serialize(row) for row in rows],
        "total": len(rows),
    }


def list_enabled_public(db: Session, kind: str) -> dict:
    """Enabled accounts only — full numbers (needed for deposit instructions)."""
    return list_accounts(db, kind=kind, enabled_only=True)


def create_account(
    db: Session,
    admin: User,
    *,
    kind: str,
    bank: str,
    account_name: str,
    account_number: str,
    is_enabled: bool,
    sort_order: int,
    request_id: uuid.UUID,
) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing and existing.action == "payment_account.create":
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    kind_n = _normalize_kind(kind)
    bank_n = _clean_text(bank, field="bank", max_len=80)
    name_n = _clean_text(account_name, field="account_name", max_len=150)
    number_n = _clean_text(account_number, field="account_number", max_len=100)

    row = PaymentAccount(
        kind=kind_n,
        bank=bank_n,
        account_name=name_n,
        account_number=number_n,
        is_enabled=bool(is_enabled),
        sort_order=int(sort_order or 0),
    )
    db.add(row)
    db.flush()
    after = _serialize(row)
    _audit(
        db,
        admin,
        action="payment_account.create",
        target_id=row.id,
        reason=f"Created {kind_n} account {bank_n}",
        before=None,
        after=after,
        request_id=request_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "An account with this bank and number already exists for this kind"
        ) from None
    db.refresh(row)
    return {"idempotent": False, **_serialize(row)}


def update_account(
    db: Session,
    admin: User,
    account_id: uuid.UUID,
    *,
    bank: str | None,
    account_name: str | None,
    account_number: str | None,
    is_enabled: bool | None,
    sort_order: int | None,
    request_id: uuid.UUID,
) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing and existing.action == "payment_account.update":
        if existing.target_id != str(account_id):
            raise HTTPException(409, "Request id was used for a different operation")
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    row = db.query(PaymentAccount).filter(PaymentAccount.id == account_id).first()
    if not row:
        raise HTTPException(404, "Payment account not found")

    before = _serialize(row)
    if bank is not None:
        row.bank = _clean_text(bank, field="bank", max_len=80)
    if account_name is not None:
        row.account_name = _clean_text(account_name, field="account_name", max_len=150)
    if account_number is not None:
        row.account_number = _clean_text(account_number, field="account_number", max_len=100)
    if is_enabled is not None:
        row.is_enabled = bool(is_enabled)
    if sort_order is not None:
        row.sort_order = int(sort_order)

    after = _serialize(row)
    _audit(
        db,
        admin,
        action="payment_account.update",
        target_id=row.id,
        reason=f"Updated {row.kind} account {row.bank}",
        before=before,
        after=after,
        request_id=request_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "An account with this bank and number already exists for this kind"
        ) from None
    db.refresh(row)
    return {"idempotent": False, **_serialize(row)}


def delete_account(
    db: Session,
    admin: User,
    account_id: uuid.UUID,
    request_id: uuid.UUID,
) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing and existing.action == "payment_account.delete":
        if existing.target_id != str(account_id):
            raise HTTPException(409, "Request id was used for a different operation")
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    row = db.query(PaymentAccount).filter(PaymentAccount.id == account_id).first()
    if not row:
        raise HTTPException(404, "Payment account not found")

    before = _serialize(row)
    db.delete(row)
    after = {"id": str(account_id), "deleted": True}
    _audit(
        db,
        admin,
        action="payment_account.delete",
        target_id=account_id,
        reason=f"Deleted {before.get('kind')} account {before.get('bank')}",
        before=before,
        after=after,
        request_id=request_id,
    )
    db.commit()
    return {"idempotent": False, **after}


def get_enabled_deposit_account(db: Session, account_id: uuid.UUID) -> PaymentAccount | None:
    return (
        db.query(PaymentAccount)
        .filter(
            PaymentAccount.id == account_id,
            PaymentAccount.kind == "deposit",
            PaymentAccount.is_enabled.is_(True),
        )
        .first()
    )


def get_enabled_withdraw_account(db: Session, account_id: uuid.UUID) -> PaymentAccount | None:
    return (
        db.query(PaymentAccount)
        .filter(
            PaymentAccount.id == account_id,
            PaymentAccount.kind == "withdraw",
            PaymentAccount.is_enabled.is_(True),
        )
        .first()
    )
