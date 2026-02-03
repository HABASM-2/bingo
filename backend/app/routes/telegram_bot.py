from fastapi import APIRouter, Request
import httpx
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.models.transaction import Transaction, WithdrawStatus
from app.core.security import create_access_token
from app.routes.telegram_auth import verify_telegram
from decimal import Decimal, InvalidOperation
from app.models.deposit import IncomingDeposit
from sqlalchemy import func
from app.core.config import settings

# LANG dictionary as in your original code (en + am)...
LANG = {
    "en": {
        # --- GENERAL ---
        "hello": "👋 Hello, {name}! 📋 Choose a command:",
        "unknown": "❓ Unknown command. Try /hello for help.",
        "language_updated": "✅ Language updated!",
        "choose_language": "🌐 Choose language:",
        "play_bingo": "🎮 Play Bingo",
        "deposit": "💳 Deposit",
        "balance_btn": "💰 My Balance",
        "withdraw_btn": "💸 Withdraw",
        "transfer_btn": "🔄 Transfer",
        "invite_btn": "📢 Invite Friends",
        "support_btn": "📞 Support",
        "instruction_btn": "📖 How to Play",
        "balance": "💰 Your balance is: ${balance:.2f}",
        "deposit_instruction": "💳 Send a screenshot of your payment.\nAfter admin confirmation, your balance will update.",
        "cancel_deposit": "❌ Cancel Deposit",
        "withdraw_enter_amount": "💸 Enter withdrawal amount:",
        "withdraw_method": "🏦 Choose withdrawal method:",
        "withdraw_success": "✅ Withdrawal request of ${amount:.2f} via {method} submitted.\nStatus: pending",
        "cancel_withdraw": "❌ Cancel Withdrawal",
        "pending_withdrawal": "❌ You already have a pending withdrawal of ${amount:.2f}.",
        "transfer_enter_username": "👤 Enter recipient username (example: @john):",
        "transfer_enter_amount_to": "💸 Enter amount to send to @{username}:",
        "transfer_success": "✅ Transfer successful!\nYou sent ${amount:.2f} to @{username}.",
        "cannot_self_transfer": "❌ You cannot transfer money to yourself.",
        "user_not_found": "❌ User @{username} not found.",
        "invite_text": "📢 Invite friends and earn rewards!\nShare your link:\n{link}",
        "invalid_number": "❌ Please enter a valid number (example: 25)",
        "amount_gt_zero": "❌ Amount must be greater than 0.",
        "insufficient_balance": "❌ Insufficient balance. Your balance: ${balance:.2f}",
        "support_text": "📞 Contact support: @YourSupportUsername",
        "instruction_text": "📖 How to Play Bingo:\n1. Deposit money\n2. Join a game\n3. Mark numbers\n4. Win rewards 🎉",
        # --- NEW ---
        "play_bingo_web": "▶️ Play Bingo",
        "click_play": "▶️ Click below to play Bingo!",
        "already_registered": "✅ You are already registered!",
        "withdraw_cancelled": "❌ Withdrawal cancelled. You can enter other commands.",
        "transfer_cancelled": "❌ Transfer cancelled.",
        "deposit_cancelled": "❌ Deposit cancelled.",
        "enter_account": "🏦 Enter your account number for {method}:",
        "enter_phone": "📱 Enter your phone number for Telebirr:",
        "select_withdraw_method": "💳 Select withdrawal method:",
        "enter_transfer_username": "👤 Enter the Telegram username (without @):",
        "transfer_received": "💰 You received ${amount:.2f} from @{username}.",
        "deposit_accounts": "💰 Send money to:\n📱 Telebirr: 0912345678\n🏦 CBE: 123456789\n🏦 Abyssinia: 987654321\n\nThen send TX ID here.",
        "deposit_confirmed": "✅ Deposit of ETB {amount} confirmed!",
        "payment_not_found": "❌ Payment not found or already used.",
        "cannot_read_sms": "❌ Could not read payment SMS.",
        "welcome_webapp": "🎉 Welcome {name}! Your Bingo session is ready.",
    },
    "am": {
        # --- GENERAL ---
        "hello": "👋 ሰላም {name}! 📋 አንድ ትእዛዝ ይምረጡ:",
        "unknown": "❓ ያልታወቀ ትእዛዝ። /hello ይሞክሩ",
        "language_updated": "✅ ቋንቋ ተቀይሯል!",
        "choose_language": "🌐 ቋንቋ ይምረጡ:",
        "play_bingo": "🎮 ቢንጎ ተጫወት",
        "deposit": "💳 ገንዘብ አስገባ",
        "balance_btn": "💰 ቀሪ ሂሳብ",
        "withdraw_btn": "💸 ገንዘብ ማውጣት",
        "transfer_btn": "🔄 ገንዘብ ማስተላለፍ",
        "invite_btn": "📢 ጓደኞችን ይጋብዙ",
        "support_btn": "📞 ድጋፍ",
        "instruction_btn": "📖 መመሪያ",
        "balance": "💰 ቀሪ ሂሳብዎ: ${balance:.2f}",
        "deposit_instruction": "💳 በሚፈልጉት ገንዘብ ማስገቢያ ካስገቡ በኋላ transaction id ይላኩ። ",
        "cancel_deposit": "❌ ገንዘብ ማስገባትዎን ያቋርጡ! ",
        "withdraw_enter_amount": "💸 የሚወጣ የገንዘብ መጠን ያስገቡ:",
        "withdraw_method": "🏦 የገንዘብ መውጫ መንገድ ይምረጡ:",
        "withdraw_success": "✅ ${amount:.2f} መውጫ በ {method} ተጠይቋል።\nሁኔታ: pending",
        "cancel_withdraw": "❌ ያቋርጡ!",
        "pending_withdrawal": "❌ ${amount:.2f} የሚወጣ ገንዘብ አለዎት",
        "transfer_enter_username": "🔄 የተቀባይ ዩዘርኔም (@ ሳይጠቀሙ) ያስገቡ (ምሳሌ: john):",
        "transfer_enter_amount_to": "💸 የሚላክ መጠን ያስገቡ @{username}:",
        "transfer_success": "✅ የተሳካ ማስተላለፍ!\n${amount:.2f} ወደ @{username} ተልኳል",
        "cannot_self_transfer": "❌ ለራስዎ መላክ አይቻልም",
        "user_not_found": "❌ @{username} አልተገኘም",
        "invite_text": "📢 ጓደኞችን ጋብዙ እና ሽልማት ያግኙ!\nይህን ሊንክ ያጋሩ:\n{link}",
        "invalid_number": "❌ ትክክለኛ ቁጥር ያስገቡ (ምሳሌ: 25)",
        "amount_gt_zero": "❌ መጠን ከ 0 በላይ መሆን አለበት",
        "insufficient_balance": "❌ ቀሪ ሂሳብ በቂ አይደለም። ያለው: ${balance:.2f}",
        "support_text": "📞 ድጋፍ: @YourSupportUsername",
        "instruction_text": "📖 ቢንጎ መመሪያ:\n1. ገንዘብ አስገባ\n2. ጨዋታ ግባ\n3. ቁጥሮች ምልክት አድርግ\n4. ሽልማት አሸንፍ 🎉",
        # --- NEW ---
        "play_bingo_web": "▶️ ቢንጎ ተጫወት",
        "click_play": "▶️ ቢንጎ ለመጫወት ይጫኑ",
        "already_registered": "✅ ተመዝግበዋል",
        "withdraw_cancelled": "❌ ገንዘብ ማውጣትን አቋርጠዋል",
        "transfer_cancelled": "❌ ማስተላለፍን  አቋርጠዋል",
        "deposit_cancelled": "❌ ገንዘብ ማስገባትዎን አቋርጠዋል",
        "enter_account": "🏦 የ{method} አካውንት ቁጥር ያስገቡ:",
        "enter_phone": "📱 የቴሌብር ስልክ ቁጥር ያስገቡ:",
        "select_withdraw_method": "💳 የማውጫ ዘዴ ይምረጡ:",
        "enter_transfer_username": "👤 የተቀባይ ዩዘርኔም ያስገቡ (ያለ @):",
        "transfer_received": "💰 ${amount:.2f} ከ @{username} ተቀብለዋል",
        "deposit_accounts": "💰 ገንዘብ ወደ:\n📱 Telebirr: 0912345678\n🏦 CBE: 123456789\n🏦 Abyssinia: 987654321\n\nከዚያ TX ID ይላኩ",
        "deposit_confirmed": "✅ ETB {amount} ተጨምሯል",
        "payment_not_found": "❌ ክፍያ አልተገኘም",
        "cannot_read_sms": "❌ SMS መክፈል አልተቻለም",
        "welcome_webapp": "🎉 እንኳን ደህና መጡ {name}! ቢንጎ ዝግጁ ነው",
    }
}

