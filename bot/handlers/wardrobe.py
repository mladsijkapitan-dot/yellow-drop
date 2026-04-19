from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import back_to_menu, wardrobe_nav
from db.models import Rarity, UserItem
from services.drop import get_archive_stats
from services.trade import get_user_items

router = Router()

RARITY_LABEL = {
    Rarity.base: "Base",
    Rarity.medium: "Medium",
    Rarity.archive: "Archive",
    Rarity.legendary: "Legendary",
}

BURN_PRESTIGE = 100


def _wardrobe_keyboard(page: int, total: int, ui_id: int, is_archive: bool, is_locked: bool):
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"wardrobe:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"wardrobe:{page + 1}"))
    builder.row(*nav)
    if not is_locked:
        builder.row(InlineKeyboardButton(text="🔄 Предложить трейд", callback_data=f"trade_init:{page}"))
        if is_archive:
            builder.row(InlineKeyboardButton(text="◈ Сжечь Archive", callback_data=f"burn_confirm:{ui_id}:{page}"))
    builder.row(InlineKeyboardButton(text="🌑 Меню", callback_data="menu"))
    return builder.as_markup()


@router.callback_query(lambda c: c.data and c.data.startswith("wardrobe:"))
async def handle_wardrobe(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1])
    user_items = await get_user_items(callback.from_user.id, session)

    if not user_items:
        await callback.message.answer(
            "Твой гардероб пуст\nПолучи первый дроп!",
            reply_markup=back_to_menu(),
        )
        await callback.answer()
        return

    total = len(user_items)
    page = max(0, min(page, total - 1))
    ui = user_items[page]

    await session.refresh(ui, ["item"])
    item = ui.item

    label = RARITY_LABEL[item.rarity]
    lock_badge = " 🔒" if ui.is_locked else ""
    date_str = ui.obtained_at.strftime("%d.%m")

    archive_lines = ""
    if item.rarity == Rarity.archive:
        stats = await get_archive_stats(item.id, session)
        if item.max_supply is not None:
            archive_lines += f"\n◈ Limited: {item.current_supply}/{item.max_supply}"
        archive_lines += f"\n◈ В коллекциях: {stats['in_collections']}"
        archive_lines += f"\n◈ Редкость среди игроков: {stats['rarity_pct']}%"

    text = (
        f"⬛ Гардероб • {page + 1}/{total}\n\n"
        f"<b>{item.name}</b>{lock_badge}\n\n"
        f"Редкость: {label}{archive_lines}\n"
        f"Получено: {date_str}"
    )

    keyboard = _wardrobe_keyboard(page, total, ui.id, item.rarity == Rarity.archive, ui.is_locked)

    if item.image_url:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer_photo(item.image_url, caption=text, parse_mode="HTML", reply_markup=keyboard)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("burn_confirm:"))
async def burn_confirm(callback: CallbackQuery, session: AsyncSession):
    _, ui_id, page = callback.data.split(":")
    ui = await session.get(UserItem, int(ui_id))
    if not ui or ui.user_id != callback.from_user.id:
        await callback.answer("Вещь не найдена.", show_alert=True)
        return
    if ui.is_locked:
        await callback.answer("Вещь заблокирована трейдом 🔒", show_alert=True)
        return

    await session.refresh(ui, ["item"])

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✓ Сжечь", callback_data=f"burn_do:{ui_id}:{page}"),
        InlineKeyboardButton(text="✖ Отмена", callback_data=f"wardrobe:{page}"),
    )

    text = (
        f"◈ Сжечь Archive\n\n"
        f"Вы действительно хотите сжечь эту Archive-вещь?\n\n"
        f"<b>{ui.item.name}</b>\n\n"
        f"После сжигания она навсегда исчезнет из вашей коллекции.\n\n"
        f"Награда: +{BURN_PRESTIGE} Prestige"
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("burn_do:"))
async def burn_do(callback: CallbackQuery, session: AsyncSession):
    _, ui_id, page = callback.data.split(":")
    ui = await session.get(UserItem, int(ui_id))
    if not ui or ui.user_id != callback.from_user.id:
        await callback.answer("Вещь не найдена.", show_alert=True)
        return
    if ui.is_locked:
        await callback.answer("Вещь заблокирована трейдом 🔒", show_alert=True)
        return

    from db.models import User
    user = await session.get(User, callback.from_user.id)
    user.prestige += BURN_PRESTIGE

    await session.delete(ui)
    await session.commit()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬛ Гардероб", callback_data=f"wardrobe:{max(0, int(page) - 1)}"))
    builder.row(InlineKeyboardButton(text="🌑 Меню", callback_data="menu"))

    text = (
        f"Вещь выведена из активных коллекций.\n\n"
        f"Получено: +{BURN_PRESTIGE} Prestige\n"
        f"Всего Prestige: {user.prestige}"
    )

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()
