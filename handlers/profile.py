from typing import Optional
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from db.models import User
from db.session import async_session_maker
from sqlalchemy import select
import logging
from datetime import datetime, timezone
from config.settings import settings
from aiogram.types import Message as TgMessage
from utils.decorators import db_session, handle_errors

router = Router()
logger = logging.getLogger(__name__)

LANGUAGE_OPTIONS = {"en": "English", "zh": "中文", "es": "Español"}

ADMIN_IDS = settings.admin_ids


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class ProfileStates(StatesGroup):
    CHOICE = State()
    AWAIT_EMAIL = State()
    AWAIT_PHONE = State()


class VerificationStates(StatesGroup):
    AWAIT_VERIFICATION = State()


# ======================
# /profile 查看资料
# ======================
@router.message(Command("profile"))
async def get_user_profile(message: types.Message, state: FSMContext):
    user_id: Optional[int] = getattr(message.from_user, "id", None)
    if not user_id:
        await message.answer("⚠️ 无法获取用户ID")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user: Optional[User] = result.scalar_one_or_none()

        if not user:
            await message.answer("⚠️ 未找到您的用户信息。请先使用 /start 注册。")
            return

        text = (
            f"👤 用户信息：\n"
            f"ID: {user.telegram_id}\n"
            f"用户名: @{user.username or '无'}\n"
            f"邮箱: {user.email or '未设置'}\n"
            f"手机号: {user.phone or '未设置'}\n"
            f"语言: {user.language or '未设置'}\n"
            f"注册时间: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="📧 修改邮箱"),
                    KeyboardButton(text="📱 修改手机号"),
                ],
                [KeyboardButton(text="🌐 修改语言"), KeyboardButton(text="❌ 取消")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await message.answer(text)
        await message.answer("请选择要修改的项目：", reply_markup=keyboard)
        await state.set_state(ProfileStates.CHOICE)


# ======================
# 修改选项选择
# ======================
@router.message(ProfileStates.CHOICE)
async def handle_choice(message: types.Message, state: FSMContext):
    if message.text == "📧 修改邮箱":
        await message.answer("请输入新邮箱：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_EMAIL)
    elif message.text == "📱 修改手机号":
        await message.answer("请输入新手机号：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_PHONE)
    elif message.text == "🌐 修改语言":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=name, callback_data=f"set_lang_{code}")]
                for code, name in LANGUAGE_OPTIONS.items()
            ]
        )
        await message.answer("请选择语言：", reply_markup=keyboard)
        await state.clear()
    elif message.text == "❌ 取消":
        await state.clear()
        await message.answer("操作已取消。", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("无效选项，请重新选择。")


# ======================
# 更新邮箱
# ======================
@router.message(ProfileStates.AWAIT_EMAIL)
async def update_email(message: types.Message, state: FSMContext):
    if not message.text or "@" not in message.text:
        await message.answer("❌ 无效邮箱，请重新输入。")
        return

    user_id: Optional[int] = getattr(message.from_user, "id", None)
    if not user_id:
        await message.answer("⚠️ 无法获取用户ID")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user: Optional[User] = result.scalar_one_or_none()
        if user:
            user.email = message.text.strip()
            await session.commit()
            await message.answer(f"✅ 邮箱已更新为：{user.email}")
        else:
            await message.answer("⚠️ 用户未找到。")
    await state.clear()


# ======================
# 更新手机号
# ======================
@router.message(ProfileStates.AWAIT_PHONE)
async def update_phone(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ 无效手机号，请重新输入。")
        return

    user_id: Optional[int] = getattr(message.from_user, "id", None)
    if not user_id:
        await message.answer("⚠️ 无法获取用户ID")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user: Optional[User] = result.scalar_one_or_none()
        if user:
            user.phone = message.text.strip()
            await session.commit()
            await message.answer(f"✅ 手机号已更新为：{user.phone}")
        else:
            await message.answer("⚠️ 用户未找到。")
    await state.clear()


# ======================
# 语言选择回调
# ======================
@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_callback(callback: types.CallbackQuery):
    data = callback.data or ""  # 确保不是 None
    lang_code: str = data.replace("set_lang_", "")

    user_id: Optional[int] = getattr(callback.from_user, "id", None)
    if not user_id:
        await callback.answer("⚠️ 无法获取用户ID", show_alert=True)
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user: Optional[User] = result.scalar_one_or_none()
        if user:
            user.language = lang_code
            await session.commit()

            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    f"✅ 语言已更新为 {LANGUAGE_OPTIONS.get(lang_code, lang_code)}"
                )
        else:
            await callback.answer("⚠️ 用户未找到。", show_alert=True)

    await callback.answer()


# ======================
# /start 注册入口
# ======================
@router.message(Command("start"))
async def handle_start(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 无法获取用户信息")
        return

    user_id = message.from_user.id
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=user_id,
                username=message.from_user.username,
                created_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.commit()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"set_lang_{code}")]
            for code, name in LANGUAGE_OPTIONS.items()
        ]
    )
    await message.answer("👋 欢迎使用，请选择语言：", reply_markup=keyboard)


@router.message(F.text == "你好")
async def handle_hello(message: Message):
    await message.answer("你也好")


def setup_profile_handlers(router: Router) -> None:

    @router.message(lambda m: m.text == "profile")
    async def profile_info(message: Message):
        await message.answer("这是你的个人信息。")
