from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.router import api_router
from contextlib import asynccontextmanager

from app.bot.bot_runner import (
    start_bot,
    stop_bot,
)

from app.bingo import game_loop, redis_store, service
from app.bingo.manager import manager as bingo_manager
from app.bingo.pubsub import PubSubListener
from app.bingo.ws import router as bingo_ws_router
from app.dama.ws import router as dama_ws_router
from app.dama.manager import CHANNEL as DAMA_CHANNEL
from app.dama.manager import dispatch_fanout_event as dama_dispatch
from app.dama.manager import hub as dama_hub
from app.aviator.ws import router as aviator_ws_router
from app.aviator.manager import CHANNEL as AVIATOR_CHANNEL
from app.aviator.manager import dispatch_fanout_event as aviator_dispatch
from app.aviator.manager import hub as aviator_hub
from app.aviator.game_loop import ensure_game_loop, stop_game_loop as stop_aviator_loop
from app.lotto.game_loop import (
    ensure_game_loop as ensure_lotto_loop,
    stop_game_loop as stop_lotto_loop,
)
from app.lotto.manager import CHANNEL as LOTTO_CHANNEL
from app.lotto.manager import dispatch_fanout_event as lotto_dispatch
from app.lotto.manager import hub as lotto_hub
from app.lotto.ws import router as lotto_ws_router
from app.core.redis_fanout import ChannelFanout

bingo_pubsub_listener = PubSubListener(service.dispatch_pubsub_event)
aviator_fanout = ChannelFanout(AVIATOR_CHANNEL, aviator_dispatch)
dama_fanout = ChannelFanout(DAMA_CHANNEL, dama_dispatch)
lotto_fanout = ChannelFanout(LOTTO_CHANNEL, lotto_dispatch)


@asynccontextmanager
async def lifespan(app: FastAPI):

    # startup
    await start_bot()

    bingo_manager.bind_pubsub(bingo_pubsub_listener)
    bingo_manager.bind_dispatch(service.dispatch_pubsub_event)
    await bingo_pubsub_listener.start()

    aviator_hub.bind_fanout(aviator_fanout)
    aviator_hub.bind_dispatch(aviator_dispatch)
    await aviator_fanout.start()

    dama_hub.bind_fanout(dama_fanout)
    dama_hub.bind_dispatch(dama_dispatch)
    await dama_fanout.start()

    lotto_hub.bind_fanout(lotto_fanout)
    lotto_hub.bind_dispatch(lotto_dispatch)
    await lotto_fanout.start()

    ensure_game_loop()
    ensure_lotto_loop()

    if settings.BINGO_BOT_ENABLED:
        try:
            from app.bingo import house_bot

            await house_bot.ensure_bot_user_async()
        except Exception:
            # Bot identity is best-effort at boot; ticks will retry.
            pass

    yield

    # shutdown
    await stop_bot()

    await stop_aviator_loop()
    await stop_lotto_loop()
    await game_loop.stop_all()
    await bingo_pubsub_listener.stop()
    await aviator_fanout.stop()
    await dama_fanout.stop()
    await lotto_fanout.stop()
    await redis_store.close_redis()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


app.include_router(api_router)
app.include_router(bingo_ws_router)
app.include_router(dama_ws_router)
app.include_router(aviator_ws_router)
app.include_router(lotto_ws_router)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
FRONTEND_AUDIO = FRONTEND_DIST / "audios"

if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

# Audio must be mounted before the SPA fallback. Without this route,
# ``/audios/16.mp3`` was answered with index.html by the catch-all handler.
# Starlette's StaticFiles also handles byte-range requests correctly, so
# browsers receive a real ``audio/mpeg`` 206 response while streaming.
if FRONTEND_AUDIO.exists():
    app.mount(
        "/audios",
        StaticFiles(directory=FRONTEND_AUDIO),
        name="audios",
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/{path:path}")
async def frontend(path: str):
    index = FRONTEND_DIST / "index.html"
    requested_file = (FRONTEND_DIST / path).resolve()

    # Serve other Vite public files (favicon, manifest, etc.) directly while
    # preventing path traversal outside the built frontend directory.
    if (
        requested_file.is_relative_to(FRONTEND_DIST.resolve())
        and requested_file.is_file()
    ):
        return FileResponse(requested_file)

    if index.exists():
        return FileResponse(index)

    return {"message": "Frontend not built. Run npm run build."}
