from fastapi import APIRouter, Request
import httpx
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.core.security import create_access_token
from app.routes.telegram_auth import verify_telegram

router = APIRouter(prefix="/telegram", tags=["Telegram"])

BOT_TOKEN = "8045248665:AAFPsHgXWQAmqx-NskW4rULWUQu1qRVq_SQ"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def send_message(chat_id: int, text: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)


def register_or_get_user(db: Session, telegram_id: int, username: str = None, first_name: str = None):
    """
    Register new Telegram user or fetch existing one
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            telegram_username=username,
            telegram_first_name=first_name,
            balance=0.0,
            is_active=True,
            is_admin=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip().lower()
    init_data = message.get("web_app_data", {}).get("data")  # WebApp init_data
    db: Session = SessionLocal()

    try:
        user = None

        # --- Telegram WebApp login (init_data) ---
        if init_data:
            valid, tg_data = verify_telegram(init_data)
            if not valid:
                await send_message(chat_id, "❌ Telegram verification failed.")
                return {"ok": True}

            telegram_id = int(tg_data["id"])
            username = tg_data.get("username")
            first_name = tg_data.get("first_name")

            user = register_or_get_user(db, telegram_id, username, first_name)
            token = create_access_token({"sub": str(user.id)})

            await send_message(
                chat_id,
                f"🎉 Welcome, {first_name or 'Player'}!\nYour Bingo session is ready.",
                reply_markup={
                    "keyboard": [
                        [
                            {
                                "text": "▶️ Play Bingo",
                                "web_app": {"url": f"https://yourdomain/web?token={token}"}
                            }
                        ]
                    ],
                    "resize_keyboard": True
                }
            )
            return {"ok": True}

        # --- Commands handling ---
        from_user = message.get("from", {})
        telegram_id = from_user.get("id")
        username = from_user.get("username")
        first_name = from_user.get("first_name")

        if telegram_id:
            user = register_or_get_user(db, telegram_id, username, first_name)

        # Command mapping
        if text == "/hello":  # new start/welcome command
            await send_message(
                chat_id,
                f"👋 Hello, {first_name or 'Player'}! Use /play to start Bingo.",
            )

        elif text == "/play":
            if not user:
                await send_message(chat_id, "❌ User not found, register first using /register")
                return {"ok": True}

            token = create_access_token({"sub": str(user.id)})

            # Telegram web_app keyboard
            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "▶️ Play Bingo",
                            "web_app": {"url": f"https://coraline-fabaceous-ungutturally.ngrok-free.dev/web?token={token}"}
                        }
                    ]
                ]
            }

            await send_message(
                chat_id,
                "Click below to open Bingo Web App ⬇️",
                reply_markup=reply_markup
            )

        elif text == "/register":
            if user.email or user.telegram_id:
                await send_message(chat_id, "✅ You are already registered!")
            else:
                # Just in case, create new user
                user = register_or_get_user(db, telegram_id, username, first_name)
                await send_message(chat_id, "🎉 Registration successful!")

        elif text == "/balance":
            await send_message(
                chat_id,
                f"💰 Your balance is: ${user.balance:.2f}"
            )

        elif text == "/support":
            await send_message(
                chat_id,
                "📞 Contact support at support@example.com"
            )

        elif text == "/invite":
            await send_message(
                chat_id,
                "📢 Invite your friends and earn rewards!"
            )

        elif text == "/instruction":
            await send_message(
                chat_id,
                "📖 Game Instructions: Mark numbers on your Bingo board and complete a line!"
            )

        else:
            await send_message(chat_id, "❓ Unknown command. Try /hello for help.")

    finally:
        db.close()

    return {"ok": True}
