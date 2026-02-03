import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend folder
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/app -> backend
load_dotenv(BASE_DIR / ".env")

class Settings:
    # --- SECURITY ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_IN_PRODUCTION")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # --- TELEGRAM ---
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    TELEGRAM_API: str = f"https://api.telegram.org/bot{BOT_TOKEN}"

    # --- WEBAPP ---
    WEBAPP_BASE_URL: str = os.getenv("WEBAPP_BASE_URL")  # your bingo web url

settings = Settings()
