import asyncio

from app.bot.bot import create_bot


bot_application = None


async def start_bot():

    global bot_application

    bot_application = create_bot()

    await bot_application.initialize()

    await bot_application.start()

    await bot_application.updater.start_polling()

    print("Telegram bot running")


async def stop_bot():

    global bot_application

    if bot_application:

        await bot_application.updater.stop()

        await bot_application.stop()

        await bot_application.shutdown()

        print("Telegram bot stopped")