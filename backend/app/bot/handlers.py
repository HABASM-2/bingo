"""Telegram bot command and callback handlers."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.helpers import persist_lang, resolve_lang
from app.bot.i18n import GAME_TITLES, t
from app.bot.links import build_invite_link
from app.bot.keyboards import (
    confirm_cancel_keyboard,
    deposit_menu_keyboard,
    deposit_method_keyboard,
    games_keyboard,
    home_keyboard,
    language_keyboard,
    main_menu_keyboard,
    open_game_keyboard,
    support_keyboard,
    withdraw_method_keyboard,
    back_home_row,
)
from app.core.config import settings
from app.db.database import SessionLocal
from app.admin.payment_accounts import (
    get_enabled_deposit_account,
    list_enabled_public,
)
from app.models.request_tr import TransferRequest, WithdrawRequest
from app.models.sms_transaction import SMSTransaction
from app.models.user import User
from app.models.wallet_transaction import Deposit
from app.services.auth_service import AuthService
from app.services.sms_parser import SMSParser


async def _answer(query) -> None:
    try:
        await query.answer()
    except Exception:
        pass


async def _edit_or_reply(query, text: str, reply_markup=None) -> None:
    try:
        await query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


# ── Menu / navigation ───────────────────────────────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred = False
    if context.args:
        context.user_data["referral_code"] = context.args[0]
        referred = True

    lang = resolve_lang(update, context)
    referral = t(lang, "welcome.referral") if referred else ""
    text = t(
        lang,
        "welcome",
        name=user.first_name if user else "",
        referral=referral,
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(lang),
    )


async def home_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    await _edit_or_reply(
        query,
        t(lang, "menu.home"),
        main_menu_keyboard(lang),
    )


async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer(query)
    lang = resolve_lang(update, context)
    text = t(lang, "menu.games")
    markup = games_keyboard(lang)
    if query:
        await _edit_or_reply(query, text, markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await games_menu(update, context)


async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await games_menu(update, context)


async def open_game_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    game: str,
):
    lang = resolve_lang(update, context)
    title = GAME_TITLES.get(game, game.title())
    text = t(
        lang,
        "open.game",
        title=title,
        blurb=t(lang, f"game.{game}.blurb"),
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=open_game_keyboard(lang, game),
    )


async def bingo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_game_command(update, context, "bingo")


async def dama_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_game_command(update, context, "dama")


async def aviator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_game_command(update, context, "aviator")


async def plinko_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_game_command(update, context, "plinko")


async def lotto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_game_command(update, context, "lotto")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_lang(update, context)
    text = t(lang, "help")
    markup = home_keyboard(lang)
    query = update.callback_query
    if query:
        await _answer(query)
        await _edit_or_reply(query, text, markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_lang(update, context)
    text = t(
        lang,
        "language.prompt",
        current=t(lang, f"language.label.{lang}"),
    )
    markup = language_keyboard(lang)
    query = update.callback_query
    if query:
        await _answer(query)
        await _edit_or_reply(query, text, markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def language_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    choice = "en" if query.data == "lang_en" else "am"
    lang = persist_lang(update, context, choice)
    await _edit_or_reply(
        query,
        t(lang, "language.changed", label=t(lang, f"language.label.{lang}")),
        main_menu_keyboard(lang),
    )


# ── Balance / register / invite / support ────────────────────────────


async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_lang(update, context)
    query = update.callback_query
    if query:
        await _answer(query)

    telegram_id = update.effective_user.id
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            text = t(lang, "err.user_not_found")
            markup = home_keyboard(lang)
            if query:
                await query.message.reply_text(text, reply_markup=markup)
            else:
                await update.message.reply_text(text, reply_markup=markup)
            return

        pending = (
            db.query(WithdrawRequest)
            .filter(
                WithdrawRequest.user_id == user.id,
                WithdrawRequest.status == "PENDING",
            )
            .first()
        )
        pending_text = ""
        if pending:
            pending_text = t(
                lang,
                "balance.pending",
                amount=pending.amount,
                method=pending.method,
                status=pending.status.title(),
            )
        text = t(
            lang,
            "balance",
            balance=user.balance or 0,
            pending=pending_text,
        )
        markup = home_keyboard(lang)
        if query:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    finally:
        db.close()


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_balance(update, context)


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    db = SessionLocal()
    try:
        service = AuthService(db)
        user, created, updated_fields, inviter = service.register_telegram_user(
            telegram_user=query.from_user,
            referral_code=context.user_data.get("referral_code"),
        )
        # Keep bot-chosen language if the user picked one before registering.
        session_lang = context.user_data.get("lang")
        if session_lang in {"en", "am"} and user.language_code != session_lang:
            user.language_code = session_lang
            db.commit()
            db.refresh(user)
        lang = session_lang if session_lang in {"en", "am"} else resolve_lang(update, context)
        if not created:
            if updated_fields:
                await query.message.reply_text(
                    t(
                        lang,
                        "register.updated",
                        fields="\n".join(f"• {field}" for field in updated_fields),
                    ),
                    parse_mode="HTML",
                    reply_markup=home_keyboard(lang),
                )
            else:
                await query.message.reply_text(
                    t(lang, "register.already"),
                    reply_markup=home_keyboard(lang),
                )
            return

        username = f"@{user.username}" if user.username else t(lang, "username.not_set")
        if inviter and inviter.telegram_id:
            from app.bot.locale import get_user_locale

            inviter_lang = get_user_locale(db, inviter.telegram_id) or lang
            try:
                await context.bot.send_message(
                    chat_id=inviter.telegram_id,
                    text=t(
                        inviter_lang,
                        "register.referral_notify",
                        name=user.first_name,
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        await query.message.reply_text(
            t(
                lang,
                "register.success",
                name=user.first_name,
                username=username,
                code=user.referral_code,
            ),
            parse_mode="HTML",
            reply_markup=home_keyboard(lang),
        )
        context.user_data.pop("referral_code", None)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_lang(update, context)
    query = update.callback_query
    if query:
        await _answer(query)

    telegram_user = update.effective_user
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_user.id).first()
        if not user:
            text = t(lang, "err.not_registered")
            if query:
                await query.message.reply_text(text, reply_markup=home_keyboard(lang))
            else:
                await update.message.reply_text(text, reply_markup=home_keyboard(lang))
            return

        invite_link = build_invite_link(user.referral_code)
        text = t(lang, "invite", link=invite_link)
        markup = home_keyboard(lang)
        if query:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    finally:
        db.close()


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await invite_handler(update, context)


async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    await query.message.reply_text(
        t(lang, "support"),
        parse_mode="HTML",
        reply_markup=support_keyboard(lang),
    )


async def instruction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy Instructions button → help."""
    await help_handler(update, context)


