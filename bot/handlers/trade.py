from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import back_to_menu, trade_confirm, trade_respond
from db.models import Rarity, Trade, TradeStatus, User, UserItem
from services.trade import (
    accept_trade,
    cancel_trade,
    decline_trade,
    create_trade,
    get_user_items,
)

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


class TradeFlow(StatesGroup):
    waiting_for_username = State()
    waiting_for_receiver_item = State()


# --- Инициация трейда из гардероба ---

@router.callback_query(lambda c: c.data and c.data.startswith("trade_init:"))
async def trade_init(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    page = int(callback.data.split(":")[1])
    user_items = await get_user_items(callback.from_user.id, session)

    if not user_items:
        await callback.answer("Нет вещей для трейда.", show_alert=True)
        return

    ui = user_items[page]
    if ui.is_locked:
        await callback.answer("Эта вещь уже в трейде 🔒", show_alert=True)
        return

    await session.refresh(ui, ["item"])
    await state.update_data(initiator_item_id=ui.id, initiator_item_name=ui.item.name)
    await state.set_state(TradeFlow.waiting_for_username)

    await callback.message.answer(
        f"Ты предлагаешь: <b>{ui.item.name}</b>\n\n"
        f"Введи @username получателя:",
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


@router.message(TradeFlow.waiting_for_username)
async def trade_get_username(message: Message, session: AsyncSession, state: FSMContext):
    raw = message.text.strip().lstrip("@")
    result = await session.execute(select(User).where(User.username == raw))
    receiver = result.scalar_one_or_none()

    if not receiver:
        await message.answer("Игрок не найден. Проверь username или попроси его написать /start.", reply_markup=back_to_menu())
        return
    if receiver.id == message.from_user.id:
        await message.answer("Нельзя торговать с собой 😄", reply_markup=back_to_menu())
        return

    # Показываем вещи получателя (последние 10, не залоченные)
    recv_items = await get_user_items(receiver.id, session)
    recv_items = [ui for ui in recv_items if not ui.is_locked][:10]

    if not recv_items:
        await message.answer(f"У @{raw} нет доступных вещей для обмена.", reply_markup=back_to_menu())
        await state.clear()
        return

    await state.update_data(receiver_id=receiver.id, receiver_username=raw)
    await state.set_state(TradeFlow.waiting_for_receiver_item)

    builder = InlineKeyboardBuilder()
    for ui in recv_items:
        await session.refresh(ui, ["item"])
        emoji = RARITY_EMOJI[ui.item.rarity]
        builder.row(InlineKeyboardButton(
            text=f"{emoji} {ui.item.name} ({RARITY_LABEL[ui.item.rarity]})",
            callback_data=f"pick_recv_item:{ui.id}",
        ))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_trade_flow"))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))

    data = await state.get_data()
    await message.answer(
        f"Выбери вещь @{raw}, которую хочешь получить взамен за <b>{data['initiator_item_name']}</b>:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("pick_recv_item:"))
async def trade_pick_receiver_item(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    recv_item_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    recv_item = await session.get(UserItem, recv_item_id)
    if not recv_item:
        await callback.answer("Вещь не найдена.", show_alert=True)
        return

    await session.refresh(recv_item, ["item"])

    init_item = await session.get(UserItem, data["initiator_item_id"])
    await session.refresh(init_item, ["item"])

    text = (
        f"Подтверди трейд:\n\n"
        f"Ты отдаёшь: <b>{init_item.item.name}</b>\n"
        f"Ты получаешь: <b>{recv_item.item.name}</b> от @{data['receiver_username']}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=trade_confirm(
            data["initiator_item_id"],
            data["receiver_id"],
            recv_item_id,
        ),
    )
    await state.clear()
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("trade_confirm:"))
async def trade_confirm_handler(callback: CallbackQuery, session: AsyncSession):
    _, init_item_id, receiver_id, recv_item_id = callback.data.split(":")
    result = await create_trade(
        initiator_id=callback.from_user.id,
        receiver_id=int(receiver_id),
        initiator_item_id=int(init_item_id),
        receiver_item_id=int(recv_item_id),
        session=session,
    )

    if isinstance(result, str):
        errors = {
            "too_many_trades": "У тебя слишком много активных трейдов (макс. 5).",
            "invalid_initiator_item": "Твоя вещь недоступна для трейда.",
            "invalid_receiver_item": "Вещь получателя недоступна для трейда.",
        }
        await callback.message.edit_text(errors.get(result, "Ошибка создания трейда."), reply_markup=back_to_menu())
        await callback.answer()
        return

    # Уведомить получателя
    init_item = await session.get(UserItem, result.initiator_item_id)
    recv_item = await session.get(UserItem, result.receiver_item_id)
    await session.refresh(init_item, ["item"])
    await session.refresh(recv_item, ["item"])

    try:
        await callback.bot.send_message(
            chat_id=result.receiver_id,
            text=(
                f"🔄 Новый трейд!\n\n"
                f"@{callback.from_user.username or callback.from_user.first_name} предлагает:\n"
                f"Отдаёт: <b>{init_item.item.name}</b>\n"
                f"Хочет: твой <b>{recv_item.item.name}</b>"
            ),
            parse_mode="HTML",
            reply_markup=trade_respond(result.id),
        )
    except Exception:
        pass  # Пользователь мог заблокировать бота

    await callback.message.edit_text(
        f"✅ Трейд отправлен! Ждём ответа.\n\nID трейда: #{result.id}",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


# --- Принятие / отклонение ---

@router.callback_query(lambda c: c.data and c.data.startswith("trade_accept:"))
async def trade_accept_handler(callback: CallbackQuery, session: AsyncSession):
    trade_id = int(callback.data.split(":")[1])
    result = await accept_trade(trade_id, callback.from_user.id, session)

    if isinstance(result, str):
        msgs = {
            "not_found": "Трейд не найден.",
            "not_your_trade": "Это не твой трейд.",
            "not_pending": "Трейд уже завершён.",
            "expired": "Трейд истёк ⌛",
        }
        await callback.message.edit_text(msgs.get(result, "Ошибка."), reply_markup=back_to_menu())
        await callback.answer()
        return

    # Получаем вещи для уведомления
    init_item = await session.get(UserItem, result.initiator_item_id)
    recv_item = await session.get(UserItem, result.receiver_item_id)
    await session.refresh(init_item, ["item"])
    await session.refresh(recv_item, ["item"])

    await callback.message.edit_text(
        f"✅ Трейд принят!\nТы получил: <b>{init_item.item.name}</b>",
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )

    try:
        await callback.bot.send_message(
            chat_id=result.initiator_id,
            text=f"✅ Твой трейд #{result.id} принят!\nТы получил: <b>{recv_item.item.name}</b>",
            parse_mode="HTML",
            reply_markup=back_to_menu(),
        )
    except Exception:
        pass

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("trade_decline:"))
async def trade_decline_handler(callback: CallbackQuery, session: AsyncSession):
    trade_id = int(callback.data.split(":")[1])
    result = await decline_trade(trade_id, callback.from_user.id, session)

    if isinstance(result, str):
        await callback.message.edit_text("Не удалось отклонить трейд.", reply_markup=back_to_menu())
        await callback.answer()
        return

    await callback.message.edit_text(
        "❌ Трейд отклонён.",
        reply_markup=back_to_menu(),
    )

    try:
        await callback.bot.send_message(
            chat_id=result.initiator_id,
            text=f"❌ Трейд #{result.id} отклонён.",
            reply_markup=back_to_menu(),
        )
    except Exception:
        pass

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("trade_cancel:"))
async def trade_cancel_handler(callback: CallbackQuery, session: AsyncSession):
    trade_id = int(callback.data.split(":")[1])
    result = await cancel_trade(trade_id, callback.from_user.id, session)

    if isinstance(result, str):
        msgs = {
            "not_found": "Трейд не найден.",
            "not_your_trade": "Это не твой трейд.",
            "not_pending": "Трейд уже завершён.",
        }
        await callback.message.edit_text(msgs.get(result, "Ошибка."), reply_markup=back_to_menu())
        await callback.answer()
        return

    await callback.message.edit_text("✅ Трейд отменён.", reply_markup=back_to_menu())

    try:
        await callback.bot.send_message(
            chat_id=result.receiver_id,
            text=f"❌ Трейд #{result.id} был отменён отправителем.",
            reply_markup=back_to_menu(),
        )
    except Exception:
        pass

    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_trade_flow")
async def cancel_trade_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=back_to_menu())
    await callback.answer()


# --- Список трейдов ---

@router.callback_query(lambda c: c.data == "trades")
async def handle_trades(callback: CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    result = await session.execute(
        select(Trade).where(
            ((Trade.initiator_id == user_id) | (Trade.receiver_id == user_id)),
            Trade.status == TradeStatus.pending,
        ).order_by(Trade.created_at.desc())
    )
    trades = result.scalars().all()

    if not trades:
        await callback.message.answer("Нет активных трейдов.", reply_markup=back_to_menu())
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for trade in trades:
        if trade.initiator_id == user_id:
            builder.row(InlineKeyboardButton(
                text=f"❌ Отменить трейд #{trade.id} (исходящий)",
                callback_data=f"trade_cancel:{trade.id}",
            ))
        else:
            builder.row(InlineKeyboardButton(
                text=f"❌ Отклонить трейд #{trade.id} (входящий)",
                callback_data=f"trade_decline:{trade.id}",
            ))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))

    await callback.message.answer(
        f"Активные трейды ({len(trades)}):",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
