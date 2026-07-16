import asyncio
import logging
import os

from telegram.error import NetworkError, TimedOut

from app.bot.bot import create_bot
from app.core.config import settings


logger = logging.getLogger(__name__)

bot_application = None
_bot_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


async def _safe_shutdown_bot() -> None:
    """Best-effort teardown when startup fails mid-way or on shutdown."""
    global bot_application

    app = bot_application
    if app is None:
        return

    try:
        updater = getattr(app, "updater", None)
        if updater is not None and getattr(updater, "running", False):
            await updater.stop()
    except Exception:
        logger.debug("Telegram updater stop failed during cleanup", exc_info=True)

    try:
        if getattr(app, "running", False):
            await app.stop()
    except Exception:
        logger.debug("Telegram app stop failed during cleanup", exc_info=True)

    try:
        await app.shutdown()
    except Exception:
        logger.debug("Telegram app shutdown failed during cleanup", exc_info=True)

    bot_application = None


async def _connect_bot_once(proxy: str | None) -> bool:
    """Initialize + start polling. Returns True when the bot is live."""
    global bot_application

    await _safe_shutdown_bot()
    bot_application = create_bot(proxy=proxy)
    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling(
        drop_pending_updates=False,
        allowed_updates=None,
    )
    return True


async def _bot_supervisor(stop_event: asyncio.Event, proxy: str | None) -> None:
    """Keep trying until Telegram accepts the connection, then stay attached.

    FastAPI must not wait on api.telegram.org during lifespan startup, but the
    wallet / balance bot still has to come online as soon as the network allows.
    """
    delay = 3.0
    max_delay = 60.0
    attempt = 0

    while not stop_event.is_set():
        attempt += 1
        try:
            await _connect_bot_once(proxy)
            logger.info("Telegram bot running")
            print("Telegram bot running")
            # Park until shutdown — polling runs on PTB's own tasks.
            await stop_event.wait()
            return
        except asyncio.CancelledError:
            raise
        except (TimedOut, NetworkError, OSError, TimeoutError) as exc:
            logger.warning(
                "Telegram bot connect attempt %s failed (%s). Retrying in %.0fs…",
                attempt,
                exc,
                delay,
            )
            if attempt == 1:
                print(
                    f"Telegram API not reachable yet ({exc}). "
                    "Retrying in background — balance bot will start when online."
                )
            await _safe_shutdown_bot()
        except Exception as exc:
            logger.exception(
                "Telegram bot connect attempt %s failed unexpectedly. Retrying in %.0fs…",
                attempt,
                delay,
            )
            if attempt == 1:
                print(
                    f"Telegram bot error ({type(exc).__name__}: {exc}). "
                    "Retrying in background…"
                )
            await _safe_shutdown_bot()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            return
        except asyncio.TimeoutError:
            delay = min(max_delay, delay * 1.6)


def _resolve_proxy() -> str | None:
    """Prefer explicit setting, then standard proxy environment variables."""
    configured = (settings.TELEGRAM_PROXY_URL or "").strip()
    if configured:
        return configured
    for key in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "https_proxy",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


async def start_bot() -> None:
    """Start the Telegram bot without blocking FastAPI lifespan.

    The bot is always intended to run when a token is present. Network blocks
    are handled with background retries — we do not permanently disable it.
    """
    global _bot_task, _stop_event

    if not settings.TELEGRAM_BOT_ENABLED:
        logger.warning(
            "TELEGRAM_BOT_ENABLED=false — set true to run balance/wallet bot"
        )
        print(
            "WARNING: TELEGRAM_BOT_ENABLED=false. "
            "Set TELEGRAM_BOT_ENABLED=true in backend/.env and restart."
        )
        return

    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is empty — cannot start Telegram bot")
        print("WARNING: TELEGRAM_BOT_TOKEN is empty — bot not started")
        return

    proxy = _resolve_proxy()
    if proxy:
        logger.info("Telegram bot will use configured proxy")

    _stop_event = asyncio.Event()
    _bot_task = asyncio.create_task(
        _bot_supervisor(_stop_event, proxy),
        name="telegram-bot-supervisor",
    )
    print("Telegram bot starting in background…")


async def stop_bot() -> None:
    global bot_application, _bot_task, _stop_event

    if _stop_event is not None:
        _stop_event.set()

    if _bot_task is not None:
        try:
            await asyncio.wait_for(_bot_task, timeout=15)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _bot_task.cancel()
            try:
                await _bot_task
            except asyncio.CancelledError:
                pass
        _bot_task = None

    _stop_event = None
    await _safe_shutdown_bot()
    logger.info("Telegram bot stopped")
    print("Telegram bot stopped")
