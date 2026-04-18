from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import main_menu
from db.models import User

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    user = await session.get(User, user_id)

    if not user:
        user = User(
            id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name or "Игрок",
        )
        session.add(user)
        await session.commit()
        text = (
            f"🌑 GRAIL\n\n"
            f"┈ Добро пожаловать, {user.first_name} ┈\n\n"
            f"Твоя коллекция, редкие находки\n"
            f"и все важные разделы уже здесь.\n\n"
            f"✦ Выбери, куда перейти ✦"
        )
    else:
        text = (
            f"🌑 GRAIL\n\n"
            f"┈ С возвращением, {user.first_name} ┈\n\n"
            f"Твоя коллекция, редкие находки\n"
            f"и все важные разделы уже здесь.\n\n"
            f"✦ Выбери, куда перейти ✦"
        )

    await message.answer(text, reply_markup=main_menu())
