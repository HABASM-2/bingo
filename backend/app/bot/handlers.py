from datetime import datetime
from decimal import Decimal
from pathlib import Path

from telegram.ext import ContextTypes

from app.db.database import SessionLocal
from app.services.auth_service import AuthService
from app.models.wallet_transaction import Deposit
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from app.models.user import User
from app.core.config import settings
from app.services.sms_parser import SMSParser
from app.db.database import SessionLocal
from app.models.sms_transaction import SMSTransaction
from app.models.request_tr import TransferRequest, WithdrawRequest
from sqlalchemy.exc import SQLAlchemyError
import uuid

logo = Path("assets/logo.png")


HOME_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton(
            "🔙 Home",
            callback_data="home",
        )
    ]
])


DEPOSIT_METHODS = {
    "telebirr": {
        "title": "🟢 Telebirr Deposit",
        "account_name": "Telegram Games",
        "account_number": "0912345678",
        "button_callback": "deposit_paid",
    },
    "cbe": {
        "title": "🏦 CBE Deposit",
        "account_name": "Telegram Games",
        "account_number": "1000123456789",
        "button_callback": "deposit_paid",
    },
    "cbebirr": {
        "title": "📱 CBE Birr Deposit",
        "account_name": "Telegram Games",
        "account_number": "0911111111",
        "button_callback": "deposit_paid",
    },
    "boa": {
        "title": "🏛️ Bank of Abyssinia Deposit",
        "account_name": "Telegram Games",
        "account_number": "1234567890",
        "button_callback": "deposit_paid",
    },
}