# ── Deposit ──────────────────────────────────────────────────────────


async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_lang(update, context)
    query = update.callback_query
    db = SessionLocal()
    try:
        accounts = list_enabled_public(db, "deposit")["items"]
    finally:
        db.close()

    if not accounts:
        text = t(lang, "deposit.empty")
        markup = InlineKeyboardMarkup([back_home_row(lang)])
    else:
        text = t(lang, "deposit.menu")
        markup = deposit_menu_keyboard(lang, accounts)

    if query:
        await _answer(query)
        await _edit_or_reply(query, text, markup)
    else:
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
        )


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await deposit_menu(update, context)


async def show_deposit_account(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    account_id: uuid.UUID,
):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    db = SessionLocal()
    try:
        account = get_enabled_deposit_account(db, account_id)
    finally:
        db.close()

    if not account:
        await _edit_or_reply(
            query,
            t(lang, "deposit.empty"),
            InlineKeyboardMarkup([back_home_row(lang)]),
        )
        return

    title = t(lang, "deposit.title.generic", bank=account.bank)
    await query.edit_message_text(
        text=t(
            lang,
            "deposit.method",
            title=title,
            bank=account.bank,
            account_name=account.account_name,
            account_number=account.account_number,
        ),
        parse_mode="HTML",
        reply_markup=deposit_method_keyboard(lang),
    )


