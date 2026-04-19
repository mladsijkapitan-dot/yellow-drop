from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import back_to_menu
from db.models import Rarity, User, UserItem
from services.drop import get_archive_stats

router = Router()

RARITY_LABEL = {
    Rarity.base: "Base",
    Rarity.medium: "Medium",
    Rarity.archive: "Archive",
    Rarity.legendary: "Legendary",
}


@router.callback_query(lambda c: c.data == "players")
async def handle_players(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).order_by(User.prestige.desc()).limit(10)
    )
    users = result.scalars().all()

    if not users:
        await callback.message.answer("Пока нет игроков.", reply_markup=back_to_menu())
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for user in users:
        name = f"@{user.username}" if user.username else user.first_name
        builder.row(InlineKeyboardButton(
            text=f"👤 {name}",
            callback_data=f"player_profile:{user.id}",
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="leaderboard"))
    builder.row(InlineKeyboardButton(text="🌑 Меню", callback_data="menu"))

    try:
        await callback.message.edit_text(
            "Выберите игрока, чтобы открыть его гардероб.",
            reply_markup=builder.as_markup(),
        )
    except Exception:
        await callback.message.answer(
            "Выберите игрока, чтобы открыть его гардероб.",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("player_profile:"))
async def handle_player_profile(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split(":")[1])
    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    # Место в зале
    rank_result = await session.scalar(
        select(func.count()).where(User.prestige > user.prestige)
    )
    rank = (rank_result or 0) + 1

    # Подсчёт вещей по редкости
    items_result = await session.execute(
        select(UserItem).where(UserItem.user_id == user_id)
    )
    user_items = items_result.scalars().all()
    total = len(user_items)

    counts = {r: 0 for r in Rarity}
    for ui in user_items:
        await session.refresh(ui, ["item"])
        counts[ui.item.rarity] += 1

    name = f"@{user.username}" if user.username else user.first_name

    lines = [f"👤 {name}\n"]
    lines.append(f"Prestige: {user.prestige}")
    lines.append(f"Место в Зале GRAIL: #{rank}\n")
    lines.append(f"Всего вещей: {total}")
    for rarity in [Rarity.legendary, Rarity.archive, Rarity.medium, Rarity.base]:
        if counts[rarity]:
            lines.append(f"{RARITY_LABEL[rarity]}: {counts[rarity]}")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="⬛ Открыть гардероб",
        callback_data=f"player_wardrobe:{user_id}:0",
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="players"))

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=builder.as_markup(),
        )
    except Exception:
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("player_wardrobe:"))
async def handle_player_wardrobe(callback: CallbackQuery, session: AsyncSession):
    _, user_id, page_str = callback.data.split(":")
    user_id = int(user_id)
    page = int(page_str)

    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    items_result = await session.execute(
        select(UserItem)
        .where(UserItem.user_id == user_id)
        .order_by(UserItem.obtained_at.desc())
    )
    user_items = items_result.scalars().all()

    if not user_items:
        await callback.answer("Гардероб пуст.", show_alert=True)
        return

    total = len(user_items)
    page = max(0, min(page, total - 1))
    ui = user_items[page]
    await session.refresh(ui, ["item"])
    item = ui.item

    name = f"@{user.username}" if user.username else user.first_name
    label = RARITY_LABEL[item.rarity]
    date_str = ui.obtained_at.strftime("%d.%m")

    archive_lines = ""
    if item.rarity == Rarity.archive:
        stats = await get_archive_stats(item.id, session)
        if item.max_supply is not None:
            archive_lines += f"\n◈ Limited: {item.current_supply}/{item.max_supply}"
        archive_lines += f"\n◈ В коллекциях: {stats['in_collections']}"
        archive_lines += f"\n◈ Редкость среди игроков: {stats['rarity_pct']}%"

    text = (
        f"⬛ Гардероб {name} • {page + 1}/{total}\n\n"
        f"<b>{item.name}</b>\n\n"
        f"Редкость: {label}{archive_lines}\n"
        f"Получено: {date_str}"
    )

    # Навигация
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"player_wardrobe:{user_id}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"player_wardrobe:{user_id}:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ Профиль", callback_data=f"player_profile:{user_id}"))

    if item.image_url:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer_photo(
            item.image_url,
            caption=text,
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
    else:
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()
