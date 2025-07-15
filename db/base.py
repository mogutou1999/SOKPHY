# base.py
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column
from sqlalchemy import String

from sqlalchemy import DateTime, func


# ✅ 全局 Base 定义（SQLAlchemy 2.0 风格）
class Base(DeclarativeBase):
    pass


# ✅ 公用 UUIDMixin
class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )


# ✅ 全局时间函数（避免 utcnow 被弃用）
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
