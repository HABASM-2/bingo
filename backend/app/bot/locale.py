"""Resolve and persist bot language preference (en | am)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User

SUPPORTED_LOCALES = frozenset({"en", "am"})
DEFAULT_LOCALE = "en"


def normalize_locale(value: str | None) -> str | None:
    """Map Telegram / stored codes onto en|am, or None if unknown."""
    if not value:
        return None
    code = value.strip().lower().replace("_", "-")
    if code in SUPPORTED_LOCALES:
        return code
    primary = code.split("-", 1)[0]
    if primary in SUPPORTED_LOCALES:
        return primary
    if primary.startswith("am"):
        return "am"
    if primary.startswith("en"):
        return "en"
    return None


def hint_locale_from_telegram(language_code: str | None) -> str:
    """Use Telegram language as a soft hint; English remains the default."""
    return normalize_locale(language_code) or DEFAULT_LOCALE


def get_user_locale(
    db: Session,
    telegram_id: int,
    *,
    telegram_language_code: str | None = None,
) -> str:
    """Prefer persisted user.language_code when it is en|am; else Telegram hint; else en."""
    user = (
        db.query(User)
        .filter(User.telegram_id == telegram_id)
        .first()
    )
    if user:
        stored = normalize_locale(user.language_code)
        if stored:
            return stored
    return hint_locale_from_telegram(telegram_language_code)


def set_user_locale(db: Session, telegram_id: int, locale: str) -> str:
    """Persist bot language on the user row when the account exists."""
    normalized = normalize_locale(locale) or DEFAULT_LOCALE
    user = (
        db.query(User)
        .filter(User.telegram_id == telegram_id)
        .first()
    )
    if user:
        user.language_code = normalized
        db.commit()
    return normalized
