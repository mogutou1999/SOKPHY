import functools
import logging
import asyncio
import time
from typing import Callable, Any, Coroutine, TypeVar, Union, Optional, cast
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    User,
)
from config.settings import settings
from handlers.auth import get_or_create_user
from sqlalchemy import select
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import ParamSpec
from contextlib import suppress
from datetime import datetime
from db.models import User as Users
from db.session import async_session_maker
from functools import wraps

logger = logging.getLogger(__name__)
P = ParamSpec("P")
R = TypeVar("R")
router = Router()
_user_cooldown: dict[int, float] = {}

ADMIN_IDS = settings.admin_ids


async def db_check_is_admin(user_id: int) -> bool:
    async with async_session_maker() as session:
        result = await session.execute(
            select(Users.is_admin).where(Users.telegram_id == user_id)
        )
        is_admin = result.scalar_one_or_none()
        return bool(is_admin)


async def test():
    start = datetime.now()
    # 模拟100次并发调用
    tasks = [handle_start(message=..., db=...) for _ in range(100)]
    await asyncio.gather(*tasks)
    print(f"耗时: {(datetime.now() - start).total_seconds():.2f}s")


# --- 核心装饰器 ---
def user_required(
    *,
    check_registration: bool = True,
    cooldown_seconds: int = 0,
    admin_only: bool = False,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, Optional[R]]]
]:
    """
    用户权限和状态检查通用装饰器

    :param check_registration: 是否检查注册
    :param cooldown_seconds: 操作冷却秒数
    :param admin_only: 是否只允许管理员执行
    """

    def decorator(
        handler: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, Optional[R]]]:

        @functools.wraps(handler)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Optional[R]:
            event = next(
                (arg for arg in args if isinstance(arg, (Message, CallbackQuery))), None
            )
            if not event:
                return None

            user = getattr(event, "from_user", None)
            if not user:
                await _safe_reply(event, "⚠️ 用户信息获取失败")
                return None

            if admin_only and user.id not in ADMIN_IDS:
                await _safe_reply(event, "🚫 权限不足，仅限管理员")
                return None

            if cooldown_seconds > 0:
                if remaining := _check_cooldown(user.id, cooldown_seconds):
                    await _safe_reply(event, f"⏳ 请等待 {remaining} 秒后再试")
                    return None

            db = cast(Optional[AsyncSession], kwargs.get("db"))

            if not isinstance(db, AsyncSession):
                await _safe_reply(event, "⚠️ 数据库连接异常")
                return None

            if check_registration:
                try:
                    if not await get_or_create_user(db, user):
                        await _safe_reply(event, "⚠️ 请先使用 /start 注册")
                        return None
                except Exception as e:
                    logger.error(f"[user_required] 注册检查失败: {e}")
                    await _safe_reply(event, "⚠️ 系统错误，请稍后再试")
                    return None

            try:
                return await handler(*args, **kwargs)
            except Exception as e:
                logger.exception(f"[user_required] Handler 执行异常: {e}")
                await _safe_reply(event, "⚠️ 系统异常，请联系管理员")
                return None

        return wrapper

    return decorator


def _check_cooldown(user_id: int, cooldown: int) -> int:
    """计算剩余冷却时间"""
    last_call = _user_cooldown.get(user_id)
    if last_call:
        elapsed = time.time() - last_call
        if elapsed < cooldown:
            return int(cooldown - elapsed)
    _user_cooldown[user_id] = time.time()
    return 0


async def _safe_reply(
    event: Union[Message, CallbackQuery], text: str, **kwargs: Any
) -> None:
    """安全通用回复"""
    try:
        if isinstance(event, Message):
            await event.answer(text, **kwargs)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text, **kwargs)
            with suppress(TelegramBadRequest):
                await event.answer()
    except Exception as e:
        logger.warning(f"[safe_reply] 发送失败: {e}")


# --- 路由处理器示例 ---
@router.message(Command("start"))
@user_required(check_registration=False)
async def handle_start(message: Message, db: AsyncSession, bot: Bot) -> None:
    """处理用户注册"""
    user = cast(User, message.from_user)

    # 创建用户记录
    new_user = await get_or_create_user(db, user)
    if not new_user:
        await message.answer("❌ 注册失败，请重试")
        return

    # 构建响应
    buttons = [[InlineKeyboardButton(text="🛒 开始购物", callback_data="shop")]]
    if not new_user.is_verified:
        buttons.append(
            [InlineKeyboardButton(text="🔐 验证账号", callback_data="verify")]
        )

    await message.answer(
        f"👋 欢迎 {user.full_name}！",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


def log_exceptions(
    handler: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, Optional[R]]]:
    """自动记录异常日志"""

    @functools.wraps(handler)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Optional[R]:
        try:
            return await handler(*args, **kwargs)
        except Exception as e:
            logger.exception(f"[异常捕获] {handler.__name__} 执行失败: {e}")
            event = next(
                (arg for arg in args if isinstance(arg, (Message, CallbackQuery))), None
            )
            if event is not None:
                await _reply(event, "❌ 系统异常，请稍后再试")
            return None

    return wrapper


async def _reply(event: Union[Message, CallbackQuery], text: str) -> None:
    """统一回复函数：适配 Message / CallbackQuery"""
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text)
            await event.answer()
    except Exception as e:
        logger.warning(f"自动回复失败: {e}")


def handle_errors(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            print(f"❌ Error: {e}")

    return wrapper


def db_session(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with async_session_maker() as session:
            return await func(*args, db=session, **kwargs)

    return wrapper
