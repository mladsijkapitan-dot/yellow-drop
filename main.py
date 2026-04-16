import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from bot.handlers import drop, start, trade, wardrobe
from bot.middlewares.db import DbSessionMiddleware, RedisMiddleware
from config import BOT_TOKEN, REDIS_URL
from db.models import Base
from db.session import engine
from db.seed import seed

logging.basicConfig(level=logging.INFO)


async def main():
    # Создать таблицы если нет
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Заполнить контент
    await seed()

    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    # Middleware
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(RedisMiddleware(redis))

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(drop.router)
    dp.include_router(wardrobe.router)
    dp.include_router(trade.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
