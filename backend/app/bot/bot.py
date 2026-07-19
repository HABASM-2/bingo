"""Telegram bot application factory and command registration."""

from __future__ import annotations

import logging

from telegram import BotCommand, BotCommandScopeDefault
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from app.bot.handlers import (
    aviator_command,
    balance_command,
    bingo_command,
    cancel_pending_withdraw,
    cancel_transfer,
    cancel_withdraw,
    check_balance,
    confirm_transfer,
    confirm_withdraw,
    dama_command,
    deposit_account_handler,
    deposit_command,
    deposit_menu,
    deposit_paid,
    games_command,
    games_menu,
    help_handler,
    home_menu,
    instruction_handler,
    invite_command,
    invite_handler,
    language_menu,
    language_set,
    lotto_command,
    play_command,
    plinko_command,
    register_command,
    start_command,
    support_handler,
    transfer_input,
    transfer_start,
    withdraw_command,
    withdraw_handler,
    withdraw_method_handler,
)
from app.bot.i18n import COMMAND_KEYS, t
from app.core.config import settings

logger = logging.getLogger(__name__)


def _commands_for_locale(locale: str) -> list[BotCommand]:
    return [BotCommand(command, t(locale, key)) for command, key in COMMAND_KEYS]


async def _register_bot_commands(application: Application) -> None:
    """Register localized command menus (English default + Amharic)."""
    bot = application.bot
    try:
        await bot.set_my_commands(
            _commands_for_locale("en"),
            language_code=None,
            scope=BotCommandScopeDefault(),
        )
        await bot.set_my_commands(
            _commands_for_locale("en"),
            language_code="en",
        )
        await bot.set_my_commands(
            _commands_for_locale("am"),
            language_code="am",
        )
        logger.info("Telegram bot commands registered (en/am)")
    except Exception:
        logger.exception("Failed to register Telegram bot commands")


def create_bot(proxy: str | None = None):
    resolved_proxy = (proxy or settings.TELEGRAM_PROXY_URL or "").strip() or None
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=10.0,
        proxy=resolved_proxy,
    )
    get_updates_request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=30.0,
        write_timeout=20.0,
        pool_timeout=10.0,
        proxy=resolved_proxy,
    )

    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(_register_bot_commands)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(CommandHandler("games", games_command))
    application.add_handler(CommandHandler("bingo", bingo_command))
    application.add_handler(CommandHandler("dama", dama_command))
    application.add_handler(CommandHandler("aviator", aviator_command))
    application.add_handler(CommandHandler("plinko", plinko_command))
    application.add_handler(CommandHandler("lotto", lotto_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("language", language_menu))
    application.add_handler(CommandHandler("lang", language_menu))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("deposit", deposit_command))
    application.add_handler(CommandHandler("withdraw", withdraw_command))
    application.add_handler(CommandHandler("invite", invite_command))

    application.add_handler(CallbackQueryHandler(register_command, pattern="^register$"))
    application.add_handler(CallbackQueryHandler(deposit_paid, pattern="^deposit_paid$"))
    application.add_handler(CallbackQueryHandler(deposit_menu, pattern="^deposit$"))
    application.add_handler(
        CallbackQueryHandler(deposit_account_handler, pattern="^deposit_account_")
    )
    application.add_handler(CallbackQueryHandler(transfer_start, pattern="^transfer$"))
    application.add_handler(CallbackQueryHandler(invite_handler, pattern="^invite$"))
    application.add_handler(CallbackQueryHandler(confirm_transfer, pattern="^confirm_transfer$"))
    application.add_handler(CallbackQueryHandler(cancel_transfer, pattern="^cancel_transfer$"))
    application.add_handler(CallbackQueryHandler(check_balance, pattern="^balance$"))
    application.add_handler(CallbackQueryHandler(home_menu, pattern="^home$"))
    application.add_handler(CallbackQueryHandler(games_menu, pattern="^games$"))
    application.add_handler(CallbackQueryHandler(help_handler, pattern="^help$"))
    application.add_handler(CallbackQueryHandler(instruction_handler, pattern="^instruction$"))
    application.add_handler(CallbackQueryHandler(support_handler, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(language_menu, pattern="^language$"))
    application.add_handler(CallbackQueryHandler(language_set, pattern="^lang_(en|am)$"))
    application.add_handler(CallbackQueryHandler(withdraw_handler, pattern="^withdraw$"))
    application.add_handler(
        CallbackQueryHandler(withdraw_method_handler, pattern="^withdraw_method_")
    )
    application.add_handler(CallbackQueryHandler(confirm_withdraw, pattern="^confirm_withdraw$"))
    application.add_handler(CallbackQueryHandler(cancel_withdraw, pattern="^cancel_withdraw$"))
    application.add_handler(
        CallbackQueryHandler(cancel_pending_withdraw, pattern="^cancel_pending_withdraw_")
    )

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_input)
    )

    return application
