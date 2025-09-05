# db/models.py
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import String, Integer, Numeric, ForeignKey, Text, DateTime,Enum as SQLEnum,Boolean,BigInteger
from sqlalchemy.sql import func
from db.base import Base, UUIDMixin, TimestampMixin
import enum
import bcrypt

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    UNPAID = "unpaid"
    PAID = "paid"
    SHIPPED = "shipped"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

class Role(str, enum.Enum):
    """用户角色枚举"""

    USER = "user"
    ADMIN = "admin"
    MANAGER = "manager"
    GUEST = "guest"
    SUPERADMIN = "superadmin"
    
# ===============================
# 用户表
# ===============================
class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(nullable=False)
    age: Mapped[Optional[int]] = mapped_column(Integer)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    language: Mapped[Optional[str]] = mapped_column(String(10))
    is_blocked: Mapped[bool] = mapped_column(default=False)
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_admin: Mapped[bool] = mapped_column(default=False)
    role: Mapped[Role] = mapped_column(SQLEnum(Role, name="role_enum"), default=Role.USER, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    _password: Mapped[Optional[str]] = mapped_column("password", String(255), nullable=True)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    first_name: Mapped[Optional[str]] = mapped_column(String(50))
    last_name: Mapped[Optional[str]] = mapped_column(String(50))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)

    cart_items: Mapped[List["CartItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship(back_populates="user")

    # -----------------------------
    # 设置密码时自动加密
    # -----------------------------
    @property
    def password(self) -> Optional[str]:
        return self._password

    @password.setter
    def password(self, raw_password: str):
        if raw_password:
            hashed = bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt())
            self._password = hashed.decode()
        else:
            self._password = None

    # -----------------------------
    # 验证密码
    # -----------------------------
    def verify_password(self, raw_password: str) -> bool:
        if not self._password:
            return False
        return bcrypt.checkpw(raw_password.encode(), self._password.encode())

# ──────────────────────────────
# ✅ 商品表
# ──────────────────────────────
class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"

    # 删除了 int 主键，使用 UUIDMixin 中的 id

    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    sales: Mapped[int] = mapped_column(Integer, default=0)

    cart_items: Mapped[List["CartItem"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    order_items: Mapped[List["OrderItem"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_file_id: Mapped[Optional[str]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

# ──────────────────────────────
# ✅ 购物车表
# ──────────────────────────────
class CartItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cart_items"

    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    product_name: Mapped[str] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="cart_items")
    product: Mapped["Product"] = relationship(back_populates="cart_items")


# ──────────────────────────────
# ✅ 订单表
# ──────────────────────────────
class Order(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "orders"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[OrderStatus] = mapped_column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_paid: Mapped[bool] = mapped_column(default=False)
    payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    out_no: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


# ──────────────────────────────
# ✅ 订单商品表
# ──────────────────────────────
class OrderItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "order_items"

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")


class Config(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "configs"

    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