async def deposit_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw = (query.data or "").replace("deposit_account_", "", 1)
    try:
        account_id = uuid.UUID(raw)
    except ValueError:
        await _answer(query)
        return
    await show_deposit_account(update, context, account_id)


async def deposit_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    context.user_data["waiting_deposit"] = True
    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.telegram_id == update.effective_user.id)
            .first()
        )
        if not user:
            await query.message.reply_text(
                t(lang, "err.user_not_found"),
                reply_markup=home_keyboard(lang),
            )
            return
        await query.message.reply_text(
            t(lang, "deposit.forward_sms"),
            reply_markup=home_keyboard(lang),
        )
    finally:
        db.close()


async def forwarded_sms_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_deposit"):
        return

    lang = resolve_lang(update, context)
    text = update.message.text
    data = SMSParser.parse(text)
    tx_id = data["transaction_id"]
    if not tx_id:
        await update.message.reply_text(
            t(lang, "deposit.invalid_sms"),
            reply_markup=home_keyboard(lang),
        )
        return

    db = SessionLocal()
    try:
        sms = (
            db.query(SMSTransaction)
            .filter(SMSTransaction.transaction_id == tx_id)
            .first()
        )
        if not sms:
            await update.message.reply_text(
                t(lang, "deposit.tx_not_found"),
                reply_markup=home_keyboard(lang),
            )
            return
        if sms.is_used:
            await update.message.reply_text(
                t(lang, "deposit.tx_used"),
                reply_markup=home_keyboard(lang),
            )
            return

        user = (
            db.query(User)
            .filter(User.telegram_id == update.effective_user.id)
            .first()
        )
        if not user:
            await update.message.reply_text(
                t(lang, "err.user_not_found"),
                reply_markup=home_keyboard(lang),
            )
            return

        user.balance += sms.amount
        db.add(
            Deposit(
                user_id=user.id,
                amount=sms.amount,
                method="telebirr",
                sms_transaction_id=sms.transaction_id,
            )
        )
        sms.is_used = True
        sms.used_at = datetime.utcnow()
        db.commit()
        context.user_data["waiting_deposit"] = False
        await update.message.reply_text(
            t(lang, "deposit.success", amount=sms.amount, tx=sms.transaction_id),
            parse_mode="HTML",
            reply_markup=home_keyboard(lang),
        )
    finally:
        db.close()


# ── Transfer ─────────────────────────────────────────────────────────


async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    context.user_data.clear()
    context.user_data["lang"] = lang
    context.user_data["transfer_step"] = "username"
    await query.message.reply_text(
        t(lang, "transfer.ask_user"),
        reply_markup=home_keyboard(lang),
    )


