import random
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DROP_COOLDOWN_HOURS, DROP_MAX_PER_DAY, RARITY_WEIGHTS
from db.models import Item, Rarity, User, UserItem


def _weighted_rarity() -> Rarity:
    rarities = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return Rarity(random.choices(rarities, weights=weights, k=1)[0])


async def get_drop_status(user: User) -> dict:
    """Возвращает статус дропа: доступен ли и сколько осталось секунд."""
    now = datetime.now(timezone.utc)

    # Lazy reset: если последний дроп был до сегодня — сбрасываем счётчик
    if user.last_drop_at and user.last_drop_at.date() < now.date():
        user.drop_count = 0

    if user.drop_count >= DROP_MAX_PER_DAY:
        # Считаем до начала следующего дня UTC
        from datetime import timedelta
        next_reset = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
        wait_seconds = int((next_reset - now).total_seconds())
        return {"available": False, "reason": "daily_limit", "wait_seconds": wait_seconds}

    if user.last_drop_at:
        from datetime import timedelta
        next_drop = user.last_drop_at + timedelta(hours=DROP_COOLDOWN_HOURS)
        if now < next_drop:
            wait_seconds = int((next_drop - now).total_seconds())
            return {"available": False, "reason": "cooldown", "wait_seconds": wait_seconds}

    drops_left = DROP_MAX_PER_DAY - user.drop_count
    return {"available": True, "drops_left": drops_left}


async def do_drop(user: User, session: AsyncSession, redis: Redis) -> Item | None:
    """Выполняет дроп с Redis-локом. Возвращает Item или None если гонка."""
    lock_key = f"drop_lock:{user.id}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=5)
    if not acquired:
        return None

    try:
        now = datetime.now(timezone.utc)

        # Повторная проверка внутри лока (защита от гонки)
        status = await get_drop_status(user)
        if not status["available"]:
            return None

        rarity = _weighted_rarity()
        result = await session.execute(
            select(Item).where(Item.rarity == rarity, Item.is_active == True)
        )
        items = result.scalars().all()
        if not items:
            # Fallback на base если нет вещей нужной редкости
            result = await session.execute(
                select(Item).where(Item.rarity == Rarity.base, Item.is_active == True)
            )
            items = result.scalars().all()

        if not items:
            return None

        chosen = random.choice(items)
        session.add(UserItem(user_id=user.id, item_id=chosen.id))

        # Lazy reset drop_count если нужно
        if user.last_drop_at and user.last_drop_at.date() < now.date():
            user.drop_count = 0

        user.drop_count += 1
        user.last_drop_at = now

        await session.commit()
        return chosen
    finally:
        await redis.delete(lock_key)
