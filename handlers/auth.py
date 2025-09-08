# handlers/auth.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, Dict
import logging
from datetime import datetime, timezone
from db.models import User
from db.session import get_async_session
from config.settings import settings
from utils.formatting import _safe_reply
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import User as TgUser
from db.models import User as DbUser


logger = logging.getLogger(__name__)
router = Router()

ADMIN_IDS = settings.admin_ids or []


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class VerificationManager:
    """管理用户验证码"""

    _codes: Dict[int, str] = {}

    @classmethod
    def set_code(cls, user_id: int, code: str) -> None:
        cls._codes[user_id] = code

    @classmethod
    def get_code(cls, user_id: int) -> Optional[str]:
        return cls._codes.get(user_id)

    @classmethod
    def delete_code(cls, user_id: int) -> None:
        cls._codes.pop(user_id, None)


@router.message(Command("logout"))
async def logout_demo(message: Message):
    await _safe_reply(message,"👋 这是一个示例登出处理器！")

class RegisterForm(StatesGroup):
    waiting_for_email = State()
    waiting_for_phone = State()

# TODO: 注册流程 /register
@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    await state.set_state(RegisterForm.waiting_for_email)
    await _safe_reply(message, "📧 请输入你的邮箱：")

@router.message(RegisterForm.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    if not message.text:
        await _safe_reply(message, "❌ 邮箱不能为空")
        return
    email = message.text.strip()
    await state.update_data(email=email)
    await state.set_state(RegisterForm.waiting_for_phone)
    await _safe_reply(message, "📱 好的，请输入你的手机号：")


@router.message(RegisterForm.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    if not message.text:
        await _safe_reply(message, "❌ 手机号不能为空")
        return

    if not message.from_user:
        await _safe_reply(message, "⚠️ 无法获取用户信息")
        return

    phone = message.text.strip()
    data = await state.get_data()
    email = data.get("email")

    async with get_async_session() as session:
        async with session.begin():
            stmt = select(User).where(User.telegram_id == message.from_user.id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                user.email = email
                user.phone = phone

    await state.clear()
    await _safe_reply(message, f"✅ 注册成功！\n邮箱: {email}\n手机号: {phone}")

# -------------------------------
# 账户信息
# -------------------------------
@router.message(Command("account"))
async def handle_account(message: Message):
    if not message.from_user:
        await _safe_reply(message, "⚠️ 无法获取用户信息")
        return
    
    async with get_async_session() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            await _safe_reply(message, "⚠️ 你还没有注册，请先使用 /register")
            return

        text = (
            f"👤 账户信息：\n"
            f"ID: {user.telegram_id}\n"
            f"用户名: {user.username or '-'}\n"
            f"邮箱: {user.email or '-'}\n"
            f"手机号: {user.phone or '-'}\n"
            f"语言: {user.language or '未设置'}\n"
            f"注册时间: {user.created_at}\n"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✏ 修改邮箱", callback_data="profile_edit_email")],
                [InlineKeyboardButton(text="📱 修改手机号", callback_data="profile_edit_phone")],
                [InlineKeyboardButton(text="🌐 切换语言", callback_data="profile_edit_language")],
            ]
        )

        await _safe_reply(message, text, reply_markup=kb)

# -------------------------------
# 工具函数
# -------------------------------
async def get_or_create_user(session: AsyncSession, tg_user: TgUser | None) -> DbUser:
    if tg_user is None:
        raise ValueError("Telegram 用户信息为空")
    async with session.begin():
        stmt = select(DbUser).where(DbUser.telegram_id == tg_user.id).with_for_update()
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        now = datetime.now(timezone.utc)

        if not user:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                is_admin=tg_user.id in settings.admin_ids,
                created_at=now,
            )
            session.add(user)

        user.last_active = now
        return user


async def is_user_blocked(db: AsyncSession, telegram_id: int) -> bool:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    return user.is_blocked if user else False


async def update_user_activity(db: AsyncSession, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    async with db.begin():
        stmt = select(User).where(User.telegram_id == user_id).with_for_update()
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.last_active = now


async def get_cached_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
