# handlers/auth.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from functools import lru_cache
from typing import Optional
import logging
from aiogram import Router, types
from datetime import datetime, timezone
from db.models import User
from db.session import async_session_maker
from config.settings import settings

from typing import Dict


_verification_codes: Dict[int, str] = {}  # 类属性替代全局变量（验证码）


logger = logging.getLogger(__name__)
router = Router()


def setup_auth_handlers(router: Router) -> None:
    auth_router = Router()

    @auth_router.message(commands=["start"])
    async def handle_start(message: types.Message):
        await message.answer("✅ /start 命令收到，auth 正常！")

    router.include_router(auth_router)


@router.message(Command("start"))
async def handle_start(message: types.Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return

    async with async_session_maker() as session:
        try:
            # 原子操作：查询+创建+更新
            user = await get_or_create_user(session, message.from_user)

            # 安全用户名显示
            name = user.first_name or "用户"
            await message.answer(f"👋 欢迎，{name}！")

        except Exception as e:
            await session.rollback()
            logger.exception("Start处理失败")
            await message.answer("❌ 服务暂时不可用")


async def get_or_create_user(session: AsyncSession, tg_user: types.User) -> User:
    """纯异步用户获取/创建"""
    async with session.begin():  # 自动事务管理
        # 先尝试获取已有用户（带行锁）
        stmt = select(User).where(User.telegram_id == tg_user.id).with_for_update()
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                is_admin=tg_user.id in settings.admin_ids,
                created_at=func.now(),  # 数据库服务器时间
            )
            session.add(user)

        # 更新活动时间
        user.last_active = func.now()
        return user


@lru_cache(maxsize=1000, typed=True)
async def get_cached_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """
    带参数验证的异步缓存函数

    参数:
        session: 异步数据库会话
        telegram_id: 必须为正整数

    返回:
        User对象 或 None

    异常:
        ValueError: 当telegram_id无效时
    """
    # 参数验证 (同步执行)
    if not (isinstance(telegram_id, int) and 1 <= telegram_id <= 2**63 - 1):
        raise ValueError(f"Invalid ID: {telegram_id} ")

    # 异步数据库操作
    # async def get_or_create_user(session: AsyncSession, telegram_id: int)-> Optional[User]:
    # AuthService 逻辑保留在 profile 或 services 层，供 handlers 引用

    # services/auth_service.py (建议已废弃，改在 profile 或 auth.py 内定义)

    @staticmethod
    async def is_user_blocked(db: AsyncSession, telegram_id: int) -> bool:
        """检查用户是否被封锁（纯异步）"""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        return user.is_blocked if user else False

    @staticmethod
    async def update_user_activity(db: AsyncSession, user_id: int) -> None:
        """更新用户活动时间（带事务管理）"""
        stmt = select(User).where(User.telegram_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.last_active = datetime.now(timezone.utc)
            await db.commit()
        else:
            await db.rollback()

        # @classmethod
        #  async def generate_verification_code(cls, user_id: int) -> str:
        """生成验证码（模拟异步操作）"""
        #      code = f"{random.randint(100000, 999999)}"
        #      cls._verification_codes[user_id] = code
        #      return code

        #  @classmethod
        #   async def verify_code(cls, user_id: int, code: str) -> bool:
        """验证码校验（内存型）"""


#     return cls._verification_codes.get(user_id) == code