def main_menu_keyboard():
    return [
        [
            InlineKeyboardButton(
                "🎮 Play",
                web_app=WebAppInfo(
                    url=settings.TELEGRAM_WEBAPP_URL
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Register",
                callback_data="register",
            ),
            InlineKeyboardButton(
                "💰 Check Balance",
                callback_data="balance",
            ),
        ],
        [
            InlineKeyboardButton(
                "💳 Deposit",
                callback_data="deposit",
            ),
            InlineKeyboardButton(
                "💸 Withdraw",
                callback_data="withdraw",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Transfer",
                callback_data="transfer",
            ),
            InlineKeyboardButton(
                "🎁 Convert Bonus",
                callback_data="bonus",
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 Invite",
                callback_data="invite",
            ),
            InlineKeyboardButton(
                "📖 Instructions",
                callback_data="instruction",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎧 Contact Support",
                callback_data="support",
            )
        ],
    ]

async def send_main_menu(message, first_name: str):
    keyboard = [
        [
            InlineKeyboardButton(
                "🎮 Play",
                web_app=WebAppInfo(
                    url=settings.TELEGRAM_WEBAPP_URL
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Register",
                callback_data="register",
            ),
            InlineKeyboardButton(
                "💰 Check Balance",
                callback_data="balance",
            ),
        ],
        [
            InlineKeyboardButton(
                "💳 Deposit",
                callback_data="deposit",
            ),
            InlineKeyboardButton(
                "💸 Withdraw",
                callback_data="withdraw",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Transfer",
                callback_data="transfer",
            ),
            InlineKeyboardButton(
                "🎁 Convert Bonus",
                callback_data="bonus",
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 Invite",
                callback_data="invite",
            ),
            InlineKeyboardButton(
                "📖 Instructions",
                callback_data="instruction",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎧 Contact Support",
                callback_data="support",
            )
        ],
    ]

    await message.reply_text(
        "Choose an option below: ",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def home_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        text="🏠 <b>Main Menu</b>\n\nChoose an option:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(main_menu_keyboard()),
    )
    
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    referred = False

    if context.args:
        context.user_data["referral_code"] = context.args[0]
        referred = True

    keyboard = [
        [
            InlineKeyboardButton(
                text="🎮 Play",
                web_app=WebAppInfo(
                    url=settings.TELEGRAM_WEBAPP_URL
                )
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Register",
                callback_data="register"
            ),
            InlineKeyboardButton(
                "💰 Check Balance",
                callback_data="balance"
            ),
        ],
        [
            InlineKeyboardButton(
                "💳 Deposit",
                callback_data="deposit"
            ),
            InlineKeyboardButton(
                "💸 Withdraw",
                callback_data="withdraw"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Transfer",
                callback_data="transfer"
            ),
            InlineKeyboardButton(
                "🎁 Convert Bonus",
                callback_data="bonus"
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 Invite",
                callback_data="invite"
            ),
            InlineKeyboardButton(
                "📖 Instructions",
                callback_data="instruction"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎧 Contact Support",
                callback_data="support"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=(
            f"👋 <b>Welcome, {user.first_name}!</b>\n\n"
            "🎮 <b>Telegram Games</b>\n\n"
            "Play exciting games, compete with friends, and enjoy a fun gaming experience.\n\n"
            +
            (
                "🎁 <b>You joined through an invitation link!</b>\n"
                "Register now and receive your welcome bonus.\n\n"
                if referred
                else ""
            )
            +
            "To get started, please choose an option from the menu below."
        ),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )

async def check_balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()


    telegram_id = update.effective_user.id


    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.telegram_id == telegram_id
            )
            .first()
        )


        if not user:

            await query.message.reply_text(
                "❌ User account not found."
            )

            return


        balance = user.balance or 0

        pending = (
            db.query(WithdrawRequest)
            .filter(
                WithdrawRequest.user_id == user.id,
                WithdrawRequest.status == "PENDING",
            )
            .first()
        )


        message = f"""
        💰 <b>Your Balance</b>

        <b>{balance} ETB</b>
        """

        if pending:
            message += f"""

        ──────────────────

        ⏳ <b>Pending Withdrawal</b>

        💰 Amount: <b>{pending.amount} ETB</b>
        📱 Method: <b>{pending.method}</b>
        📌 Status: <b>{pending.status.title()}</b>
        """

        message += """

        🎮 Ready to play!
        """

        await query.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=HOME_KEYBOARD,
        )


    finally:

        db.close()

async def register_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    telegram_user = query.from_user

    db = SessionLocal()

    try:
        service = AuthService(db)

        user, created, updated_fields, inviter = service.register_telegram_user(
            telegram_user=query.from_user,
            referral_code=context.user_data.get("referral_code")
        )

        if not created:

            if updated_fields:
                await query.message.reply_text(
                    "🔄 <b>Profile Updated</b>\n\n"
                    "Your Telegram information has been synchronized:\n\n"
                    + "\n".join(
                        f"✅ {field}"
                        for field in updated_fields
                    ),
                    parse_mode="HTML",
                    reply_markup=HOME_KEYBOARD,
                )

            else:
                await query.message.reply_text(
                    "✅ You are already registered.\n\n"
                    "Your account information is already up to date. ",
                    reply_markup=HOME_KEYBOARD,
                )

            return

        username = (
            f"@{user.username}"
            if user.username
            else "Not set"
        )

        if inviter:
            await context.bot.send_message(
                chat_id=inviter.telegram_id,
                text=(
                    "🎁 <b>Referral Bonus Received!</b>\n\n"
                    f"Your friend <b>{user.first_name}</b> "
                    "registered using your invite link.\n\n"
                    "💰 You received: <b>10 ETB</b>\n\n"
                    "Keep inviting friends and earn more rewards!"
                ),
                parse_mode="HTML",
            )

        await query.message.reply_text(
            text=(
                "🎉 <b>Registration Successful!</b>\n\n"
                f"👤 <b>Name:</b> {user.first_name}\n"
                f"📛 <b>Username:</b> {username}\n"
                f"🆔 <b>Referral Code:</b> <code>{user.referral_code}</code>\n\n"
                "💰 <b>Welcome Bonus Received:</b> 10 ETB\n\n"
                "Your account has been created successfully."
            ),
            parse_mode="HTML",
            reply_markup=HOME_KEYBOARD,
        )

        context.user_data.pop(
            "referral_code",
            None
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

async def show_deposit_method(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    method: str,
):
    query = update.callback_query
    await query.answer()

    payment = DEPOSIT_METHODS[method]

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ I've Paid",
                callback_data=payment["button_callback"],
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="deposit",
            )
        ],
    ]

    await query.edit_message_text(
        text=(
            f"{payment['title']}\n\n"

            f"👤 <b>Account Name</b>\n"
            f"{payment['account_name']}\n\n"

            f"💳 <b>Account / Phone Number</b>\n"
            f"<code>{payment['account_number']}</code>\n\n"

            "💰 <b>Minimum Deposit</b>\n"
            "10 ETB\n\n"

            "📌 <b>Instructions</b>\n"
            "1. Send money to the account above.\n"
            "2. Save the payment confirmation SMS.\n"
            "3. Press <b>I've Paid</b>.\n"
            "4. Forward the payment SMS to this bot."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def deposit_telebirr(update, context):
    await show_deposit_method(update, context, "telebirr")

async def invite_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    telegram_user = query.from_user

    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.telegram_id == telegram_user.id
            )
            .first()
        )


        if not user:

            await query.message.reply_text(
                "❌ Please register first."
            )
            return


        invite_link = (
            f"https://t.me/"
            f"{settings.TELEGRAM_BOT_USERNAME}"
            f"?start={user.referral_code}"
        )


        await query.message.reply_text(
            f"""
            👥 <b>Invite Friends</b>

            Share your invitation link:

            🔗 <code>{invite_link}</code>


            🎁 Rewards:

            ✅ Your friend gets 10 ETB welcome bonus

            ✅ You get 10 ETB referral bonus


            Invite more friends and earn more!
                        """,
            parse_mode="HTML",
            reply_markup=HOME_KEYBOARD,
            
        )


    finally:

        db.close()