async def transfer_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_deposit"):
        await forwarded_sms_handler(update, context)
        return

    lang = resolve_lang(update, context)
    text = update.message.text.strip()
    step = context.user_data.get("transfer_step")
    withdraw_step = context.user_data.get("withdraw_step")

    if withdraw_step == "account_name":
        context.user_data["withdraw"]["account_name"] = text
        context.user_data["withdraw_step"] = "account_number"
        await update.message.reply_text(t(lang, "withdraw.ask_number"))
        return

    if withdraw_step == "account_number":
        context.user_data["withdraw"]["account_number"] = text
        context.user_data["withdraw_step"] = "amount"
        await update.message.reply_text(
            t(lang, "withdraw.ask_amount"),
            parse_mode="HTML",
        )
        return

    if withdraw_step == "amount":
        try:
            amount = Decimal(text)
        except Exception:
            await update.message.reply_text(t(lang, "transfer.invalid_amount"))
            return

        if amount < Decimal("100"):
            await update.message.reply_text(t(lang, "withdraw.min"))
            return

        db = SessionLocal()
        try:
            user = (
                db.query(User)
                .filter(User.telegram_id == update.effective_user.id)
                .first()
            )
            if not user:
                await update.message.reply_text(t(lang, "err.not_registered"))
                return
            if amount > user.balance:
                await update.message.reply_text(
                    t(lang, "withdraw.insufficient", balance=user.balance)
                )
                return
        finally:
            db.close()

        context.user_data["withdraw"]["amount"] = amount
        context.user_data["withdraw_step"] = "confirm"
        await update.message.reply_text(
            t(
                lang,
                "withdraw.confirm",
                method=context.user_data["withdraw"]["method"],
                name=context.user_data["withdraw"]["account_name"],
                number=context.user_data["withdraw"]["account_number"],
                amount=amount,
            ),
            parse_mode="HTML",
            reply_markup=confirm_cancel_keyboard(
                lang,
                confirm_data="confirm_withdraw",
                cancel_data="cancel_withdraw",
            ),
        )
        return

    if step == "username":
        username = text.replace("@", "")
        db = SessionLocal()
        try:
            receiver = db.query(User).filter(User.username == username).first()
            if not receiver:
                await update.message.reply_text(
                    t(lang, "transfer.not_found"),
                    reply_markup=home_keyboard(lang),
                )
                return
            sender = (
                db.query(User)
                .filter(User.telegram_id == update.effective_user.id)
                .first()
            )
            if sender and sender.id == receiver.id:
                await update.message.reply_text(t(lang, "transfer.self"))
                return
            context.user_data["receiver_id"] = str(receiver.id)
            context.user_data["receiver_username"] = receiver.username
            context.user_data["transfer_step"] = "amount"
            await update.message.reply_text(
                t(lang, "transfer.ask_amount", username=receiver.username),
                reply_markup=home_keyboard(lang),
            )
        finally:
            db.close()
        return

    if step == "amount":
        try:
            amount = Decimal(text)
        except Exception:
            await update.message.reply_text(t(lang, "transfer.invalid_amount"))
            return
        if amount <= 0:
            await update.message.reply_text(t(lang, "transfer.amount_positive"))
            return

        context.user_data["amount"] = amount
        context.user_data["transfer_step"] = "confirm"
        await update.message.reply_text(
            t(
                lang,
                "transfer.confirm",
                username=context.user_data["receiver_username"],
                amount=amount,
            ),
            parse_mode="HTML",
            reply_markup=confirm_cancel_keyboard(
                lang,
                confirm_data="confirm_transfer",
                cancel_data="cancel_transfer",
            ),
        )


async def confirm_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = resolve_lang(update, context)

    if context.user_data.get("transfer_step") != "confirm":
        await query.answer(t(lang, "transfer.expired"), show_alert=True)
        return
    if "receiver_id" not in context.user_data or "amount" not in context.user_data:
        await query.answer(t(lang, "transfer.missing"), show_alert=True)
        return

    await _answer(query)
    context.user_data["transfer_step"] = "processing"
    db = SessionLocal()
    try:
        sender = (
            db.query(User).filter(User.telegram_id == query.from_user.id).first()
        )
        receiver = (
            db.query(User)
            .filter(User.id == context.user_data["receiver_id"])
            .first()
        )
        amount = context.user_data["amount"]
        if not sender or not receiver:
            await query.message.reply_text(t(lang, "transfer.not_found"))
            return
        if sender.balance < amount:
            await query.message.reply_text(t(lang, "transfer.insufficient"))
            return

        sender.balance -= amount
        receiver.balance += amount
        db.add(
            TransferRequest(
                sender_id=sender.id,
                receiver_id=receiver.id,
                amount=amount,
                status="COMPLETED",
            )
        )
        db.commit()

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        await query.message.reply_text(
            t(
                lang,
                "transfer.done",
                amount=amount,
                username=receiver.username,
                balance=sender.balance,
            ),
            parse_mode="HTML",
            reply_markup=home_keyboard(lang),
        )

        try:
            await context.bot.send_message(
                chat_id=receiver.telegram_id,
                text=t(
                    lang,
                    "transfer.received",
                    amount=amount,
                    username=sender.username or sender.first_name,
                    balance=receiver.balance,
                ),
                parse_mode="HTML",
                reply_markup=home_keyboard(lang),
            )
        except Exception:
            pass

        for key in ("receiver_id", "receiver_username", "amount", "transfer_step"):
            context.user_data.pop(key, None)
    except SQLAlchemyError:
        db.rollback()
        await query.message.reply_text(
            t(lang, "transfer.failed"),
            reply_markup=home_keyboard(lang),
        )
        context.user_data["transfer_step"] = "confirm"
    finally:
        db.close()


