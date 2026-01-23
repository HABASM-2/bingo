from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import Base, engine
from app.routes import auth, bingo, admin
from app.models import user
from app.database_init import ensure_database
from app.routes.telegram_bot import router as telegram_router
import os

# --- ensure database exists ---
ensure_database()

app = FastAPI(title="Bingo API")

# --- Include Telegram bot router ---
app.include_router(telegram_router)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Create tables ---
Base.metadata.create_all(bind=engine)

# --- Include other routes ---
app.include_router(bingo.router)
app.include_router(auth.router)
app.include_router(admin.router)

# --- Serve React frontend from dist ---
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))

if os.path.exists(FRONTEND_DIST):
    # 1️⃣ Mount entire dist folder to serve JS/CSS/assets
    app.mount("/web", StaticFiles(directory=FRONTEND_DIST, html=True), name="web")

    # 2️⃣ Catch-all for SPA routing (handles /web?token=... or /web/some/path)
    @app.get("/web/{full_path:path}", include_in_schema=False)
    async def catch_all(full_path: str = ""):
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    # Optional: /web root
    @app.get("/web", include_in_schema=False)
    async def serve_web_root():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
else:
    print(f"React build not found at {FRONTEND_DIST}")

# --- Root route ---
@app.get("/")
def root():
    return {"message": "Bingo API is running 🚀"}
