import asyncio

from app.bot.bot import create_bot


async def main():

    bot = create_bot()

    await bot.initialize()
    await bot.start()

    await bot.updater.start_polling()

    print("Telegram bot running")

    await asyncio.Event().wait()


asyncio.run(main())