async def deposit_cbe(update, context):
    await show_deposit_method(update, context, "cbe")

async def instruction_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        """
📖 <b>How to Play</b>

🎮 <b>Getting Started</b>

1️⃣ Register your account.
2️⃣ Deposit funds into your wallet.
3️⃣ Press <b>🎮 Play</b>.
4️⃣ Join your preferred game.
5️⃣ Win and receive rewards automatically.

━━━━━━━━━━━━━━━

💳 <b>Deposits</b>

• Minimum Deposit: <b>10 ETB</b>
• Supported Method: <b>Telebirr</b>

━━━━━━━━━━━━━━━

💸 <b>Withdrawals</b>

• Minimum Withdrawal: <b>100 ETB</b>
• Requests are reviewed by the admin.
• Funds are sent after approval.

━━━━━━━━━━━━━━━

👥 <b>Referral Rewards</b>

• Invite friends using your referral link.
• Your friend receives <b>10 ETB</b>.
• You receive <b>10 ETB</b> for every successful registration.

━━━━━━━━━━━━━━━

⚠️ <b>Important</b>

• Never share your Telegram account.
• Make sure payment details are correct.
• Contact support if you need assistance.

Good luck and enjoy playing! 🎉
        """,
        parse_mode="HTML",
        reply_markup=HOME_KEYBOARD,
    )

async def deposit_cbebirr(update, context):
    await show_deposit_method(update, context, "cbebirr")

