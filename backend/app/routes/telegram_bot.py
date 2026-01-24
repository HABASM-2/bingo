from fastapi import APIRouter, HTTPException, Request
import httpx
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.models.transaction import Transaction, WithdrawStatus
from app.core.security import create_access_token
from app.routes.telegram_auth import verify_telegram
from decimal import Decimal, InvalidOperation

router = APIRouter(prefix="/telegram", tags=["Telegram"])

BOT_TOKEN = "8045248665:AAFPsHgXWQAmqx-NskW4rULWUQu1qRVq_SQ"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Track users in withdrawal flow
withdraw_state = {}  # {telegram_id: {"status": ..., "amount": ..., "method": ...}}

user_state = {}  # {telegram_id: {"status": ..., "stake": ...}}


async def send_message(chat_id: int, text: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)


def register_or_get_user(db: Session, telegram_id: int, username: str = None, first_name: str = None):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            telegram_username=username,
            telegram_first_name=first_name,
            balance=Decimal("0.00"),
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
    db: Session = SessionLocal()

    try:
        message = data.get("message")
        callback_query = data.get("callback_query")

        # --- Determine chat_id and telegram_id ---
        if callback_query:
            from_user = callback_query.get("from", {})
            chat_id = callback_query["message"]["chat"]["id"]
            telegram_id = from_user.get("id")
            callback_data = callback_query.get("data")
        elif message:
            from_user = message.get("from", {})
            chat_id = message["chat"]["id"]
            telegram_id = from_user.get("id")
            callback_data = None
        else:
            return {"ok": True}

        username = from_user.get("username")
        first_name = from_user.get("first_name")

        # --- Telegram WebApp login ---
        init_data = message.get("web_app_data", {}).get("data") if message else None
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
                            {"text": "▶️ Play Bingo", "web_app": {"url": f"https://yourdomain/web?token={token}"}}
                        ]
                    ],
                    "resize_keyboard": True
                }
            )
            return {"ok": True}

        # --- Ensure user exists ---
        user = register_or_get_user(db, telegram_id, username, first_name)
        state = withdraw_state.get(telegram_id)
        text = (message.get("text") or "").strip() if message else ""

        # --- Handle callback buttons first ---
        if callback_data and state:
            # Method selection
            if callback_data.startswith("method_") and state.get("status") == "awaiting_method":
                method = callback_data.split("_")[1].capitalize()
                state["method"] = method
                state["status"] = "awaiting_account"
                if method == "Telebirr":
                    await send_message(chat_id, "📱 Enter your phone number for Telebirr:")
                else:
                    await send_message(chat_id, f"🏦 Enter your account number for {method}:")
                return {"ok": True}

        # Cancel pending withdrawal
        # Handle callback buttons first
        if callback_data:
            # --- Withdrawal flow ---
            state_withdraw = withdraw_state.get(telegram_id)
            if state_withdraw:
                # Method selection
                if callback_data.startswith("method_") and state_withdraw.get("status") == "awaiting_method":
                    method = callback_data.split("_")[1].capitalize()
                    state_withdraw["method"] = method
                    state_withdraw["status"] = "awaiting_account"
                    if method == "Telebirr":
                        await send_message(chat_id, "📱 Enter your phone number for Telebirr:")
                    else:
                        await send_message(chat_id, f"🏦 Enter your account number for {method}:")
                    return {"ok": True}

            # Cancel pending withdrawal
            if callback_data == "withdraw_cancel":
                pending_tx = db.query(Transaction).filter(
                    Transaction.user_id == user.id,
                    Transaction.type == "withdraw",
                    Transaction.withdraw_status == WithdrawStatus.PENDING
                ).first()
                if pending_tx:
                    user.balance += pending_tx.amount  # refund
                    pending_tx.withdraw_status = WithdrawStatus.CANCELLED
                    db.commit()
                    withdraw_state.pop(telegram_id, None)
                    await send_message(chat_id, f"❌ Pending withdrawal of ${pending_tx.amount:.2f} cancelled and refunded.")
                else:
                    await send_message(chat_id, "❌ No pending withdrawal to cancel.")
                return {"ok": True}

            # --- Bingo stake selection flow ---
            state_play = user_state.get(telegram_id)
            if state_play and callback_data.startswith("stake_") and state_play.get("status") == "awaiting_stake":
                stake = int(callback_data.split("_")[1])
                token = create_access_token({"sub": str(user.id)})
                url = f"https://coraline-fabaceous-ungutturally.ngrok-free.dev/web?token={token}&stake={stake}"

                await send_message(chat_id, f"▶️ Your Bingo session for ${stake} is ready!", reply_markup={
                    "inline_keyboard": [[{"text": f"Play Bingo ${stake}", "web_app": {"url": url}}]]
                }) 

                user_state.pop(telegram_id)  # clear state
                return {"ok": True}

        # --- Multi-step withdrawal ---
        if state:
            status = state.get("status")

            if status == "awaiting_amount" and text:
                try:
                    amount = Decimal(text)
                except InvalidOperation:
                    await send_message(chat_id, "❌ Please enter a valid number (example: 25)")
                    return {"ok": True}

                if amount > user.balance:
                    await send_message(chat_id, f"❌ Insufficient balance. Your balance: ${user.balance:.2f}")
                    return {"ok": True}

                state["amount"] = amount
                state["status"] = "awaiting_method"
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "Telebirr", "callback_data": "method_telebirr"},
                         {"text": "CBE", "callback_data": "method_cbe"},
                         {"text": "Abyssinia", "callback_data": "method_abyssinia"}]
                    ]
                }
                await send_message(chat_id, "💳 Select withdrawal method:", reply_markup=reply_markup)
                return {"ok": True}

            elif status == "awaiting_account" and text:
                account_input = text.strip()
                method = state.get("method")
                try:
                    tx = Transaction(
                        user_id=user.id,
                        type="withdraw",
                        amount=state["amount"],
                        stake_amount=Decimal("0.00"),
                        reason="Telegram withdrawal request",
                        withdraw_status=WithdrawStatus.PENDING,
                        bank=method,
                        account_number=account_input
                    )
                    user.balance -= state["amount"]
                    db.add(tx)
                    db.commit()
                    withdraw_state.pop(telegram_id, None)
                    await send_message(chat_id, f"✅ Withdrawal request of ${tx.amount:.2f} via {method} submitted.\nStatus: pending")
                except Exception as e:
                    await send_message(chat_id, f"❌ Error creating withdrawal: {str(e)}")
                    withdraw_state.pop(telegram_id, None)
                return {"ok": True}

        # --- Standard text commands ---
        if text.lower() == "/hello":
            await send_message(chat_id, f"👋 Hello, {first_name or 'Player'}! Use /play to start Bingo.")
        elif text.lower() == "/play":
            # Ask user to select a stake room
            user_state[telegram_id] = {"status": "awaiting_stake"}
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "$10", "callback_data": "stake_10"},
                    {"text": "$20", "callback_data": "stake_20"},
                    {"text": "$50", "callback_data": "stake_50"}]
                ]
            }
            await send_message(chat_id, "🎯 Select your Bingo stake:", reply_markup=reply_markup)
        elif text.lower() == "/register":
            await send_message(chat_id, "✅ You are already registered!")
        elif text.lower() == "/balance":
            await send_message(chat_id, f"💰 Your balance is: ${user.balance:.2f}")
        elif text.lower() == "/support":
            await send_message(chat_id, "📞 Contact support at support@example.com")
        elif text.lower() == "/invite":
            await send_message(chat_id, "📢 Invite your friends and earn rewards!")
        elif text.lower() == "/instruction":
            await send_message(chat_id, "📖 Game Instructions: Mark numbers on your Bingo board and complete a line!")

        elif text.lower() == "/withdraw":
            # Check for pending withdrawal
            pending_tx = db.query(Transaction).filter(
                Transaction.user_id == user.id,
                Transaction.type == "withdraw",
                Transaction.withdraw_status == WithdrawStatus.PENDING
            ).first()
            if pending_tx:
                reply_markup = {"inline_keyboard": [[{"text": "Cancel Pending Withdrawal ❌", "callback_data": "withdraw_cancel"}]]}
                await send_message(chat_id, f"❌ You already have a pending withdrawal of ${pending_tx.amount:.2f}.", reply_markup=reply_markup)
                return {"ok": True}

            withdraw_state[telegram_id] = {"status": "awaiting_amount"}
            await send_message(chat_id, "💸 Enter the amount you want to withdraw:")

        else:
            await send_message(chat_id, "❓ Unknown command. Try /hello for help.")

    finally:
        db.close()

    return {"ok": True}
