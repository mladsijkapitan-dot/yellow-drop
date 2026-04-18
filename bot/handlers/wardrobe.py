from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import back_to_menu, wardrobe_nav
from db.models import Rarity
from services.drop import get_archive_stats
from services.trade import get_user_items

router = Router()

RARITY_LABEL = {
    Rarity.base: "Base",
    Rarity.medium: "Medium",
    Rarity.archive: "Archive",
    Rarity.legendary: "Legendary",
}


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

    if item.image_url:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer_photo(
            item.image_url,
            caption=text,
            parse_mode="HTML",
            reply_markup=wardrobe_nav(page, total),
        )
    else:
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=wardrobe_nav(page, total),
            )
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=wardrobe_nav(page, total))
    await callback.answer()
