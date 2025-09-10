# handlers/profile.py
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
    Message as TgMessage,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from db.models import User
from db.session import get_async_session
from sqlalchemy import select
import logging
from utils.formatting import _safe_reply
from datetime import datetime, timezone
from config.settings import settings
from utils.decorators import db_session, handle_errors

router = Router()
logger = logging.getLogger(__name__)

LANGUAGE_OPTIONS = {"en": "English", "zh": "中文", "es": "Español"}

ADMIN_IDS = []

class ProfileStates(StatesGroup):
    CHOICE = State()
    AWAIT_EMAIL = State()
    AWAIT_PHONE = State()
    
class VerificationStates(StatesGroup):
    AWAIT_VERIFICATION = State()
# -----------------------------
# 获取用户对象
# -----------------------------
async def get_user(session, user_id: int) -> Optional[User]:
    try:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        return result.scalar_one_or_none()
    except ValueError as e:
        logger.exception(f"获取用户 {user_id} 失败: {e}")
        return None
    
def get_user_id(obj: types.Message | types.CallbackQuery) -> Optional[int]:
    return getattr(obj.from_user, "id", None)    
# ======================
# /profile 查看资料
# ======================
@router.message(Command("profile"))
async def get_user_profile(message: types.Message, state: FSMContext):
    user_id = get_user_id(message)
    if not user_id:
        await _safe_reply(message, "⚠️ 无法获取用户ID")
        return

    async with get_async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user: Optional[User] = result.scalar_one_or_none()

        if not user:
            await _safe_reply(message, "⚠️ 未找到您的用户信息。请先使用 /start 注册。")
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
                [KeyboardButton(text="📧 修改邮箱"), KeyboardButton(text="📱 修改手机号")],
                [KeyboardButton(text="🌐 修改语言"), KeyboardButton(text="❌ 取消")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await _safe_reply(message, text)
        await _safe_reply(message, "请选择要修改的项目：", reply_markup=keyboard)
        await state.set_state(ProfileStates.CHOICE)


# ======================
# 修改选项选择
# ======================
@router.message(ProfileStates.CHOICE)
async def handle_choice(message: types.Message, state: FSMContext):
    if message.text == "📧 修改邮箱":
        await _safe_reply(message, "请输入新邮箱：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_EMAIL)
    elif message.text == "📱 修改手机号":
        await _safe_reply(message, "请输入新手机号：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_PHONE)
    elif message.text == "🌐 修改语言":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=name, callback_data=f"set_lang_{code}")] for code, name in LANGUAGE_OPTIONS.items()]
        )
        await _safe_reply(message, "请选择语言：", reply_markup=keyboard)
        await state.clear()
    elif message.text == "❌ 取消":
        await state.clear()
        await _safe_reply(message, "操作已取消。", reply_markup=ReplyKeyboardRemove())
    else:
        await _safe_reply(message, "无效选项，请重新选择。")




# ======================
# 更新邮箱
# ======================
@router.message(ProfileStates.AWAIT_EMAIL)
async def update_email(message: types.Message, state: FSMContext):
    if not message.text or "@" not in message.text:
        await _safe_reply(message, "❌ 无效邮箱，请重新输入。")
        return
    user_id = get_user_id(message)
    if not user_id:
        await _safe_reply(message, "⚠️ 无法获取用户ID")
        return
    async with get_async_session() as session:
        user = await get_user(session, user_id)
        if not user:
            await _safe_reply(message, "⚠️ 用户未找到。")
        else:
            user.email = message.text.strip()
            await session.commit()
            await _safe_reply(message, f"✅ 邮箱已更新为：{user.email}")

    await state.clear()



# ======================
# 更新手机号
# ======================
@router.message(ProfileStates.AWAIT_PHONE)
async def update_phone(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await _safe_reply(message, "❌ 无效手机号，请重新输入。")
        return
    user_id = get_user_id(message)
    if not user_id:
        await _safe_reply(message, "⚠️ 无法获取用户ID")
        return
    async with get_async_session() as session:
        user = await get_user(session, user_id)
        if not user:
            await _safe_reply(message, "⚠️ 用户未找到。")
        else:
            user.phone = message.text.strip()
            await session.commit()
            await _safe_reply(message, f"✅ 手机号已更新为：{user.phone}")
    await state.clear()

# ======================
# 语言选择回调
# ======================
@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_callback(callback: types.CallbackQuery):
    lang_code = (callback.data or "").replace("set_lang_", "")
    user_id = get_user_id(callback)
    if not user_id:
        await _safe_reply(callback, "⚠️ 无法获取用户ID", show_alert=True)
        return
    async with get_async_session() as session:
        user = await get_user(session, user_id)
        if user:
            user.language = lang_code
            await session.commit()
            await _safe_reply(callback, f"✅ 语言已更新为 {LANGUAGE_OPTIONS.get(lang_code, lang_code)}")
       


