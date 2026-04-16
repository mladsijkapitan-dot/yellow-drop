from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import TRADE_EXPIRE_HOURS, TRADE_MAX_ACTIVE
from db.models import Trade, TradeStatus, UserItem


async def get_user_items(user_id: int, session: AsyncSession) -> list[UserItem]:
    result = await session.execute(
        select(UserItem)
        .where(UserItem.user_id == user_id)
        .order_by(UserItem.obtained_at.desc())
    )
    return result.scalars().all()


async def count_active_trades(user_id: int, session: AsyncSession) -> int:
    result = await session.execute(
        select(Trade).where(
            and_(
                or_(Trade.initiator_id == user_id, Trade.receiver_id == user_id),
                Trade.status == TradeStatus.pending,
            )
        )
    )
    return len(result.scalars().all())


async def create_trade(
    initiator_id: int,
    receiver_id: int,
    initiator_item_id: int,
    receiver_item_id: int,
    session: AsyncSession,
) -> Trade | str:
    """Создаёт трейд. Возвращает Trade или строку с ошибкой."""
    # Проверить лимит активных трейдов
    if await count_active_trades(initiator_id, session) >= TRADE_MAX_ACTIVE:
        return "too_many_trades"

    # Проверить что вещи принадлежат нужным людям и не залочены
    init_item = await session.get(UserItem, initiator_item_id)
    recv_item = await session.get(UserItem, receiver_item_id)

    if not init_item or init_item.user_id != initiator_id or init_item.is_locked:
        return "invalid_initiator_item"
    if not recv_item or recv_item.user_id != receiver_id or recv_item.is_locked:
        return "invalid_receiver_item"

    # Залочить обе вещи
    init_item.is_locked = True
    recv_item.is_locked = True

    trade = Trade(
        initiator_id=initiator_id,
        receiver_id=receiver_id,
        initiator_item_id=initiator_item_id,
        receiver_item_id=receiver_item_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=TRADE_EXPIRE_HOURS),
    )
    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    return trade


async def accept_trade(trade_id: int, user_id: int, session: AsyncSession) -> Trade | str:
    """Принимает трейд. Атомарно меняет владельцев вещей."""
    trade = await session.get(Trade, trade_id)
    if not trade:
        return "not_found"
    if trade.receiver_id != user_id:
        return "not_your_trade"
    if trade.status != TradeStatus.pending:
        return "not_pending"
    if trade.expires_at < datetime.now(timezone.utc):
        await _expire_trade(trade, session)
        return "expired"

    init_item = await session.get(UserItem, trade.initiator_item_id)
    recv_item = await session.get(UserItem, trade.receiver_item_id)

    # Атомарный обмен
    init_item.user_id = trade.receiver_id
    recv_item.user_id = trade.initiator_id
    init_item.is_locked = False
    recv_item.is_locked = False
    trade.status = TradeStatus.accepted

    await session.commit()
    return trade


async def decline_trade(trade_id: int, user_id: int, session: AsyncSession) -> Trade | str:
    trade = await session.get(Trade, trade_id)
    if not trade:
        return "not_found"
    if trade.receiver_id != user_id:
        return "not_your_trade"
    if trade.status != TradeStatus.pending:
        return "not_pending"

    await _unlock_and_update(trade, TradeStatus.declined, session)
    return trade


async def cancel_trade(trade_id: int, user_id: int, session: AsyncSession) -> Trade | str:
    trade = await session.get(Trade, trade_id)
    if not trade:
        return "not_found"
    if trade.initiator_id != user_id:
        return "not_your_trade"
    if trade.status != TradeStatus.pending:
        return "not_pending"

    await _unlock_and_update(trade, TradeStatus.cancelled, session)
    return trade


async def _expire_trade(trade: Trade, session: AsyncSession):
    await _unlock_and_update(trade, TradeStatus.expired, session)


async def _unlock_and_update(trade: Trade, status: TradeStatus, session: AsyncSession):
    init_item = await session.get(UserItem, trade.initiator_item_id)
    recv_item = await session.get(UserItem, trade.receiver_item_id)
    if init_item:
        init_item.is_locked = False
    if recv_item:
        recv_item.is_locked = False
    trade.status = status
    await session.commit()
