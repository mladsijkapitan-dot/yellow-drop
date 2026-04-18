from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import back_to_menu
from db.models import User

router = Router()


async def leaderboard_text(session: AsyncSession, current_user_id: int) -> str:
    result = await session.execute(
        select(User).order_by(User.prestige.desc()).limit(10)
    )
    users = result.scalars().all()

    if not users:
        return "Пока нет игроков в таблице."

    lines = ["🏛️ <b>Зал Престижа</b>\n"]
    for i, user in enumerate(users):
        name = f"@{user.username}" if user.username else user.first_name
        marker = " ←" if user.id == current_user_id else ""
        lines.append(f"{i + 1}. {name} — {user.prestige} Prestige{marker}")

    return "\n".join(lines)


@router.message(Command("top"))
async def cmd_top(message: Message, session: AsyncSession):
    text = await leaderboard_text(session, message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=back_to_menu())


@router.callback_query(lambda c: c.data == "leaderboard")
async def handle_leaderboard(callback: CallbackQuery, session: AsyncSession):
    text = await leaderboard_text(session, callback.from_user.id)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=back_to_menu())
    await callback.answer()
