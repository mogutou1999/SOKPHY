# base.py
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column
from sqlalchemy import String
from typing import Annotated
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import enum

# 类型注解简化（SQLAlchemy 2.0+）
UUID_PK = Annotated[uuid.UUID, mapped_column(primary_key=True)]
TIMESTAMP = Annotated[datetime, mapped_column(DateTime(timezone=True))]


# ✅ 全局 Base 定义（SQLAlchemy 2.0 风格）
class Base(DeclarativeBase):
    pass


# ✅ 公用 UUIDMixin
class UUIDMixin:
    id: Mapped[UUID_PK] = mapped_column(
        PG_UUID(as_uuid=True) if PG_UUID else String(36),
        default=uuid.uuid4,
        index=True,
        comment="主键UUID",
    )


# ✅ 全局时间函数（避免 utcnow 被弃用）
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[TIMESTAMP] = mapped_column(
        server_default=func.now(),  # 使用数据库时间而非应用时间
        nullable=False,
        comment="创建时间(UTC)",
    )

    updated_at: Mapped[TIMESTAMP] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),  # 自动更新
        nullable=False,
        comment="最后更新时间(UTC)",
    )
