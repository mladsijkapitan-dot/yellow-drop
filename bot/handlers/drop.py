from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import after_drop, back_to_menu, main_menu
from config import RARITY_PRESTIGE
from db.models import Item, Rarity, User
from services.drop import do_drop, get_drop_status

router = Router()

RARITY_EMOJI = {
    Rarity.base: "⚪",
    Rarity.medium: "🔵",
    Rarity.archive: "🟣",
    Rarity.legendary: "🟡",
}

RARITY_LABEL = {
    Rarity.base: "Base",
    Rarity.medium: "Medium",
    Rarity.archive: "Archive",
    Rarity.legendary: "Legendary",
}


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def _format_drop_text(item: Item, total_prestige: int) -> str:
    label = RARITY_LABEL[item.rarity]
    prestige_earned = RARITY_PRESTIGE.get(item.rarity.value, 0)

    if item.rarity == Rarity.archive and item.max_supply is not None:
        supply_line = f"LIMITED {item.current_supply} / {item.max_supply}\n"
        header = "Ты выбил лимитированную Archive-вещь.\n\n"
    else:
        supply_line = ""
        header = "Дроп получен\n\n"

    return (
        f"{header}"
        f"<b>{item.name}</b>\n\n"
        f"Редкость: {label}\n"
        f"{supply_line}"
        f"Начислено: +{prestige_earned} Prestige\n"
        f"Всего Prestige: {total_prestige}"
    )


@router.message(Command("drop"))
async def cmd_drop(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return

    status = await get_drop_status(user)
    if not status["available"]:
        wait = format_time(status["wait_seconds"])
        if status["reason"] == "daily_limit":
            await message.answer(f"На сегодня дропы закончились 😴\nСледующие через {wait}", reply_markup=main_menu())
        else:
            await message.answer(f"⏳ Следующий дроп через {wait}", reply_markup=main_menu())
        return

    item = await do_drop(user, session)
    if not item:
        await message.answer("Попробуй ещё раз.", reply_markup=main_menu())
        return

    await session.refresh(user)
    await session.refresh(item)
    text = _format_drop_text(item, user.prestige)
    if item.image_url:
        await message.answer_photo(item.image_url, caption=text, parse_mode="HTML", reply_markup=after_drop())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=after_drop())


@router.callback_query(lambda c: c.data == "drop")
async def handle_drop(callback: CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Сначала напиши /start", show_alert=True)
        return

    status = await get_drop_status(user)

    if not status["available"]:
        wait = format_time(status["wait_seconds"])
        if status["reason"] == "daily_limit":
            await callback.answer(
                f"На сегодня дропы закончились 😴\nСледующие через {wait}",
                show_alert=True,
            )
        else:
            await callback.answer(
                f"⏳ Следующий дроп через {wait}",
                show_alert=True,
            )
        return

    await callback.answer("✦ Крутим...")

    item = await do_drop(user, session)
    if not item:
        await callback.message.answer("Попробуй ещё раз — что-то пошло не так.", reply_markup=back_to_menu())
        return

    await session.refresh(user)
    await session.refresh(item)
    text = _format_drop_text(item, user.prestige)

    if item.image_url:
        await callback.message.answer_photo(item.image_url, caption=text, parse_mode="HTML", reply_markup=after_drop())
    else:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=after_drop())


@router.callback_query(lambda c: c.data == "menu")
async def handle_menu(callback: CallbackQuery):
    await callback.message.answer("👋 Добро пожаловать в главное меню GRAIL!\n\nЗдесь вы можете открыть дроп, перейти в гардероб или посмотреть свои трейды.\n\nВыберите нужный раздел ниже.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(lambda c: c.data == "noop")
async def handle_noop(callback: CallbackQuery):
    await callback.answer()
