# utils/decorators.py
import functools
import logging
import asyncio
import time
from typing import Callable, Any, Coroutine, TypeVar, Union, Optional, cast, Sequence
from contextlib import suppress
from datetime import datetime, timezone
from aiogram.types import CallbackQuery, Message
   
from utils.formatting import _safe_reply
from aiogram import Bot, Router
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import User as Users
from db.session import  get_async_session
from config.settings import settings
from handlers.start import handle_start
logger = logging.getLogger(__name__)
router = Router()
_user_cooldown: dict[int, float] = {}

ADMIN_IDS = getattr(settings, "admin_ids", [])

P = TypeVar("P")
R = TypeVar("R")

def db_session(
    func: Callable[..., Coroutine[Any, Any, R]],
) -> Callable[..., Coroutine[Any, Any, R]]:
    """自动创建 AsyncSession"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> R:
        db: Optional[AsyncSession] = kwargs.get("db")
        if db is None:
            async with get_async_session() as session:
                kwargs["db"] = session
                return await func(*args, **kwargs)
        else:
            return await func(*args, **kwargs)

    return wrapper


async def db_check_is_admin(user_id: int) -> bool:
    async with get_async_session() as session:
        result = await session.execute(
            select(Users.is_admin).where(Users.telegram_id == user_id)
        )
        is_admin = result.scalar_one_or_none()
        return bool(is_admin)


async def test():
    start = datetime.now(timezone.utc)
    # 模拟100次并发调用
    tasks = [handle_start(message=..., db=...) for _ in range(100)]
    await asyncio.gather(*tasks)
    print(f"耗时: {(datetime.now(timezone.utc) - start).total_seconds():.2f}s")


# --- 核心装饰器 ---
def user_required(
    *,
    check_registration: bool = True,
    cooldown_seconds: int = 0,
    admin_only: bool = False,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, R]]],
    Callable[..., Coroutine[Any, Any, Optional[R]]],
]:
    """
    用户权限和状态检查通用装饰器
    """

    def decorator(handler: Callable[..., Coroutine[Any, Any, R]]):
        @functools.wraps(handler)
        async def wrapper(*args, **kwargs) -> Optional[R]:
            event = next(
                (arg for arg in args if isinstance(arg, (Message, CallbackQuery))), None
            )
            if not event:
                return None

            user = getattr(event, "from_user", None)
            if not user:
                await safe_reply(event, "⚠️ 用户信息获取失败")
                return None

            if admin_only and user.id not in ADMIN_IDS:
                await safe_reply(event, "🚫 权限不足，仅限管理员")
                return None

            if cooldown_seconds > 0:
                if remaining := _check_cooldown(user.id, cooldown_seconds):
                    await safe_reply(event, f"⏳ 请等待 {remaining} 秒后再试")
                    return None

            db: Optional[AsyncSession] = kwargs.get("db")
            if not isinstance(db, AsyncSession):
                await safe_reply(event, "⚠️ 数据库连接异常")
                return None

            if check_registration:
                try:
                    from handlers.auth import get_or_create_user  # 延迟导入避免循环依赖

                    if not await get_or_create_user(db, user):
                        await safe_reply(event, "⚠️ 请先使用 /start 注册")
                        return None
                except ValueError as e:
                    logger.error(f"[user_required] 注册检查失败: {e}")
                    await safe_reply(event, "⚠️ 系统错误，请稍后再试")
                    return None

            try:
                return await handler(*args, **kwargs)
            except ValueError as e:
                logger.exception(f"[user_required] Handler 执行异常: {e}")
                await safe_reply(event, "⚠️ 系统异常，请联系管理员")
                return None

        return wrapper

    return decorator


# -----------------------------
# 冷却计算
# -----------------------------
def _check_cooldown(user_id: int, cooldown: int) -> int:
    last_call = _user_cooldown.get(user_id)
    if last_call:
        elapsed = time.time() - last_call
        if elapsed < cooldown:
            return int(cooldown - elapsed)
    _user_cooldown[user_id] = time.time()
    return 0


# -----------------------------
# 安全消息发送
# -----------------------------
async def safe_reply(event: Union[Message, CallbackQuery], text: str, **kwargs):
    """
    安全回复函数，支持 Message 和 CallbackQuery 类型。

    :param event: 事件对象，可能是 Message 或 CallbackQuery
    :param text: 回复的文本内容
    """
    try:
        if isinstance(event, Message):
            await event.answer(text, **kwargs)
        elif isinstance(event, CallbackQuery):
            # 回复消息文本
            if event.message:
                message = cast(Message, event.message)  # 显式转换为 Message 类型
                await _safe_reply(message,text, **kwargs)
            # 回答回调，防止 loading 圈圈
            with suppress(Exception):
                await event.answer()
    except ValueError as e:
        logger.warning(f"[safe_reply] 消息发送失败: {e}")



def handle_errors(
    func: Callable[..., Coroutine[Any, Any, R]],
) -> Callable[..., Coroutine[Any, Any, Optional[R]]]:
    """捕获 handler 异常并回复"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Optional[R]:
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            logger.exception(f"[handle_errors] Handler 出错: {e}")
            for arg in args:
                if hasattr(arg, "answer"):
                    await arg.answer("⚠️ 发生错误，请稍后重试", show_alert=True)
            return None

    return wrapper


