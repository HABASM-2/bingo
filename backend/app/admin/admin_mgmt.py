"""Admin broadcast and multi-admin management services."""

from __future__ import annotations

import asyncio
import html
import logging
import uuid
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.admin.helpers import (
    SUPER_ADMIN_USERNAME,
    normalize_username,
    sanitize,
)
from app.bot.links import VALID_GAMES, build_webapp_url, normalize_game_id
from app.bot.notify import send_telegram_html
from app.core.config import settings
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser
from app.models.user import User

logger = logging.getLogger("app.admin.broadcast")

BROADCAST_CONCURRENCY = 8
BROADCAST_THROTTLE_S = 0.05
BROADCAST_ERROR_CAP = 25


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


def _webapp_base_host() -> str:
    base = (settings.TELEGRAM_WEBAPP_URL or "").strip()
    if not base:
        return ""
    return (urlparse(base).netloc or "").casefold()


def build_broadcast_markup(
    *,
    button_url: str | None,
    button_label: str | None,
    game: str | None,
) -> InlineKeyboardMarkup | None:
    label = (button_label or "").strip() or "Open"
    game_id = normalize_game_id(game)

    if game_id and game_id != "home":
        url = build_webapp_url(game_id)
        if not url:
            raise HTTPException(422, "Telegram Mini App URL is not configured")
        if not button_label:
            label = f"Play {game_id.title()}"
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(label, web_app=WebAppInfo(url=url))]]
        )

    url = (button_url or "").strip()
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(422, "button_url must be an http(s) URL")

    host = parsed.netloc.casefold()
    webapp_host = _webapp_base_host()
    if webapp_host and host == webapp_host:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(label, web_app=WebAppInfo(url=url))]]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, url=url)]]
    )


def list_admins(db: Session) -> dict:
    rows = (
        db.query(AdminUser)
        .order_by(AdminUser.created_at.asc())
        .all()
    )
    items = [
        {
            "username": SUPER_ADMIN_USERNAME,
            "is_super": True,
            "created_by": None,
            "created_at": None,
            "managed": False,
        }
    ]
    seen = {SUPER_ADMIN_USERNAME}
    for row in rows:
        if row.username in seen:
            continue
        seen.add(row.username)
        items.append(
            {
                "username": row.username,
                "is_super": False,
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "managed": True,
            }
        )
    return {"items": items, "total": len(items)}


def add_admin(db: Session, admin: User, username: str, request_id: uuid.UUID) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing and existing.action == "admins.add":
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    normalized = normalize_username(username)
    if not normalized:
        raise HTTPException(422, "Username is required")
    if len(normalized) > 32:
        raise HTTPException(422, "Username is too long")
    if normalized == SUPER_ADMIN_USERNAME:
        raise HTTPException(409, "Super-admin is already present")

    prior = (
        db.query(AdminUser)
        .filter(AdminUser.username == normalized)
        .first()
    )
    if prior:
        raise HTTPException(409, "Admin already exists")

    row = AdminUser(
        username=normalized,
        created_by=normalize_username(admin.username) or SUPER_ADMIN_USERNAME,
    )
    db.add(row)
    after = {
        "username": normalized,
        "created_by": row.created_by,
        "is_super": False,
        "managed": True,
    }
    _audit(
        db,
        admin,
        action="admins.add",
        target_type="admin_user",
        target_id=normalized,
        reason=f"Added admin @{normalized}",
        before=None,
        after=after,
        request_id=request_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Admin already exists") from None
    db.refresh(row)
    after["created_at"] = row.created_at.isoformat() if row.created_at else None
    return {"idempotent": False, **after}


def remove_admin(db: Session, admin: User, username: str, request_id: uuid.UUID) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing and existing.action == "admins.remove":
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    normalized = normalize_username(username)
    if not normalized:
        raise HTTPException(422, "Username is required")
    if normalized == SUPER_ADMIN_USERNAME:
        raise HTTPException(403, "Cannot remove the super-admin")

    row = (
        db.query(AdminUser)
        .filter(AdminUser.username == normalized)
        .first()
    )
    if not row:
        raise HTTPException(404, "Admin not found")

    before = {
        "username": row.username,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    db.delete(row)
    after = {"username": normalized, "removed": True}
    _audit(
        db,
        admin,
        action="admins.remove",
        target_type="admin_user",
        target_id=normalized,
        reason=f"Removed admin @{normalized}",
        before=before,
        after=after,
        request_id=request_id,
    )
    db.commit()
    return {"idempotent": False, **after}


def _recipient_chat_ids(db: Session) -> list[int]:
    rows = (
        db.query(User.telegram_id)
        .filter(
            User.is_bot.is_(False),
            User.is_active.is_(True),
            User.telegram_id.isnot(None),
        )
        .all()
    )
    chat_ids: list[int] = []
    for (telegram_id,) in rows:
        try:
            value = int(telegram_id)
        except (TypeError, ValueError):
            continue
        # House bots use negative sentinel ids; skip any non-positive chat.
        if value > 0:
            chat_ids.append(value)
    return chat_ids


async def broadcast_message(
    db: Session,
    admin: User,
    *,
    message: str,
    button_url: str | None,
    button_label: str | None,
    game: str | None,
    request_id: uuid.UUID,
) -> dict:
    existing = _existing_request(db, admin, request_id)
    if existing and existing.action == "telegram.broadcast":
        after = existing.after_data or {}
        return {"idempotent": True, **after}

    text = (message or "").strip()
    if not text:
        raise HTTPException(422, "Message is required")

    game_id = normalize_game_id(game)
    if game and not game_id:
        raise HTTPException(
            422,
            f"Invalid game. Allowed: {', '.join(sorted(VALID_GAMES - {'home'}))}",
        )

    markup = build_broadcast_markup(
        button_url=button_url,
        button_label=button_label,
        game=game_id,
    )

    # Escape free-form admin text for HTML parse mode.
    safe_text = html.escape(text)
    chat_ids = _recipient_chat_ids(db)
    intended = len(chat_ids)

    sem = asyncio.Semaphore(BROADCAST_CONCURRENCY)
    succeeded = 0
    failed = 0
    errors: list[dict] = []

    async def _send_one(chat_id: int) -> bool:
        async with sem:
            ok = await send_telegram_html(chat_id, safe_text, reply_markup=markup)
            await asyncio.sleep(BROADCAST_THROTTLE_S)
            return ok

    results = await asyncio.gather(
        *[_send_one(chat_id) for chat_id in chat_ids],
        return_exceptions=True,
    )

    for chat_id, result in zip(chat_ids, results):
        if result is True:
            succeeded += 1
        else:
            failed += 1
            if len(errors) < BROADCAST_ERROR_CAP:
                if isinstance(result, Exception):
                    err = type(result).__name__
                else:
                    err = "send_failed"
                errors.append({"telegram_id": chat_id, "error": err})

    after = {
        "intended": intended,
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors,
        "has_button": markup is not None,
        "game": game_id,
    }
    preview = text if len(text) <= 200 else f"{text[:200]}…"
    _audit(
        db,
        admin,
        action="telegram.broadcast",
        target_type="telegram",
        target_id="broadcast",
        reason=preview,
        before={
            "button_url": button_url,
            "button_label": button_label,
            "game": game_id,
        },
        after=after,
        request_id=request_id,
    )
    db.commit()
    logger.info(
        "Admin broadcast admin=%s intended=%s succeeded=%s failed=%s",
        normalize_username(admin.username),
        intended,
        succeeded,
        failed,
    )
    return {"idempotent": False, **after}