async def cancel_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    context.user_data.clear()
    context.user_data["lang"] = lang
    await query.message.reply_text(
        t(lang, "transfer.cancelled"),
        reply_markup=home_keyboard(lang),
    )


# ── Withdraw ─────────────────────────────────────────────────────────


async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = resolve_lang(update, context)
    query = update.callback_query
    if query:
        await _answer(query)

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.telegram_id == update.effective_user.id)
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

    keyboard: list[list[InlineKeyboardButton]] = []
    if not pending:
        keyboard.extend(withdraw_method_keyboard(lang))
        text = t(lang, "withdraw.select")
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    t(lang, "btn.cancel_pending_withdraw"),
                    callback_data=f"cancel_pending_withdraw_{pending.id}",
                )
            ]
        )
        text = t(
            lang,
            "withdraw.pending",
            amount=pending.amount,
            method=pending.method,
        )

    keyboard.append(
        [InlineKeyboardButton(t(lang, "btn.back"), callback_data="home")]
    )
    markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await withdraw_handler(update, context)


async def withdraw_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    method = query.data.replace("withdraw_method_", "")
    context.user_data["withdraw"] = {"method": method.upper()}
    context.user_data["withdraw_step"] = "account_name"
    await query.message.reply_text(t(lang, "withdraw.ask_name"))


async def confirm_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    db = SessionLocal()
    try:
        user = (
            db.query(User).filter(User.telegram_id == query.from_user.id).first()
        )
        if not user:
            await query.message.reply_text(
                t(lang, "err.not_registered"),
                reply_markup=home_keyboard(lang),
            )
            return
        data = context.user_data.get("withdraw")
        if not data:
            await query.message.reply_text(
                t(lang, "withdraw.expired"),
                reply_markup=home_keyboard(lang),
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
            t(
                lang,
                "withdraw.submitted",
                amount=request.amount,
                method=request.method,
            ),
            parse_mode="HTML",
            reply_markup=home_keyboard(lang),
        )
    finally:
        db.close()


async def cancel_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    context.user_data.pop("withdraw", None)
    context.user_data.pop("withdraw_step", None)
    await query.message.reply_text(
        t(lang, "withdraw.cancelled"),
        reply_markup=home_keyboard(lang),
    )


async def cancel_pending_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await _answer(query)
    lang = resolve_lang(update, context)
    withdraw_id = uuid.UUID(query.data.replace("cancel_pending_withdraw_", ""))
    db = SessionLocal()
    try:
        user = (
            db.query(User).filter(User.telegram_id == query.from_user.id).first()
        )
        if not user:
            await query.message.reply_text(
                t(lang, "err.not_registered"),
                reply_markup=home_keyboard(lang),
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
                t(lang, "withdraw.pending_missing"),
                reply_markup=home_keyboard(lang),
            )
            return
        withdraw.status = "CANCELLED"
        db.commit()
        await query.message.reply_text(
            t(lang, "withdraw.pending_cancelled"),
            parse_mode="HTML",
            reply_markup=home_keyboard(lang),
        )
    finally:
        db.close()
