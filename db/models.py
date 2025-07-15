import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
import enum
from sqlalchemy import String, Integer, Boolean, DateTime, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from datetime import datetime
from db.roles import Role
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Numeric,
    Float,
    Integer,
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Boolean

from db.base import Base, UUIDMixin, utcnow, TimestampMixin
from db.roles import Role


class OrderStatus(enum.Enum):
    PENDING = "pending"
    UNPAID = "unpaid"
    PAID = "paid"
    SHIPPED = "shipped"
    REFUNDED = "refunded"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    age: Mapped[Optional[int]] = mapped_column(Integer)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    language: Mapped[Optional[str]] = mapped_column(String(10))
    is_blocked: Mapped[bool] = mapped_column(default=False)
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)  # ✅ 添加这行
    role: Mapped[Role] = mapped_column(SqlEnum(Role), default=Role.USER.value)

    phone: Mapped[Optional[str]] = mapped_column(String(20))
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cart_items: Mapped[List["CartItem"]] = relationship(back_populates="user")
    orders: Mapped[List["Order"]] = relationship(back_populates="user")
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stock: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    cart_items: Mapped[List["CartItem"]] = relationship(back_populates="product")
    order_items: Mapped[List["OrderItem"]] = relationship(back_populates="product")


class CartItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # ✅ 这些字段要有
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")


class Order(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "orders"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, default=OrderStatus.UNPAID.value)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order")


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")
