import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.handlers import admin, drop, leaderboard, start, trade, wardrobe
from bot.middlewares.db import DbSessionMiddleware
from config import BOT_TOKEN
from db.models import Base
from db.session import engine
from db.seed import seed

logging.basicConfig(level=logging.INFO)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(DbSessionMiddleware())

    dp.include_router(start.router)
    dp.include_router(drop.router)
    dp.include_router(wardrobe.router)
    dp.include_router(trade.router)
    dp.include_router(leaderboard.router)
    dp.include_router(admin.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="drop", description="🎁 Получить дроп"),
    ])

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
