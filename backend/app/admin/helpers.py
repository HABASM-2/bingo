"""Authorization, range validation, masking, and audit sanitization helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.current_user import get_current_user
from app.api.dependencies import get_db
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger("app.admin")

# Hard-coded platform owner — always a super-admin even without a DB row.
SUPER_ADMIN_USERNAME = "has365"

SENSITIVE_KEYS = {
    "token", "access_token", "refresh_token", "password", "secret",
    "init_data", "authorization", "account_number", "phone",
}


def normalize_username(value: str | None) -> str:
    return (value or "").strip().lstrip("@").casefold()


def admin_usernames() -> frozenset[str]:
    """Env bootstrap allowlist (still honored alongside DB rows)."""
    return frozenset(
        normalized
        for item in settings.ADMIN_TELEGRAM_USERNAMES.split(",")
        if (normalized := normalize_username(item))
    )


def is_super_admin_username(username: str | None) -> bool:
    return normalize_username(username) == SUPER_ADMIN_USERNAME


def is_super_admin(user: User) -> bool:
    return is_super_admin_username(user.username)


def _username_in_admin_table(db: Session, username: str) -> bool:
    from app.models.admin_user import AdminUser

    return (
        db.query(AdminUser.id)
        .filter(AdminUser.username == username)
        .first()
        is not None
    )


def is_admin(user: User, db: Session | None = None) -> bool:
    """True if super-admin, env allowlist, or a row in ``admin_users``."""
    username = normalize_username(user.username)
    if not username:
        return False
    if username == SUPER_ADMIN_USERNAME:
        return True
    if username in admin_usernames():
        return True
    if db is not None:
        return _username_in_admin_table(db, username)
    return False


def admin_permissions(user: User, db: Session | None = None) -> dict[str, bool]:
    allowed = is_admin(user, db)
    super_user = allowed and is_super_admin(user)
    return {
        "is_admin": allowed,
        "is_super": super_user,
        "can_maintenance": super_user,
        "can_adjust_balance": super_user,
        "can_manage_admins": super_user,
    }


def require_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not is_admin(current_user, db):
        logger.warning(
            "Denied admin access user_id=%s telegram_id=%s username=%r",
            current_user.id,
            current_user.telegram_id,
            current_user.username,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


def require_super_admin(
    current_user: User = Depends(require_admin),
) -> User:
    if not is_super_admin(current_user):
        logger.warning(
            "Denied super-admin access user_id=%s telegram_id=%s username=%r",
            current_user.id,
            current_user.telegram_id,
            current_user.username,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-administrator access required",
        )
    return current_user


def sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if str(key).casefold() in SENSITIVE_KEYS else sanitize(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item) for item in value]
    return str(value)


def mask_account(value: str) -> str:
    text = value.strip()
    return text if len(text) <= 4 else f"{'*' * max(4, len(text) - 4)}{text[-4:]}"


def date_range(
    from_: datetime | None,
    to: datetime | None,
    *,
    max_days: int = 3660,
) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    end = to or now
    start = from_ or (end - timedelta(days=7))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if start > end:
        raise HTTPException(422, "'from' must be before 'to'")
    if end - start > timedelta(days=max_days):
        raise HTTPException(422, f"Date range cannot exceed {max_days} days")
    return start, end