async def support_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💬 Contact Support",
                    url="https://t.me/TelegramGamesSupport",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home",
                )
            ],
        ]
    )

    await query.message.reply_text(
        """
🎧 <b>Customer Support</b>

Need help?

Our support team can assist you with:

💳 Deposit issues
💸 Withdrawal issues
🎮 Game issues
👤 Account problems
❓ General questions

Click the button below to contact support.
        """,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

async def deposit_boa(update, context):
    await show_deposit_method(update, context, "boa")
    
async def deposit_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🟢 Telebirr",
                callback_data="deposit_telebirr",
            )
        ],
        [
            InlineKeyboardButton(
                "🏦 CBE",
                callback_data="deposit_cbe",
            )
        ],
        [
            InlineKeyboardButton(
                "📱 CBE Birr",
                callback_data="deposit_cbebirr",
            )
        ],
        [
            InlineKeyboardButton(
                "🏛️ Bank of Abyssinia",
                callback_data="deposit_boa",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home",
            )
        ],
    ]

    await query.edit_message_text(
        text=(
            "💳 <b>Deposit</b>\n\n"
            "Choose your preferred payment method."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def transfer_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()


    context.user_data.clear()

    context.user_data["transfer_step"] = "username"


    await query.message.reply_text(
        "👤 Enter receiver Telegram username\n\n"
        "Example:\n"
        "@habitamu",
        reply_markup=HOME_KEYBOARD,
    )

async def transfer_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    # =====================
    # DEPOSIT SMS
    # =====================

    if context.user_data.get("waiting_deposit"):
        await forwarded_sms_handler(update, context)
        return


    text = update.message.text.strip()

    step = context.user_data.get("transfer_step")

    withdraw_step = context.user_data.get("withdraw_step")

    if withdraw_step == "account_name":

        context.user_data["withdraw"]["account_name"] = text

        context.user_data["withdraw_step"] = "account_number"

        await update.message.reply_text(
            "📱 Enter your account/phone number."
        )

        return

    elif withdraw_step == "account_number":

        context.user_data["withdraw"]["account_number"] = text

        context.user_data["withdraw_step"] = "amount"

        await update.message.reply_text(
            "💰 Enter withdrawal amount.\n\nMinimum: 100 ETB"
        )

        return

    elif withdraw_step == "amount":

        try:
            amount = Decimal(text)

        except:
            await update.message.reply_text(
                "❌ Invalid amount."
            )
            return

        if amount < Decimal("100"):
            await update.message.reply_text(
                "❌ Minimum withdrawal amount is 100 ETB."
            )
            return

        db = SessionLocal()

        try:
            user = (
                db.query(User)
                .filter(
                    User.telegram_id == update.effective_user.id
                )
                .first()
            )

            if not user:
                await update.message.reply_text(
                    "❌ Please register first."
                )
                return

            if amount > user.balance:
                await update.message.reply_text(
                    f"❌ Insufficient balance.\n\n"
                    f"Available: {user.balance} ETB"
                )
                return

        finally:
            db.close()

        context.user_data["withdraw"]["amount"] = amount

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Confirm",
                        callback_data="confirm_withdraw",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="cancel_withdraw",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            f"""
    💸 <b>Confirm Withdrawal</b>

    🏦 Method:
    {context.user_data["withdraw"]["method"]}

    👤 Account Name:
    {context.user_data["withdraw"]["account_name"]}

    📱 Account Number:
    {context.user_data["withdraw"]["account_number"]}

    💰 Amount:
    {amount} ETB
            """,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        # Put it HERE
        context.user_data["withdraw_step"] = "confirm"

        return

    # =====================
    # STEP 1: USERNAME
    # =====================

    if step == "username":

        username = text.replace("@", "")

        db = SessionLocal()

        try:

            receiver = (
                db.query(User)
                .filter(User.username == username)
                .first()
            )

            if not receiver:
                await update.message.reply_text(
                    "❌ User not found", 
                    reply_markup=HOME_KEYBOARD,
                )
                return

            sender = (
                db.query(User)
                .filter(
                    User.telegram_id == update.effective_user.id
                )
                .first()
            )

            if sender.id == receiver.id:
                await update.message.reply_text(
                    "❌ Cannot transfer to yourself"
                )
                return

            context.user_data["receiver_id"] = str(receiver.id)
            context.user_data["receiver_username"] = receiver.username
            context.user_data["transfer_step"] = "amount"

            await update.message.reply_text(
                f"✅ Receiver found\n\n"
                f"👤 @{receiver.username}\n\n"
                "💰 Enter amount:", 
                reply_markup=HOME_KEYBOARD,
            )

        finally:
            db.close()

        return


    # =====================
    # STEP 2: AMOUNT
    # =====================

    elif step == "amount":

        try:
            amount = Decimal(text)

        except:
            await update.message.reply_text(
                "❌ Invalid amount"
            )
            return


        if amount <= 0:
            await update.message.reply_text(
                "❌ Amount must be greater than zero"
            )
            return


        context.user_data["amount"] = amount


        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data="confirm_transfer"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="cancel_transfer"
                )
            ]
        ]


        await update.message.reply_text(
            f"""
    💸 <b>Confirm Transfer</b>

    👤 To:
    @{context.user_data['receiver_username']}

    💰 Amount:
    {amount} ETB
            """,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


        context.user_data["transfer_step"] = "confirm"

        return

async def confirm_transfer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query


    await query.answer()


    # Prevent old buttons / already processed requests
    if context.user_data.get("transfer_step") != "confirm":

        await query.answer(
            "⚠️ This transfer has expired.",
            show_alert=True
        )
        return


    # Prevent missing data
    if (
        "receiver_id" not in context.user_data
        or "amount" not in context.user_data
    ):

        await query.answer(
            "⚠️ Transfer data missing. Start again.",
            show_alert=True
        )
        return



    # Lock immediately against double click
    context.user_data["transfer_step"] = "processing"



    db = SessionLocal()


    try:

        sender = (
            db.query(User)
            .filter(
                User.telegram_id ==
                query.from_user.id
            )
            .first()
        )


        receiver = (
            db.query(User)
            .filter(
                User.id ==
                context.user_data["receiver_id"]
            )
            .first()
        )


        amount = context.user_data["amount"]



        if not sender or not receiver:

            await query.message.reply_text(
                "❌ User not found."
            )

            return



        if sender.balance < amount:

            await query.message.reply_text(
                "❌ Not enough balance."
            )

            return



        # Transfer money

        sender.balance -= amount

        receiver.balance += amount



        transfer = TransferRequest(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=amount,
            status="COMPLETED"
        )


        db.add(transfer)

        db.commit()



        # Remove buttons from old message

        try:
            await query.edit_message_reply_markup(
                reply_markup=None
            )

        except Exception:
            pass



        # Notify sender

        await query.message.reply_text(
            f"""
                ✅ <b>Transfer Completed</b>


                💸 Sent:
                {amount} ETB


                👤 To:
                @{receiver.username}


                💰 Remaining Balance:
                {sender.balance} ETB
                            """,
            parse_mode="HTML", 
            reply_markup=HOME_KEYBOARD,
        )



        # Notify receiver

        try:

            await context.bot.send_message(
                chat_id=receiver.telegram_id,

                text=f"""
                🎉 <b>You received a transfer</b>


                💰 Amount:
                {amount} ETB


                👤 From:
                @{sender.username or sender.first_name}


                💳 New Balance:
                {receiver.balance} ETB
                                """,

                parse_mode="HTML", 
                reply_markup=HOME_KEYBOARD,
            )


        except Exception as e:

            print(
                "Receiver notification failed:",
                e
            )



        # Clear old transfer data

        context.user_data.pop(
            "receiver_id",
            None
        )

        context.user_data.pop(
            "receiver_username",
            None
        )

        context.user_data.pop(
            "amount",
            None
        )

        context.user_data.pop(
            "transfer_step",
            None
        )



    except SQLAlchemyError as e:

        db.rollback()

        print(
            "Transfer failed:",
            e
        )


        await query.message.reply_text(
            "❌ Transfer failed. Try again.", 
            reply_markup=HOME_KEYBOARD,
        )


        # allow retry
        context.user_data["transfer_step"] = "confirm"



    finally:

        db.close()

async def cancel_transfer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()


    context.user_data.clear()


    await query.message.reply_text(
        "❌ Transfer cancelled", 
        reply_markup=HOME_KEYBOARD,
    )

async def forwarded_sms_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.user_data.get("waiting_deposit"):
        return


    text = update.message.text


    data = SMSParser.parse(text)


    tx_id = data["transaction_id"]


    if not tx_id:

        await update.message.reply_text(
            "❌ Invalid SMS, Please send correctly!",
            reply_markup=HOME_KEYBOARD,
        )
        return


    db = SessionLocal()


    try:

        sms = (
            db.query(SMSTransaction)
            .filter(
                SMSTransaction.transaction_id == tx_id
            )
            .first()
        )


        if not sms:

            await update.message.reply_text(
                "❌ Transaction not found. "
                "Please wait a little and try again.", 
                reply_markup=HOME_KEYBOARD,
            )

            return



        if sms.is_used:

            await update.message.reply_text(
                "⚠️ This transaction was already used.", 
                reply_markup=HOME_KEYBOARD,
            )

            return



        telegram_id = update.effective_user.id


        user = (
            db.query(User)
            .filter(
                User.telegram_id == telegram_id
            )
            .first()
        )


        if not user:

            await update.message.reply_text(
                "User not found, resend again correctly", 
                reply_markup=HOME_KEYBOARD,
            )
            return



        # CREDIT USER BALANCE

        user.balance += sms.amount


        # Create deposit history record

        deposit = Deposit(

            user_id=user.id,

            amount=sms.amount,

            method="telebirr",

            sms_transaction_id=sms.transaction_id

        )

        db.add(deposit)



        # mark SMS consumed

        sms.is_used = True
        sms.used_at = datetime.utcnow()



        db.commit()



        context.user_data["waiting_deposit"] = False


        await update.message.reply_text(
            f"""
                ✅ Deposit Successful

                💰 Amount:
                {sms.amount} ETB

                🆔 Transaction:
                {sms.transaction_id}

                Your balance has been updated.
                """, 
                reply_markup=HOME_KEYBOARD,
        )


    finally:

        db.close()

async def deposit_paid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()


    telegram_id = update.effective_user.id


    context.user_data["waiting_deposit"] = True


    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.telegram_id == telegram_id
            )
            .first()
        )


        if not user:

            await query.message.reply_text(
                "User not found", 
                reply_markup=HOME_KEYBOARD,
            )
            return


        await query.message.reply_text(
            "📨 Forward your Telebirr confirmation SMS now.", 
            reply_markup=HOME_KEYBOARD,
        )


    finally:
        db.close()

