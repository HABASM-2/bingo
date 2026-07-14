from telegram import Update


class BotService:

    @staticmethod
    async def send_registration_success(update: Update, user):

        text = (
            "🎉 <b>Registration Successful!</b>\n\n"
            f"👤 <b>Name:</b> {user.first_name}\n"
            f"🆔 <b>Username:</b> @{user.username if user.username else 'Not Set'}\n\n"
            "💰 <b>Balance:</b> 0.00 ETB\n"
            "🎁 <b>Bonus:</b> 0.00 ETB\n"
            "🎮 <b>Status:</b> Active\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ Your account has been created successfully.\n\n"
            "Press 🎮 Play to start playing."
        )

        await update.message.reply_text(
            text,
            parse_mode="HTML",
        )