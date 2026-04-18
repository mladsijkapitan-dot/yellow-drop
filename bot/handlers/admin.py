from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete as sa_delete, or_, select as sa_select

from config import ADMIN_IDS
from db.models import Item, Rarity, Trade, TradeStatus, User, UserItem

router = Router()

RARITY_LABEL = {
    Rarity.base: "⚪ Base",
    Rarity.medium: "🔵 Medium",
    Rarity.archive: "🟣 Archive",
    Rarity.legendary: "🟡 Legendary",
}


class AddItem(StatesGroup):
    name = State()
    rarity = State()
    description = State()
    max_supply = State()
    photo = State()


class AddPhoto(StatesGroup):
    waiting = State()


class EditItem(StatesGroup):
    choosing_field = State()
    entering_value = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 К списку вещей", callback_data="admin_list:0"))
    builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))
    return builder.as_markup()


# --- Главное меню админки ---

class Broadcast(StatesGroup):
    waiting_message = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить вещь", callback_data="admin_add"))
    builder.row(InlineKeyboardButton(text="📋 Список вещей", callback_data="admin_list:0"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    await message.answer("👔 Админ-панель GRAIL", reply_markup=builder.as_markup())


# --- Список вещей ---

@router.callback_query(lambda c: c.data and c.data.startswith("admin_list:"))
async def admin_list(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.split(":")[1])
    PAGE_SIZE = 8

    result = await session.execute(select(Item).order_by(Item.rarity, Item.name))
    items = result.scalars().all()

    if not items:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))
        await callback.message.edit_text("Вещей нет.", reply_markup=builder.as_markup())
        await callback.answer()
        return

    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    page_items = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    builder = InlineKeyboardBuilder()
    for item in page_items:
        status = "✓" if item.is_active else "✖"
        builder.row(InlineKeyboardButton(
            text=f"{status} {item.name} ({item.rarity.value})",
            callback_data=f"admin_item:{item.id}",
        ))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"admin_list:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"admin_list:{page + 1}"))
    if nav:
        builder.row(*nav)

    builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))

    try:
        await callback.message.edit_text(
            f"📋 Все вещи ({len(items)} шт):",
            reply_markup=builder.as_markup(),
        )
    except Exception:
        await callback.message.answer(
            f"📋 Все вещи ({len(items)} шт):",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


# --- Карточка вещи ---

@router.callback_query(lambda c: c.data and c.data.startswith("admin_item:"))
async def admin_item(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(callback.data.split(":")[1])
    item = await session.get(Item, item_id)
    if not item:
        await callback.message.edit_text("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    status = "✓ Активна" if item.is_active else "✖ Скрыта"
    supply_line = ""
    if item.rarity.value == "archive" and item.max_supply is not None:
        supply_line = f"\nЛимит: {item.current_supply} / {item.max_supply}"
    text = (
        f"📦 <b>{item.name}</b>\n"
        f"Редкость: {RARITY_LABEL[item.rarity]}\n"
        f"Статус: {status}{supply_line}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_edit:{item_id}:name"))
    builder.row(InlineKeyboardButton(text="✏️ Редкость", callback_data=f"admin_edit:{item_id}:rarity"))
    photo_text = "🖼 Изменить фото" if item.image_url else "🖼 Добавить фото"
    builder.row(InlineKeyboardButton(text=photo_text, callback_data=f"admin_edit:{item_id}:photo"))
    toggle_text = "✖ Скрыть из дропа" if item.is_active else "✓ Включить в дроп"
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle:{item_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete:{item_id}"))
    builder.row(InlineKeyboardButton(text="💀 Удалить из всех гардеробов", callback_data=f"admin_force_delete:{item_id}"))
    builder.row(InlineKeyboardButton(text="◀ К списку", callback_data="admin_list:0"))
    builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


# --- Включить/выключить ---

@router.callback_query(lambda c: c.data and c.data.startswith("admin_toggle:"))
async def admin_toggle(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(callback.data.split(":")[1])
    item = await session.get(Item, item_id)
    if not item:
        await callback.message.edit_text("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    item.is_active = not item.is_active
    await session.commit()

    status = "включена в дроп ✓" if item.is_active else "скрыта из дропа ✖"
    await callback.answer(f"{item.name} {status}", show_alert=True)
    await admin_item(callback, session)


# --- Удалить ---

@router.callback_query(lambda c: c.data and c.data.startswith("admin_delete:"))
async def admin_delete(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(callback.data.split(":")[1])
    item = await session.get(Item, item_id)
    if not item:
        await callback.message.edit_text("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✓ Да, удалить", callback_data=f"admin_delete_confirm:{item_id}"),
        InlineKeyboardButton(text="✖ Отмена", callback_data=f"admin_item:{item_id}"),
    )
    builder.row(InlineKeyboardButton(text="◀ К списку", callback_data="admin_list:0"))

    await callback.message.edit_text(
        f"Удалить <b>{item.name}</b>?",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin_force_delete:"))
async def admin_force_delete(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(callback.data.split(":")[1])
    item = await session.get(Item, item_id)
    if not item:
        await callback.message.edit_text("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💀 Да, удалить везде", callback_data=f"admin_force_delete_confirm:{item_id}"),
        InlineKeyboardButton(text="✖ Отмена", callback_data=f"admin_item:{item_id}"),
    )

    await callback.message.edit_text(
        f"⚠️ Удалить <b>{item.name}</b> из всех гардеробов игроков?\n\nЭто действие необратимо.",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin_force_delete_confirm:"))
async def admin_force_delete_confirm(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(callback.data.split(":")[1])
    item = await session.get(Item, item_id)
    if not item:
        await callback.message.edit_text("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    # 1. Находим все user_item ids для этой вещи
    user_items_result = await session.execute(
        sa_select(UserItem.id).where(UserItem.item_id == item_id)
    )
    user_item_ids = [row[0] for row in user_items_result.all()]

    # 2. Отменяем все трейды где участвуют эти вещи
    if user_item_ids:
        trades_result = await session.execute(
            sa_select(Trade).where(
                or_(
                    Trade.initiator_item_id.in_(user_item_ids),
                    Trade.receiver_item_id.in_(user_item_ids),
                )
            )
        )
        for trade in trades_result.scalars().all():
            trade.status = TradeStatus.cancelled
        await session.flush()

    # 3. Удаляем трейды полностью (чтобы снять FK)
    if user_item_ids:
        await session.execute(
            sa_delete(Trade).where(
                or_(
                    Trade.initiator_item_id.in_(user_item_ids),
                    Trade.receiver_item_id.in_(user_item_ids),
                )
            )
        )
        await session.flush()

    # 4. Удаляем из всех гардеробов
    await session.execute(sa_delete(UserItem).where(UserItem.item_id == item_id))
    await session.flush()

    # 5. Удаляем саму вещь
    await session.delete(item)
    await session.commit()

    await callback.message.edit_text("💀 Вещь удалена из всех гардеробов и из игры.", reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin_delete_confirm:"))
async def admin_delete_confirm(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(callback.data.split(":")[1])
    item = await session.get(Item, item_id)
    if item:
        await session.delete(item)
        await session.commit()

    await callback.message.edit_text("🗑 Вещь удалена.", reply_markup=admin_back_keyboard())
    await callback.answer()


# --- Редактировать поле ---

@router.callback_query(lambda c: c.data and c.data.startswith("admin_edit:"))
async def admin_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    _, item_id, field = callback.data.split(":")

    if field == "rarity":
        builder = InlineKeyboardBuilder()
        for r in Rarity:
            builder.row(InlineKeyboardButton(
                text=RARITY_LABEL[r],
                callback_data=f"admin_set_rarity:{item_id}:{r.value}",
            ))
        builder.row(InlineKeyboardButton(text="◀ Назад", callback_data=f"admin_item:{item_id}"))
        await callback.message.answer("Выбери новую редкость:", reply_markup=builder.as_markup())
        await callback.answer()
        return

    if field == "photo":
        await state.update_data(item_id=int(item_id))
        await state.set_state(AddPhoto.waiting)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data=f"admin_item:{item_id}"))
        await callback.message.answer("Отправь фото для этой вещи:", reply_markup=builder.as_markup())
        await callback.answer()
        return

    await state.update_data(item_id=int(item_id), field=field)
    await state.set_state(EditItem.entering_value)

    field_names = {"name": "название", "description": "описание"}
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data=f"admin_item:{item_id}"))
    await callback.message.answer(
        f"Введи новое {field_names.get(field, field)}:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.message(EditItem.entering_value)
async def admin_edit_value(message: Message, session: AsyncSession, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    item = await session.get(Item, data["item_id"])
    if not item:
        await message.answer("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await state.clear()
        return

    setattr(item, data["field"], message.text.strip())
    await session.commit()
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀ К вещи", callback_data=f"admin_item:{item.id}"))
    builder.row(InlineKeyboardButton(text="📋 К списку", callback_data="admin_list:0"))
    await message.answer(f"✓ Обновлено: {message.text.strip()}", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("admin_set_rarity:"))
async def admin_set_rarity(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        return

    _, item_id, rarity_val = callback.data.split(":")
    item = await session.get(Item, int(item_id))
    if not item:
        await callback.message.edit_text("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    item.rarity = Rarity(rarity_val)
    await session.commit()
    await callback.answer(f"Редкость изменена на {rarity_val}", show_alert=True)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀ К вещи", callback_data=f"admin_item:{item_id}"))
    builder.row(InlineKeyboardButton(text="📋 К списку", callback_data="admin_list:0"))
    await callback.message.edit_text("✓ Редкость обновлена.", reply_markup=builder.as_markup())


# --- Добавить вещь ---

@router.callback_query(lambda c: c.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AddItem.name)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data="admin_menu"))
    await callback.message.answer("Введи название вещи:", reply_markup=builder.as_markup())
    await callback.answer()


@router.message(AddItem.name)
async def admin_add_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.update_data(name=message.text.strip())
    await state.set_state(AddItem.rarity)

    builder = InlineKeyboardBuilder()
    for r in Rarity:
        builder.row(InlineKeyboardButton(text=RARITY_LABEL[r], callback_data=f"admin_pick_rarity:{r.value}"))
    builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data="admin_menu"))

    await message.answer("Выбери редкость:", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("admin_pick_rarity:"))
async def admin_add_rarity(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    rarity_val = callback.data.split(":")[1]
    await state.update_data(rarity=rarity_val)

    if rarity_val == "archive":
        await state.set_state(AddItem.max_supply)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data="admin_menu"))
        await callback.message.answer("Введи лимит выпадения этой Archive-вещи (число, например 50):", reply_markup=builder.as_markup())
    else:
        await state.set_state(AddItem.photo)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="Пропустить фото", callback_data="admin_skip_photo"))
        builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data="admin_menu"))
        await callback.message.answer("Отправь фото карточки вещи или пропусти:", reply_markup=builder.as_markup())
    await callback.answer()


@router.message(AddPhoto.waiting)
async def admin_set_photo(message: Message, session: AsyncSession, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if not message.photo:
        await message.answer("Отправь именно фото (не файл).")
        return

    data = await state.get_data()
    item = await session.get(Item, data["item_id"])
    if not item:
        await message.answer("Вещь не найдена.", reply_markup=admin_back_keyboard())
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    item.image_url = file_id
    await session.commit()
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀ К вещи", callback_data=f"admin_item:{item.id}"))
    builder.row(InlineKeyboardButton(text="📋 К списку", callback_data="admin_list:0"))
    await message.answer(f"✓ Фото для <b>{item.name}</b> сохранено!", parse_mode="HTML", reply_markup=builder.as_markup())


@router.message(AddItem.max_supply)
async def admin_add_max_supply(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Введи целое положительное число (например, 50).")
        return

    await state.update_data(max_supply=int(text))
    await state.set_state(AddItem.photo)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить фото", callback_data="admin_skip_photo"))
    builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data="admin_menu"))
    await message.answer(f"Лимит: {text} шт. Теперь отправь фото или пропусти:", reply_markup=builder.as_markup())


@router.message(AddItem.photo)
async def admin_add_photo(message: Message, session: AsyncSession, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if not message.photo:
        await message.answer("Отправь фото или нажми «Пропустить фото».")
        return

    data = await state.get_data()
    file_id = message.photo[-1].file_id
    item = Item(
        name=data["name"],
        rarity=Rarity(data["rarity"]),
        description="",
        image_url=file_id,
        is_active=True,
        max_supply=data.get("max_supply"),
    )
    session.add(item)
    await session.commit()
    await state.clear()

    supply_note = f"\nLIMITED 0 / {item.max_supply}" if item.max_supply else ""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить ещё", callback_data="admin_add"))
    builder.row(InlineKeyboardButton(text="📋 К списку", callback_data="admin_list:0"))
    builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))
    await message.answer_photo(
        file_id,
        caption=f"✓ Вещь добавлена!\n\n<b>{item.name}</b>\n{RARITY_LABEL[item.rarity]}{supply_note}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data == "admin_skip_photo")
async def admin_skip_photo(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    item = Item(
        name=data["name"],
        rarity=Rarity(data["rarity"]),
        description="",
        is_active=True,
        max_supply=data.get("max_supply"),
    )
    session.add(item)
    await session.commit()
    await state.clear()

    supply_note = f"\nLIMITED 0 / {item.max_supply}" if item.max_supply else ""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить ещё", callback_data="admin_add"))
    builder.row(InlineKeyboardButton(text="📋 К списку", callback_data="admin_list:0"))
    builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))
    await callback.message.edit_text(
        f"✓ Вещь добавлена (без фото)!\n\n<b>{item.name}</b>\n{RARITY_LABEL[item.rarity]}{supply_note}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(Broadcast.waiting_message)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✖ Отмена", callback_data="admin_menu"))
    await callback.message.answer(
        "Отправь сообщение для рассылки.\n\nМожно текст, фото с подписью или просто фото.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.message(Broadcast.waiting_message)
async def admin_broadcast_send(message: Message, session: AsyncSession, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()

    result = await session.execute(sa_select(User.id))
    user_ids = [row[0] for row in result.all()]

    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            if message.photo:
                await message.bot.send_photo(
                    chat_id=user_id,
                    photo=message.photo[-1].file_id,
                    caption=message.caption or "",
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    chat_id=user_id,
                    text=message.text,
                    parse_mode="HTML",
                )
            sent += 1
        except Exception:
            failed += 1

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌑 Меню админа", callback_data="admin_menu"))
    await message.answer(
        f"✓ Рассылка завершена\n\nОтправлено: {sent}\nНе доставлено: {failed}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(lambda c: c.data == "admin_menu")
async def admin_menu_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить вещь", callback_data="admin_add"))
    builder.row(InlineKeyboardButton(text="📋 Список вещей", callback_data="admin_list:0"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    try:
        await callback.message.edit_text("👔 Админ-панель GRAIL", reply_markup=builder.as_markup())
    except Exception:
        await callback.message.answer("👔 Админ-панель GRAIL", reply_markup=builder.as_markup())
    await callback.answer()