async def withdraw_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.telegram_id == query.from_user.id)
            .first()
        )

        pending = None

        if user:
            pending = (
                db.query(WithdrawRequest)
                .filter(
                    WithdrawRequest.user_id == user.id,
                    WithdrawRequest.status == "PENDING",
                )
                .first()
            )

    finally:
        db.close()

    keyboard = []

    # Only allow new withdrawals if none are pending
    if not pending:

        keyboard.extend(
            [
                [
                    InlineKeyboardButton(
                        "📱 Telebirr",
                        callback_data="withdraw_method_telebirr",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏦 CBE",
                        callback_data="withdraw_method_cbe",
                    )
                ],
            ]
        )

        text = "💸 <b>Select Withdrawal Method</b>"

    # Show cancel button if pending exists
    if pending:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "❌ Cancel Pending Withdrawal",
                    callback_data=f"cancel_pending_withdraw_{pending.id}",
                )
            ]
        )

        text = (
            f"""
        💸 <b>Withdraw</b>

        ⏳ You already have a pending withdrawal.

        💰 Amount: {pending.amount} ETB
        📱 Method: {pending.method}

        You can cancel it before submitting another request.
        """
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home",
            )
        ]
    )

    await query.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def withdraw_method_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    method = query.data.replace(
        "withdraw_method_",
        "",
    )

    context.user_data["withdraw"] = {
        "method": method.upper(),
    }

    context.user_data["withdraw_step"] = "account_name"

    await query.message.reply_text(
        "👤 Enter the account holder's full name."
    )

