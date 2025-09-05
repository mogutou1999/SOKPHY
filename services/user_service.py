# services/user_service.py
from db.session import get_async_session
from db.models import User, Role
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

async def db_get_user(telegram_id: int) -> Optional[User]:
    """根据 Telegram ID 获取用户"""
    async with get_async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


def is_admin(user: Optional[User]) -> bool:
    """判断用户是否是管理员"""
    if not user:
        return False
    return user.role in (Role.ADMIN, Role.SUPERADMIN)
