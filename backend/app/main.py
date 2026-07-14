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

bingo_pubsub_listener = PubSubListener(service.dispatch_pubsub_event)


@asynccontextmanager
async def lifespan(app: FastAPI):

    # startup
    await start_bot()

    bingo_manager.bind_pubsub(bingo_pubsub_listener)
    bingo_manager.bind_dispatch(service.dispatch_pubsub_event)
    await bingo_pubsub_listener.start()

    yield

    # shutdown
    await stop_bot()

    await game_loop.stop_all()
    await bingo_pubsub_listener.stop()
    await redis_store.close_redis()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


app.include_router(api_router)
app.include_router(bingo_ws_router)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/{path:path}")
async def frontend(path: str):
    index = FRONTEND_DIST / "index.html"

    if index.exists():
        return FileResponse(index)

    return {"message": "Frontend not built. Run npm run build."}