async def confirm_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.telegram_id == query.from_user.id
            )
            .first()
        )

        if not user:

            await query.message.reply_text(
                "❌ Please register first.",
                reply_markup=HOME_KEYBOARD,
            )

            return

        data = context.user_data.get("withdraw")

        if not data:

            await query.message.reply_text(
                "❌ Withdrawal session expired.",
                reply_markup=HOME_KEYBOARD,
            )

            return

        request = WithdrawRequest(
            user_id=user.id,
            method=data["method"],
            account_name=data["account_name"],
            account_number=data["account_number"],
            amount=data["amount"],
            status="PENDING",
        )

        db.add(request)

        db.commit()
        context.user_data.pop("withdraw", None)
        context.user_data.pop("withdraw_step", None)
        await query.message.reply_text(
            f"""
        ✅ <b>Withdrawal Request Submitted</b>

        💰 Amount:
        {request.amount} ETB

        📱 Method:
        {request.method}

        ⏳ Status:
        Pending Approval

        Your request has been sent successfully.

        You'll receive a notification once it has been processed.
        """,
            parse_mode="HTML",
            reply_markup=HOME_KEYBOARD,
        )

    finally:

        db.close()

async def cancel_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    context.user_data.pop("withdraw", None)
    context.user_data.pop("withdraw_step", None)

    await query.message.reply_text(
        "❌ Withdrawal cancelled.",
        reply_markup=HOME_KEYBOARD,
    )

async def cancel_pending_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    await query.answer()

    withdraw_id = uuid.UUID(
        query.data.replace(
            "cancel_pending_withdraw_",
            "",
        )
    )

    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.telegram_id == query.from_user.id
            )
            .first()
        )

        if not user:

            await query.message.reply_text(
                "❌ Please register first.",
                reply_markup=HOME_KEYBOARD,
            )

            return

        withdraw = (
            db.query(WithdrawRequest)
            .filter(
                WithdrawRequest.id == withdraw_id,
                WithdrawRequest.user_id == user.id,
                WithdrawRequest.status == "PENDING",
            )
            .first()
        )

        if not withdraw:

            await query.message.reply_text(
                "❌ Pending withdrawal not found.",
                reply_markup=HOME_KEYBOARD,
            )

            return

        withdraw.status = "CANCELLED"

        db.commit()

        await query.message.reply_text(
            """
✅ <b>Withdrawal Cancelled</b>

Your pending withdrawal request has been cancelled successfully.

You can now submit a new withdrawal request.
            """,
            parse_mode="HTML",
            reply_markup=HOME_KEYBOARD,
        )

    finally:

        db.close()