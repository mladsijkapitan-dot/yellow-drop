import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Integer, SmallInteger, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Rarity(str, enum.Enum):
    base = "base"
    medium = "medium"
    archive = "archive"
    legendary = "legendary"


class TradeStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    drop_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_drop_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prestige: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list["UserItem"]] = relationship(back_populates="user")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity))
    description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_supply: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = безлимит
    current_supply: Mapped[int] = mapped_column(Integer, default=0)
    burned_count: Mapped[int] = mapped_column(Integer, default=0)


class UserItem(Base):
    __tablename__ = "user_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"))
    obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="items")
    item: Mapped["Item"] = relationship()


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    initiator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    receiver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    initiator_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_items.id"))
    receiver_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_items.id"))
    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus), default=TradeStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    initiator: Mapped["User"] = relationship(foreign_keys=[initiator_id])
    receiver: Mapped["User"] = relationship(foreign_keys=[receiver_id])
    initiator_item: Mapped["UserItem"] = relationship(foreign_keys=[initiator_item_id])
    receiver_item: Mapped["UserItem"] = relationship(foreign_keys=[receiver_item_id])
