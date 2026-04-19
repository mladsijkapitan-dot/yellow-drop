from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User

router = Router()


def leaderboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👁️ Смотреть игроков", callback_data="players"))
    builder.row(InlineKeyboardButton(text="🌑 Меню", callback_data="menu"))
    return builder.as_markup()


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
    await message.answer(text, parse_mode="HTML", reply_markup=leaderboard_keyboard())


@router.callback_query(lambda c: c.data == "leaderboard")
async def handle_leaderboard(callback: CallbackQuery, session: AsyncSession):
    text = await leaderboard_text(session, callback.from_user.id)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=leaderboard_keyboard())
    await callback.answer()
