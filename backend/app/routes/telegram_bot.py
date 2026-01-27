from fastapi import APIRouter, HTTPException, Request
import httpx
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.models.transaction import Transaction, WithdrawStatus
from app.core.security import create_access_token
from app.routes.telegram_auth import verify_telegram
from decimal import Decimal, InvalidOperation
from app.models.deposit import IncomingDeposit
from app.routes.sms_webhook import parse_sms

router = APIRouter(prefix="/telegram", tags=["Telegram"])

BOT_TOKEN = "8045248665:AAFPsHgXWQAmqx-NskW4rULWUQu1qRVq_SQ"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Track users in withdrawal flow
withdraw_state = {}  # {telegram_id: {"status": ..., "amount": ..., "method": ...}}

user_state = {}  # {telegram_id: {"status": ..., "stake": ...}}

# Track transfer states
transfer_state = {}  # {telegram_id: {"status": ..., "recipient": ..., "amount": ...}}
deposit_state = {}  # {telegram_id: {"status": "awaiting_txid"}}

def get_command_keyboard():
    return {
        "keyboard": [
            [{"text": "▶️ Play Bingo"}],
            [{"text": "💳 Deposit"}, {"text": "💰 My Balance"}, {"text": "💸 Withdraw"}, {"text": "🔄 Transfer"}],
            [{"text": "📢 Invite Friends"}, {"text": "📞 Support"}, {"text": "📖 How to Play"}]
        ],
        "resize_keyboard": True
    }
    
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

        # --- Check if user came via referral ---
        if message and "text" in message:
            start_param = message["text"].split()
        else:
            start_param = []
        referrer_id = None
        if len(start_param) > 1:
            try:
                referrer_id = int(start_param[1])
            except:
                referrer_id = None

        # Check if user already exists
        user_exists = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user_exists:
            # --- Register the new user ---
            user = register_or_get_user(db, telegram_id, username, first_name)

            # --- Credit 10 Birr to referrer if applicable ---
            if referrer_id and referrer_id != telegram_id:
                referrer = db.query(User).filter(User.telegram_id == referrer_id).first()
                if referrer:
                    referrer.balance += Decimal("10.00")  # 10 Birr bonus
                    tx = Transaction(
                        user_id=referrer.id,
                        type="deposit",
                        amount=Decimal("10.00"),
                        stake_amount=Decimal("0.00"),
                        reason=f"Invite bonus from @{username or first_name}"
                    )
                    db.add(tx)
                    db.commit()
                    await send_message(referrer.telegram_id, f"🎉 You received 10 Birr bonus! Your friend {first_name or 'Player'} joined using your invite link.")
        else:
            # Existing user - no referral bonus
            user = user_exists

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
                if telegram_id in withdraw_state:
                    withdraw_state.pop(telegram_id)
                    await send_message(chat_id, "❌ Withdrawal cancelled. You can now enter other commands.", reply_markup=get_command_keyboard())
                return {"ok": True} 
            if callback_data == "transfer_cancel":
                if telegram_id in transfer_state:
                    transfer_state.pop(telegram_id)
                    await send_message(chat_id, "❌ Transfer cancelled. You can now enter other commands.", reply_markup=get_command_keyboard())
                return {"ok": True}

            if callback_data == "deposit_cancel":
                if telegram_id in deposit_state:
                    deposit_state.pop(telegram_id)
                    await send_message(chat_id,
                                    "❌ Deposit cancelled. You can now enter other commands.",
                                    reply_markup=get_command_keyboard())
                return {"ok": True}
                
        # --- Multi-step withdrawal ---
        if state:
            status = state.get("status")

            # Add Cancel button to every step
            cancel_markup = {
                "inline_keyboard": [
                    [{"text": "❌ Cancel Withdrawal", "callback_data": "withdraw_cancel"}]
                ]
            }

            if status == "awaiting_amount" and text:
                try:
                    amount = Decimal(text)
                except InvalidOperation:
                    await send_message(chat_id, "❌ Please enter a valid number (example: 25)", reply_markup=cancel_markup)
                    return {"ok": True}

                if amount > user.balance:
                    await send_message(chat_id, f"❌ Insufficient balance. Your balance: ${user.balance:.2f}", reply_markup=cancel_markup)
                    return {"ok": True}

                state["amount"] = amount
                state["status"] = "awaiting_method"
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "Telebirr", "callback_data": "method_telebirr"},
                        {"text": "CBE", "callback_data": "method_cbe"},
                        {"text": "Abyssinia", "callback_data": "method_abyssinia"}],
                        [{"text": "❌ Cancel Withdrawal", "callback_data": "withdraw_cancel"}]  # cancel option
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

        # --- Handle multi-step transfer ---
        state_transfer = transfer_state.get(telegram_id)
        if state_transfer:
            status = state_transfer.get("status")

            cancel_markup = {
                "inline_keyboard": [
                    [{"text": "❌ Cancel Transfer", "callback_data": "transfer_cancel"}]
                ]
            }

            # Step 1: Get recipient username
            if status == "awaiting_username" and text:
                recipient_username = text.strip().lstrip("@")
                recipient = db.query(User).filter(User.telegram_username == recipient_username).first()
                if not recipient:
                    await send_message(chat_id, f"❌ User @{recipient_username} not found. Enter a valid username:", reply_markup=cancel_markup)
                    return {"ok": True}
                if recipient.id == user.id:
                    await send_message(chat_id, "❌ You cannot transfer money to yourself.", reply_markup=cancel_markup)
                    return {"ok": True}

                state_transfer["recipient_username"] = recipient_username
                state_transfer["recipient_id"] = recipient.id
                state_transfer["status"] = "awaiting_amount"
                await send_message(chat_id, f"💸 Enter the amount you want to transfer to @{recipient_username}:", reply_markup=cancel_markup)
                return {"ok": True}

            # Step 2: Get amount
            elif status == "awaiting_amount" and text:
                try:
                    amount = Decimal(text.strip())
                except InvalidOperation:
                    await send_message(chat_id, "❌ Please enter a valid number (example: 25)", reply_markup=cancel_markup)
                    return {"ok": True}

                if amount <= 0:
                    await send_message(chat_id, "❌ Amount must be greater than 0.", reply_markup=cancel_markup)
                    return {"ok": True}

                if amount > user.balance:
                    await send_message(chat_id, f"❌ Insufficient balance. Your balance: ${user.balance:.2f}", reply_markup=cancel_markup)
                    return {"ok": True}

                recipient_id = state_transfer["recipient_id"]
                recipient_username = state_transfer["recipient_username"]
                recipient = db.query(User).filter(User.id == recipient_id).first()
                if not recipient:
                    await send_message(chat_id, f"❌ Recipient not found. Aborting transfer.", reply_markup=get_command_keyboard())
                    transfer_state.pop(telegram_id, None)
                    return {"ok": True}

                # Perform transfer
                user.balance -= amount
                recipient.balance += amount

                # Record transactions
                tx_sender = Transaction(
                    user_id=user.id,
                    type="withdraw",
                    amount=amount,
                    stake_amount=Decimal("0.00"),
                    reason=f"Transfer to @{recipient.telegram_username}",
                    withdraw_status=None
                )
                tx_recipient = Transaction(
                    user_id=recipient.id,
                    type="deposit",
                    amount=amount,
                    stake_amount=Decimal("0.00"),
                    reason=f"Received transfer from @{user.telegram_username or user.display_name}"
                )
                db.add_all([tx_sender, tx_recipient])
                db.commit()

                # Notify both users
                await send_message(chat_id, f"✅ You transferred ${amount:.2f} to @{recipient.telegram_username}. New balance: ${user.balance:.2f}")
                if recipient.telegram_id:
                    try:
                        await send_message(
                            recipient.telegram_id,
                            f"💰 You received ${amount:.2f} from @{user.telegram_username or user.display_name}. New balance: ${recipient.balance:.2f}"
                        )
                    except Exception as e:
                        print("Failed to notify recipient:", e)

                transfer_state.pop(telegram_id, None)
                return {"ok": True}
            
            state = deposit_state.get(telegram_id)
            if state and state.get("status") == "awaiting_txid" and text:
                txid = text.strip()

                dep = db.query(IncomingDeposit).filter_by(
                    transaction_id=txid,
                    is_matched=False
                ).first()

                if not dep:
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "❌ Cancel Deposit", "callback_data": "deposit_cancel"}]
                        ]
                    }
                    await send_message(chat_id,
                        "❌ Transaction not found or already used. "
                        "Please try again or cancel the deposit.",
                        reply_markup=reply_markup
                    )
                    return {"ok": True}

                # CREDIT USER
                user.balance += dep.amount
                dep.is_matched = True
                dep.matched_user_id = user.id

                tx = Transaction(
                    user_id=user.id,
                    type="deposit",
                    amount=dep.amount,
                    stake_amount=0,
                    reason=f"Deposit via {dep.provider}"
                )
                db.add(tx)
                db.commit()

                deposit_state.pop(telegram_id, None)  # ✅ clear state after success
                await send_message(chat_id, f"✅ Deposit of ETB {dep.amount} confirmed and added to your balance!")
                return {"ok": True}
    
        # --- Standard text commands ---
        if text.lower() == "/hello":
            await send_message(chat_id, f"👋 Hello, {first_name or 'Player'}! 📋 Choose a command:", reply_markup=get_command_keyboard())
        elif text in ["▶️ Play Bingo", "/play"]:
            # Directly generate token and send Bingo URL
            token = create_access_token({"sub": str(user.id)})
            url = f"https://coraline-fabaceous-ungutturally.ngrok-free.dev/web?token={token}"  # <-- adjust your domain

            # Send WebApp button
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "Play Bingo ▶️", "web_app": {"url": url}}]
                ]
            }

            await send_message(chat_id, "▶️ Click below to play Bingo!", reply_markup=reply_markup)
        elif text.lower() == "/register":
            await send_message(chat_id, "✅ You are already registered!")
        elif text in ["💰 My Balance", "/balance"]:
            await send_message(chat_id, f"💰 Your balance is: ${user.balance:.2f}")
        elif text in ["📞 Support", "/support"]:
            support_text = (
                "📞 Contact our support team:\n\n"
                "Ethiopia Phone Numbers:\n"
                "• +251 946 236 923\n"
                "• +251 944 322 100\n\n"
                "You can also email us at 2gethas@gmail.com\n"
                "We are available 24/7 to help you!"
            )
            await send_message(chat_id, support_text)
        elif text in ["📢 Invite Friends", "/invite"]:
            # Generate a unique invite link with the user's Telegram ID
            invite_link = f"https://t.me/YourBotUsername?start={telegram_id}"

            invite_text = (
                "📢 Invite your friends and earn rewards!\n\n"
                "✅ Share your unique link below. "
                "Each friend that joins gives you a 10 Birr bonus!\n\n"
                "Click below to share:"
            )

            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Share Invite Link 🔗",
                            "url": invite_link
                        }
                    ]
                ]
            }

            # Send message with inline button
            await send_message(chat_id, invite_text, reply_markup=reply_markup)
        elif text in ["📖 How to Play", "/instruction"]:
            await send_message(chat_id, "📖 Game Instructions: Mark numbers on your Bingo board and complete a line!")

        elif text in ["💸 Withdraw", "/withdraw"]:
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
        elif text in ["🔄 Transfer", "/transfer"]:
            transfer_state[telegram_id] = {"status": "awaiting_username"}
            await send_message(chat_id, "👤 Enter the Telegram username of the friend you want to transfer money to (without @):")
            return {"ok": True}
        elif text in ["💳 Deposit", "/deposit"]:
            # Start deposit process
            deposit_state[telegram_id] = {"status": "awaiting_txid"}

            accounts_text = (
                "💰 To deposit, please use one of the following accounts:\n\n"
                "📱 Telebirr (Recommended for speed): 0912 345 678\n"
                "🏦 CBE Account: 1234567890\n"
                "🏦 Abyssinia Account: 0987654321\n\n"
                "➡️ After sending the money, reply here with your **Transaction ID** (only once)."
            )

            # Include Cancel button when starting
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "❌ Cancel Deposit", "callback_data": "deposit_cancel"}]
                ]
            }

            await send_message(chat_id, accounts_text, reply_markup=reply_markup)
    
        elif text.startswith("Dear"):
            parsed = parse_sms(text)
            if not parsed:
                await send_message(chat_id, "❌ Could not read payment SMS.")
                return {"ok": True}

            dep = db.query(IncomingDeposit).filter_by(
                transaction_id=parsed["txid"],
                amount=parsed["amount"],
                is_matched=False
            ).first()

            if not dep:
                await send_message(chat_id, "❌ Payment not found or already used.")
                return {"ok": True}

            # CREDIT USER
            user.balance += dep.amount
            dep.is_matched = True
            dep.matched_user_id = user.id

            tx = Transaction(
                user_id=user.id,
                type="deposit",
                amount=dep.amount,
                stake_amount=0,
                reason=f"Auto deposit via {dep.provider}"
            )
            db.add(tx)
            db.commit()

            await send_message(chat_id, f"✅ Deposit of ETB {dep.amount} confirmed and added to your balance!")
        else:
            await send_message(chat_id, "❓ Unknown command. Try /hello for help.")

    finally:
        db.close()

    return {"ok": True}
