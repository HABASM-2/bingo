from telegram import Update
from telegram.ext import ContextTypes


async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = update.message.text

    if text == "📝 Register":
        await register(update, context)

    elif text == "🎮 Play":
        await play(update, context)

    elif text == "💰 Check Balance":
        await check_balance(update, context)

    else:
        await update.message.reply_text(
            "Please choose an option from the menu."
        )