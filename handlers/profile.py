from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message,CallbackQuery,  ReplyKeyboardMarkup, ReplyKeyboardRemove,KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User
from db.session import async_session_maker
from config import settings
from sqlalchemy import select, update
import logging
from datetime import datetime
import random
from typing import Dict, Optional
from config.settings import settings

router = Router()
logger = logging.getLogger(__name__)

LANGUAGE_OPTIONS = {
    "en": "English",
    "zh": "中文",
    "es": "Español"
}

ADMIN_IDS = settings.admin_ids
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

class ProfileStates(StatesGroup):
    CHOICE = State()
    AWAIT_EMAIL = State()
    AWAIT_PHONE = State()
    AWAIT_LANGUAGE = State()

class VerificationStates(StatesGroup):
    AWAIT_VERIFICATION = State()

verification_codes: Dict[int, str] = {}

def setup_profile_handlers(router: Router) -> None:
    profile_router = Router()

    @profile_router.message(F.text == "/profile")
    async def handle_profile(message: Message) -> None:
        await message.answer("✅ Profile handler: /profile 命令收到。")

    router.include_router(profile_router)





@router.message(Command("profile"))
async def get_user_profile(message: types.Message, state: FSMContext):
    user_id = message.from_user.id  # type: ignore[attr-defined]
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("⚠️ 未找到您的用户信息。")
            return

        text = (
            f"👤 用户信息：\n"
            f"ID: {user.telegram_id}\n"
            f"用户名: @{user.username or '无'}\n"
            f"邮箱: {user.email or '未设置'}\n"
            f"语言: {user.language or '未设置'}\n"
            f"注册时间: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📧 修改邮箱"), KeyboardButton(text="📱 修改手机号")],
                [KeyboardButton(text="🌐 修改语言"), KeyboardButton(text="❌ 取消")]
            ],
    resize_keyboard=True,
    one_time_keyboard=True
)

        await message.answer(text)
        await message.answer("请选择要修改的项目：", reply_markup=keyboard)
        await state.set_state(ProfileStates.CHOICE)

@router.message(ProfileStates.CHOICE)
async def handle_choice(message: Message, state: FSMContext):
    text = message.text
    if text == "📧 修改邮箱":
        await message.answer("请输入新邮箱：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_EMAIL)
    elif text == "📱 修改手机号":
        await message.answer("请输入新手机号：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_PHONE)
    elif text == "🌐 修改语言":
        await message.answer("请输入语言代码（例如：en、zh、es）：", reply_markup=ReplyKeyboardRemove())
        await state.set_state(ProfileStates.AWAIT_LANGUAGE)
    elif text == "❌ 取消":
        await state.clear()
        await message.answer("操作已取消。", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("无效选项，请重新选择。")

@router.message(ProfileStates.AWAIT_EMAIL)
async def update_email(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ 无效输入，请重新输入手机号。")
        return

    new_phone = message.text.strip()
    user_id = message.from_user.id   # type: ignore[attr-defined]

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.phone = new_phone
            await session.commit()
            await message.answer(f"✅ 手机号已更新为：{new_phone}")
        else:
            await message.answer("⚠️ 用户未找到。")
    await state.clear()
@router.message(ProfileStates.AWAIT_PHONE)
async def update_phone(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ 无效输入，请重新输入手机号。")
        return

    new_phone = message.text.strip()
    user_id = message.from_user.id   # type: ignore[attr-defined]

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.phone = new_phone
            await session.commit()
            await message.answer(f"✅ 手机号已更新为：{new_phone}")
        else:
            await message.answer("⚠️ 用户未找到。")
    await state.clear()
@router.message(ProfileStates.AWAIT_LANGUAGE)
async def update_language(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ 无效输入，请重新输入语言代码。")
        return

    new_lang = message.text.strip()
    user_id = message.from_user.id # type: ignore[attr-defined]
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.language = new_lang
            await session.commit()
            await message.answer(f"✅ 语言偏好已更新为：{new_lang}")
        else:
            await message.answer("⚠️ 用户未找到。")
    await state.clear()

@router.message(F.text.in_(["en", "zh", "es"]))
async def handle_language_reply(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        list=[["en", "zh", "es"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("请选择语言代码：", reply_markup=keyboard)

@router.message(Command("start"))
async def handle_start(message: Message):
    ...
    if not message.text:
        await message.answer("❌ 无效输入")
        return
    lang = message.text.strip()
    user_id = message.from_user.id   # type: ignore[attr-defined]
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("⚠️ 用户不存在。")
            return
        user.language = lang
        await session.commit()
        await message.answer(f"✅ 语言已设置为 {lang}", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "update_language")
async def choose_language(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(name, callback_data=f"set_lang_{code}")]
        for code, name in LANGUAGE_OPTIONS.items()
    ])
    if callback.message:
        await callback.message("请选择语言：", reply_markup=keyboard)
    else:
        await callback.answer("⚠️ 无法编辑消息", show_alert=True)
    await callback.answer()

@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_callback(callback: types.CallbackQuery):
    if not callback.data:
        await callback.answer("⚠️ 回调数据为空")
        return

    lang_code = callback.data.replace("set_lang_", "")
    user_id = callback.from_user.id

    if not callback.message:
        await callback.answer("⚠️ 无法编辑消息")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        db_user = result.scalar_one_or_none()

        if db_user:
            db_user.language = lang_code
            await session.commit()
            await callback.message(
                f"✅ 语言已更新为 {LANGUAGE_OPTIONS.get(lang_code, lang_code)}"
            )
        else:
            await callback.message("⚠️ 未找到用户信息")

    await callback.answer()



@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("欢迎")

@router.message(F.text == "你好")
async def handle_hello(message: Message):
    await message.answer("你也好")
    