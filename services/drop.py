import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DROP_COOLDOWN_HOURS, DROP_MAX_PER_DAY, RARITY_WEIGHTS
from db.models import Item, Rarity, User, UserItem


def _weighted_rarity() -> Rarity:
    rarities = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return Rarity(random.choices(rarities, weights=weights, k=1)[0])


async def get_drop_status(user: User) -> dict:
    now = datetime.now(timezone.utc)

    # Lazy reset: если последний дроп был до сегодня — сбрасываем счётчик
    if user.last_drop_at and user.last_drop_at.date() < now.date():
        user.drop_count = 0

    if user.drop_count >= DROP_MAX_PER_DAY:
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


async def do_drop(user: User, session: AsyncSession) -> Item | None:
    """Выполняет дроп. SELECT FOR UPDATE защищает от гонки запросов."""
    # Блокируем строку пользователя на время транзакции
    result = await session.execute(
        select(User).where(User.id == user.id).with_for_update()
    )
    locked_user = result.scalar_one()

    now = datetime.now(timezone.utc)

    # Lazy reset внутри лока
    if locked_user.last_drop_at and locked_user.last_drop_at.date() < now.date():
        locked_user.drop_count = 0

    # Повторная проверка внутри лока
    if locked_user.drop_count >= DROP_MAX_PER_DAY:
        return None

    if locked_user.last_drop_at:
        from datetime import timedelta
        next_drop = locked_user.last_drop_at + timedelta(hours=DROP_COOLDOWN_HOURS)
        if now < next_drop:
            return None

    rarity = _weighted_rarity()
    items_result = await session.execute(
        select(Item).where(Item.rarity == rarity, Item.is_active == True)
    )
    items = items_result.scalars().all()

    if not items:
        items_result = await session.execute(
            select(Item).where(Item.rarity == Rarity.base, Item.is_active == True)
        )
        items = items_result.scalars().all()

    if not items:
        return None

    chosen = random.choice(items)
    session.add(UserItem(user_id=locked_user.id, item_id=chosen.id))

    locked_user.drop_count += 1
    locked_user.last_drop_at = now

    await session.commit()

    # Обновляем исходный объект user
    user.drop_count = locked_user.drop_count
    user.last_drop_at = locked_user.last_drop_at

    return chosen
