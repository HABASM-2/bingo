from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from app.core.config import settings
from app.bot.handlers import (
    confirm_withdraw,
    start_command, 
    register_command, 
    deposit_menu, 
    deposit_telebirr, 
    home_menu, 
    deposit_paid,
    check_balance,
    transfer_input,
    transfer_start,
    cancel_transfer,
    confirm_transfer,
    deposit_boa,
    deposit_cbebirr,
    deposit_cbe, 
    invite_handler, 
    instruction_handler,
    support_handler, 
    cancel_withdraw,
    withdraw_handler, 
    withdraw_method_handler, 
    cancel_pending_withdraw
)


def create_bot(proxy: str | None = None):
    resolved_proxy = (proxy or settings.TELEGRAM_PROXY_URL or "").strip() or None
    # Separate clients for commands vs long-polling so a proxy/timeout
    # config applies to both paths without sharing one crowded pool.
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
        .build()
    )


    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            register_command,
            pattern="^register$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            deposit_paid,
            pattern="^deposit_paid$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            deposit_menu,
            pattern="^deposit$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            deposit_telebirr,
            pattern="^deposit_telebirr$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(deposit_cbe, pattern="^deposit_cbe$")
    )

    application.add_handler(
        CallbackQueryHandler(deposit_cbebirr, pattern="^deposit_cbebirr$")
    )

    application.add_handler(
        CallbackQueryHandler(deposit_boa, pattern="^deposit_boa$")
    )

    application.add_handler(
        CallbackQueryHandler(
            transfer_start,
            pattern="^transfer$"
        )
    )


    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            transfer_input
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            invite_handler,
            pattern="^invite$"
        )
    )


    application.add_handler(
        CallbackQueryHandler(
            confirm_transfer,
            pattern="^confirm_transfer$"
        )
    )


    application.add_handler(
        CallbackQueryHandler(
            cancel_transfer,
            pattern="^cancel_transfer$"
        )
    )
    
    application.add_handler(
        CallbackQueryHandler(
            check_balance,
            pattern="^balance$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            deposit_menu,
            pattern="^deposit$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            home_menu,
            pattern="^home$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            instruction_handler,
            pattern="^instruction$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            support_handler,
            pattern="^support$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            withdraw_handler,
            pattern="^withdraw$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            withdraw_method_handler,
            pattern="^withdraw_method_",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_withdraw,
            pattern="^confirm_withdraw$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            cancel_withdraw,
            pattern="^cancel_withdraw$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            cancel_pending_withdraw,
            pattern="^cancel_pending_withdraw_",
        )
    )

    return application