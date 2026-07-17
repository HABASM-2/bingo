"""Fire-and-forget Telegram notifications for admin / wallet events.

Failures are logged and never raised to callers so financial commits stay intact.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.i18n import t
from app.bot.links import build_webapp_url
from app.bot.locale import normalize_locale
from app.core.config import settings

logger = logging.getLogger("app.bot.notify")


def abbreviate_id(value: Any, *, keep: int = 8) -> str:
    text = str(value or "").replace("-", "")
    if len(text) <= keep:
        return text or "—"
    return f"{text[:keep]}…"


def _locale(language_code: str | None) -> str:
    return normalize_locale(language_code) or "en"


def play_games_keyboard(lang: str) -> InlineKeyboardMarkup:
    url = build_webapp_url(None, lang=lang)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "btn.play_games"), web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton(t(lang, "btn.home"), callback_data="home")],
        ]
    )


async def send_telegram_html(
    chat_id: int,
    text: str,
    *,
    reply_markup=None,
) -> bool:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        logger.warning("Telegram notify skipped: bot token not configured")
        return False
    if not chat_id:
        logger.warning("Telegram notify skipped: missing chat id")
        return False
    try:
        from telegram import Bot
        from telegram.error import Forbidden, TelegramError

        bot = Bot(token=token)
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        await bot.send_message(**kwargs)
        return True
    except Forbidden:
        logger.info("Telegram notify blocked or chat unavailable chat_id=%s", chat_id)
        return False
    except TelegramError as exc:
        logger.warning(
            "Telegram notify failed chat_id=%s error=%s",
            chat_id,
            type(exc).__name__,
        )
        return False
    except Exception:
        logger.exception("Telegram notify unexpected failure chat_id=%s", chat_id)
        return False


async def notify_withdrawal_decision(
    *,
    telegram_id: int,
    language_code: str | None,
    approved: bool,
    amount: str | Decimal,
    withdrawal_id: Any,
    balance: str | Decimal | None = None,
    reason: str | None = None,
) -> bool:
    lang = _locale(language_code)
    ref = abbreviate_id(withdrawal_id)
    amount_s = str(amount)
    if approved:
        text = t(
            lang,
            "withdraw.decision.approved",
            amount=amount_s,
            ref=ref,
            balance=str(balance if balance is not None else "—"),
        )
    else:
        text = t(
            lang,
            "withdraw.decision.rejected",
            amount=amount_s,
            ref=ref,
            reason=(reason or t(lang, "withdraw.decision.no_reason")).strip(),
        )
    return await send_telegram_html(
        int(telegram_id),
        text,
        reply_markup=play_games_keyboard(lang),
    )
