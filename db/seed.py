"""Начальный контент — 25 вещей для MVP."""
import asyncio

from sqlalchemy import select

from db.models import Item, Rarity
from db.session import AsyncSessionFactory

ITEMS = [
    # BASE (10)
    ("Nike Air Force 1 White", Rarity.base, "Классика в белом цвете. С чем угодно."),
    ("Levi's 501 Blue", Rarity.base, "Прямые джинсы — вечный базис."),
    ("White Tee Oversized", Rarity.base, "Оверсайз-футболка без принта. Просто белая."),
    ("New Era 9Forty Black", Rarity.base, "Кепка на каждый день."),
    ("Nike Crew Socks", Rarity.base, "Белые носки с логотипом. Много не бывает."),
    ("Черная толстовка без капюшона", Rarity.base, "Crewneck на осень и весну."),
    ("Adidas Тrackpants Black", Rarity.base, "Спортивки в классическом черном."),
    ("Белая рубашка оверсайз", Rarity.base, "Базовая белая рубаха."),
    ("Чёрные джинсы slim", Rarity.base, "Слим под что угодно."),
    ("Серое худи с капюшоном", Rarity.base, "Стандарт любого гардероба."),

    # MEDIUM (8)
    ("Nike Cortez OG", Rarity.medium, "Ретро-кроссовок, который вернулся."),
    ("Carhartt WIP Beanie", Rarity.medium, "Шапка рыбака от Carhartt. Иконика."),
    ("Dickies 874 Pants Khaki", Rarity.medium, "Рабочие брюки, ставшие streetwear."),
    ("Champion Reverse Weave Hoodie", Rarity.medium, "Оригинальное обратное плетение."),
    ("Vans Old Skool Black/White", Rarity.medium, "Скейт-классика для города."),
    ("Patagonia Synchilla Fleece", Rarity.medium, "Флиска на все случаи жизни."),
    ("Стёганый пуффер-жилет чёрный", Rarity.medium, "Жилет поверх худи — правильный слой."),
    ("Baggy Cargo Pants Olive", Rarity.medium, "Широкие карго в оливе."),

    # ARCHIVE (5)
    ("Raf Simons x Adidas Detroit Runner", Rarity.archive, "Коллаборация 2014. Раритет."),
    ("Helmut Lang Astro Hoodie 2002", Rarity.archive, "Архивный астро-худи с молниями."),
    ("Margiela Tabi Boots Black", Rarity.archive, "Раздвоенный нос. Ни с чем не спутать."),
    ("Stone Island Shadow Project Jacket", Rarity.archive, "Лимитированная техно-куртка."),
    ("Undercover SS04 Graphic Tee", Rarity.archive, "Архивный принт Jun Takahashi."),

    # LEGENDARY (2)
    ("Nike Air Yeezy 1 Prototype", Rarity.legendary, "Прото, который видели единицы. 🟡"),
    ("Virgil Abloh x MCA Chicago Tee", Rarity.legendary, "Музейный тираж. Один из 100."),
]


async def seed():
    async with AsyncSessionFactory() as session:
        existing = (await session.execute(select(Item))).scalars().all()
        if existing:
            print(f"Уже есть {len(existing)} вещей, пропускаю seed.")
            return

        for name, rarity, description in ITEMS:
            session.add(Item(name=name, rarity=rarity, description=description))

        await session.commit()
        print(f"Добавлено {len(ITEMS)} вещей.")


if __name__ == "__main__":
    asyncio.run(seed())