router = APIRouter(prefix="/telegram", tags=["Telegram"])

# --- States ---
withdraw_state = {}
transfer_state = {}
deposit_state = {}
user_lang = {}
DEFAULT_LANG = "en"

def t(telegram_id: int, key: str, **kwargs):
    lang_code = user_lang.get(telegram_id, DEFAULT_LANG)
    return LANG.get(lang_code, LANG["am"]).get(key, key).format(**kwargs)

def is_btn(telegram_id: int, key: str, text: str):
    """Check button text across all languages"""
    for lang in LANG.values():
        if key in lang and text == lang[key]:
            return True
    return False

def get_command_keyboard(telegram_id: int):
    return {
        "keyboard": [
            [{"text": t(telegram_id, "play_bingo")}],
            [
                {"text": t(telegram_id, "deposit")},
                {"text": t(telegram_id, "balance_btn")},
                {"text": t(telegram_id, "withdraw_btn")},
                {"text": t(telegram_id, "transfer_btn")}
            ],
            [
                {"text": t(telegram_id, "invite_btn")},
                {"text": t(telegram_id, "support_btn")},
                {"text": t(telegram_id, "instruction_btn")}
            ]
        ],
        "resize_keyboard": True
    }

async def send_message(chat_id: int, text: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        await client.post(f"{settings.TELEGRAM_API}/sendMessage", json=payload)

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
        user = register_or_get_user(db, telegram_id, username, first_name)
        text = (message.get("text") or "").strip() if message else ""

        # Ensure user language is initialized
        if telegram_id not in user_lang:
            user_lang[telegram_id] = DEFAULT_LANG

        # --- LANGUAGE CHANGE ---
        if callback_data and callback_data.startswith("lang_"):
            lang_code = callback_data.split("_")[1]
            user_lang[telegram_id] = lang_code
            await send_message(chat_id, t(telegram_id, "language_updated"), reply_markup=get_command_keyboard(telegram_id))
            return {"ok": True}

        # --- Handle cancel buttons ---
        if callback_data:
            if callback_data == "withdraw_cancel" and telegram_id in withdraw_state:
                withdraw_state.pop(telegram_id)
                await send_message(chat_id, t(telegram_id, "withdraw_cancelled"), reply_markup=get_command_keyboard(telegram_id))
                return {"ok": True}
            if callback_data == "transfer_cancel" and telegram_id in transfer_state:
                transfer_state.pop(telegram_id)
                await send_message(chat_id, t(telegram_id, "transfer_cancelled"), reply_markup=get_command_keyboard(telegram_id))
                return {"ok": True}
            if callback_data == "deposit_cancel" and telegram_id in deposit_state:
                deposit_state.pop(telegram_id)
                await send_message(chat_id, t(telegram_id, "deposit_cancelled"), reply_markup=get_command_keyboard(telegram_id))
                return {"ok": True}

            # Withdraw method selection
            state = withdraw_state.get(telegram_id)
            if callback_data and state and state.get("status") == "awaiting_method":
                method = callback_data.split("_")[1].capitalize()
                state["method"] = method
                state["status"] = "awaiting_account"
                prompt = t(telegram_id, "enter_phone") if method == "Telebirr" else t(telegram_id, "enter_account", method=method)
                await send_message(chat_id, prompt)
                return {"ok": True}

        # --- Multi-step withdrawal ---
        state = withdraw_state.get(telegram_id)
        if state:
            status = state.get("status")
            cancel_markup = {"inline_keyboard": [[{"text": t(telegram_id, 'cancel_withdraw'), "callback_data": "withdraw_cancel"}]]}
            if status == "awaiting_amount" and text:
                try:
                    amount = Decimal(text)
                except InvalidOperation:
                    await send_message(chat_id, t(telegram_id, "invalid_number"), reply_markup=cancel_markup)
                    return {"ok": True}
                if amount > user.balance:
                    await send_message(chat_id, t(telegram_id, "insufficient_balance", balance=user.balance), reply_markup=cancel_markup)
                    return {"ok": True}
                state["amount"] = amount
                state["status"] = "awaiting_method"
                reply_markup = {"inline_keyboard": [[
                    {"text": "Telebirr", "callback_data": "method_telebirr"},
                    {"text": "CBE", "callback_data": "method_cbe"},
                    {"text": "Abyssinia", "callback_data": "method_abyssinia"}
                ], [{"text": t(telegram_id, "cancel_withdraw"), "callback_data": "withdraw_cancel"}]]}
                await send_message(chat_id, t(telegram_id, "select_withdraw_method"), reply_markup=reply_markup)
                return {"ok": True}
            elif status == "awaiting_account" and text:
                account_input = text.strip()
                method = state.get("method")
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
                await send_message(chat_id, t(telegram_id, "withdraw_success", amount=tx.amount, method=method))
                return {"ok": True}

        # --- Multi-step transfer ---
        state_transfer = transfer_state.get(telegram_id)
        cancel_transfer_markup = {"inline_keyboard": [[{"text": t(telegram_id, 'cancel_transfer'), "callback_data": "transfer_cancel"}]]}
        if state_transfer:
            status = state_transfer.get("status")
            if status == "awaiting_username" and text:
                recipient_username = text.strip().lstrip("@")
                recipient = db.query(User).filter(
                    func.lower(User.telegram_username) == recipient_username.lower()
                ).first()
                if not recipient:
                    await send_message(chat_id, t(telegram_id, "user_not_found", username=recipient_username), reply_markup=cancel_transfer_markup)
                    return {"ok": True}
                if recipient.id == user.id:
                    await send_message(chat_id, t(telegram_id, "cannot_self_transfer"), reply_markup=cancel_transfer_markup)
                    return {"ok": True}
                state_transfer.update({"recipient_username": recipient_username, "recipient_id": recipient.id, "status": "awaiting_amount"})
                await send_message(chat_id, t(telegram_id, "transfer_enter_amount_to", username=recipient_username), reply_markup=cancel_transfer_markup)
                return {"ok": True}
            elif status == "awaiting_amount" and text:
                try:
                    amount = Decimal(text)
                except InvalidOperation:
                    await send_message(chat_id, t(telegram_id, "invalid_number"), reply_markup=cancel_transfer_markup)
                    return {"ok": True}
                if amount <= 0:
                    await send_message(chat_id, t(telegram_id, "amount_gt_zero"), reply_markup=cancel_transfer_markup)
                    return {"ok": True}
                if amount > user.balance:
                    await send_message(chat_id, t(telegram_id, "insufficient_balance", balance=user.balance), reply_markup=cancel_transfer_markup)
                    return {"ok": True}
                recipient_id = state_transfer["recipient_id"]
                recipient_username = state_transfer["recipient_username"]
                recipient = db.query(User).filter(User.id == recipient_id).first()
                user.balance -= amount
                recipient.balance += amount
                tx_sender = Transaction(user_id=user.id, type="withdraw", amount=amount, stake_amount=0, reason=f"Transfer to @{recipient_username}")
                tx_recipient = Transaction(user_id=recipient.id, type="deposit", amount=amount, stake_amount=0, reason=f"Received transfer from @{user.telegram_username or user.telegram_first_name or 'Player'}")
                db.add_all([tx_sender, tx_recipient])
                db.commit()
                await send_message(chat_id, t(telegram_id, "transfer_success", amount=amount, username=recipient_username))
                try:
                    await send_message(
                        recipient.telegram_id,
                        t(recipient.telegram_id, "transfer_received",
                        amount=amount,
                        username=user.telegram_username or user.telegram_first_name or "Player")
                    )
                except:
                    pass
                transfer_state.pop(telegram_id)
                return {"ok": True}

        # --- Multi-step deposit ---
        state_deposit = deposit_state.get(telegram_id)
        cancel_deposit_markup = {"inline_keyboard": [[{"text": t(telegram_id, "cancel_deposit"), "callback_data": "deposit_cancel"}]]}
        if state_deposit and state_deposit.get("status") == "awaiting_txid" and text:
            txid = text.strip()
            dep = db.query(IncomingDeposit).filter_by(transaction_id=txid, is_matched=False).first()
            if not dep:
                await send_message(chat_id, t(telegram_id, "payment_not_found"), reply_markup=cancel_deposit_markup)
                return {"ok": True}
            user.balance += dep.amount
            dep.is_matched = True
            dep.matched_user_id = user.id
            tx = Transaction(user_id=user.id, type="deposit", amount=dep.amount, stake_amount=0, reason=f"Deposit via {dep.provider}")
            db.add(tx)
            db.commit()
            deposit_state.pop(telegram_id)
            await send_message(chat_id, t(telegram_id, "deposit_confirmed", amount=dep.amount))
            return {"ok": True}

        # --- Standard text commands ---
        if text.lower() == "/hello":
            user_lang[telegram_id] = user_lang.get(telegram_id, DEFAULT_LANG)
            await send_message(
                chat_id,
                t(telegram_id, "hello", name=first_name or "Player"),
                reply_markup=get_command_keyboard(telegram_id)
            )
        elif text == "/play" or is_btn(telegram_id, "play_bingo", text):
            token = create_access_token({"sub": str(user.id)})
            url = f"{settings.WEBAPP_BASE_URL}/web?token={token}"
            reply_markup = {"inline_keyboard": [[{"text": t(telegram_id, "play_bingo_web"), "web_app": {"url": url}}]]}
            await send_message(chat_id, t(telegram_id, "click_play"), reply_markup=reply_markup)

        elif text == "/register":
            await send_message(chat_id, t(telegram_id, "already_registered"))

        elif text == "/balance" or is_btn(telegram_id, "balance_btn", text):
            await send_message(chat_id, t(telegram_id, "balance", balance=user.balance))

        elif text == "/support" or is_btn(telegram_id, "support_btn", text):
            await send_message(chat_id, t(telegram_id, "support_text"))

        elif text == "/instruction" or is_btn(telegram_id, "instruction_btn", text):
            await send_message(chat_id, t(telegram_id, "instruction_text"))

        elif text == "/invite" or is_btn(telegram_id, "invite_btn", text):
            invite_link = f"https://t.me/YourBotUsername?start={telegram_id}"
            await send_message(chat_id, t(telegram_id, "invite_text", link=invite_link))

        elif text == "/deposit" or is_btn(telegram_id, "deposit", text):
            deposit_state[telegram_id] = {"status": "awaiting_txid"}
            await send_message(chat_id, t(telegram_id, "deposit_accounts"))

        elif text == "/withdraw" or is_btn(telegram_id, "withdraw_btn", text):
            withdraw_state[telegram_id] = {"status": "awaiting_amount"}
            await send_message(chat_id, t(telegram_id, "withdraw_enter_amount"))

        elif text == "/transfer" or is_btn(telegram_id, "transfer_btn", text):
            transfer_state[telegram_id] = {"status": "awaiting_username"}
            await send_message(chat_id, t(telegram_id, "enter_transfer_username"))

        elif text in ["🌐 Language", "/language"]:
            reply_markup = {"inline_keyboard": [[
                {"text": "🇪🇹 አማርኛ", "callback_data": "lang_am"},
                {"text": "🇬🇧 English", "callback_data": "lang_en"}
            ]]}
            await send_message(chat_id, t(telegram_id, "choose_language"), reply_markup=reply_markup)

        else:
            await send_message(chat_id, t(telegram_id, "unknown"))

    finally:
        db.close()
    return {"ok": True}
