"""Shared helpers for Telegram bot handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.locale import DEFAULT_LOCALE, get_user_locale, set_user_locale
from app.db.database import SessionLocal


def resolve_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Return en|am for this chat: session cache → DB → Telegram hint → en."""
    cached = context.user_data.get("lang")
    if cached in {"en", "am"}:
        return cached

    user = update.effective_user
    if user is None:
        return DEFAULT_LOCALE

    db = SessionLocal()
    try:
        lang = get_user_locale(
            db,
            user.id,
            telegram_language_code=getattr(user, "language_code", None),
        )
    finally:
        db.close()

    context.user_data["lang"] = lang
    return lang


def persist_lang(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    locale: str,
) -> str:
    user = update.effective_user
    telegram_id = user.id if user else 0
    db = SessionLocal()
    try:
        lang = set_user_locale(db, telegram_id, locale) if telegram_id else locale
    finally:
        db.close()
    context.user_data["lang"] = lang
    return lang
