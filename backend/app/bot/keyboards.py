"""Inline keyboards for the modernized Telegram bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.i18n import t
from app.bot.links import build_webapp_url


def _webapp_button(label: str, game: str | None, lang: str) -> InlineKeyboardButton:
    url = build_webapp_url(game, lang=lang)
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=url))


def home_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t(lang, "btn.home"), callback_data="home")]]
    )


def back_home_row(lang: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(t(lang, "btn.back"), callback_data="home")]


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_webapp_button(t(lang, "btn.play"), None, lang)],
            [
                InlineKeyboardButton(t(lang, "btn.play_games"), callback_data="games"),
                InlineKeyboardButton(t(lang, "btn.balance"), callback_data="balance"),
            ],
            [
                InlineKeyboardButton(t(lang, "btn.deposit"), callback_data="deposit"),
                InlineKeyboardButton(t(lang, "btn.withdraw"), callback_data="withdraw"),
            ],
            [
                InlineKeyboardButton(t(lang, "btn.transfer"), callback_data="transfer"),
                InlineKeyboardButton(t(lang, "btn.register"), callback_data="register"),
            ],
            [
                InlineKeyboardButton(t(lang, "btn.language"), callback_data="language"),
                InlineKeyboardButton(t(lang, "btn.help"), callback_data="help"),
            ],
            [
                InlineKeyboardButton(t(lang, "btn.invite"), callback_data="invite"),
                InlineKeyboardButton(t(lang, "btn.support"), callback_data="support"),
            ],
        ]
    )


def games_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _webapp_button(t(lang, "btn.play_bingo"), "bingo", lang),
                _webapp_button(t(lang, "btn.play_dama"), "dama", lang),
            ],
            [
                _webapp_button(t(lang, "btn.play_aviator"), "aviator", lang),
                _webapp_button(t(lang, "btn.play_plinko"), "plinko", lang),
            ],
            [_webapp_button(t(lang, "btn.play_lotto"), "lotto", lang)],
            back_home_row(lang),
        ]
    )


def open_game_keyboard(lang: str, game: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_webapp_button(t(lang, f"btn.play_{game}"), game, lang)],
            [
                InlineKeyboardButton(t(lang, "btn.play_games"), callback_data="games"),
                InlineKeyboardButton(t(lang, "btn.home"), callback_data="home"),
            ],
        ]
    )


def language_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t(lang, "btn.lang_en"), callback_data="lang_en"),
                InlineKeyboardButton(t(lang, "btn.lang_am"), callback_data="lang_am"),
            ],
            back_home_row(lang),
        ]
    )


def deposit_menu_keyboard(
    lang: str,
    accounts: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for account in accounts or []:
        label = t(
            lang,
            "btn.deposit_account",
            bank=account.get("bank") or "Bank",
        )
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"deposit_account_{account['id']}",
                )
            ]
        )
    rows.append(back_home_row(lang))
    return InlineKeyboardMarkup(rows)


def deposit_method_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "btn.paid"), callback_data="deposit_paid")],
            [InlineKeyboardButton(t(lang, "btn.back"), callback_data="deposit")],
        ]
    )


def withdraw_method_keyboard(lang: str) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                t(lang, "method.telebirr"),
                callback_data="withdraw_method_telebirr",
            )
        ],
        [
            InlineKeyboardButton(
                t(lang, "method.cbe"),
                callback_data="withdraw_method_cbe",
            )
        ],
    ]


def support_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "btn.contact_support"),
                    url="https://t.me/TelegramGamesSupport",
                )
            ],
            back_home_row(lang),
        ]
    )


def confirm_cancel_keyboard(
    lang: str,
    *,
    confirm_data: str,
    cancel_data: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "btn.confirm"), callback_data=confirm_data)],
            [InlineKeyboardButton(t(lang, "btn.cancel"), callback_data=cancel_data)],
        ]
    )
