from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎁 Дроп", callback_data="drop"),
        InlineKeyboardButton(text="👔 Гардероб", callback_data="wardrobe:0"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Мои трейды", callback_data="trades"),
        InlineKeyboardButton(text="✨ Зал Престижа", callback_data="leaderboard"),
    )
    return builder.as_markup()


def wardrobe_nav(page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"wardrobe:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"wardrobe:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="🔄 Предложить трейд", callback_data=f"trade_init:{page}"))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    return builder.as_markup()


def trade_confirm(initiator_item_id: int, receiver_id: int, receiver_item_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=f"trade_confirm:{initiator_item_id}:{receiver_id}:{receiver_item_id}",
        ),
        InlineKeyboardButton(text="❌ Отмена", callback_data="menu"),
    )
    return builder.as_markup()


def trade_respond(trade_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"trade_accept:{trade_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"trade_decline:{trade_id}"),
    )
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu"))
    return builder.as_markup()
