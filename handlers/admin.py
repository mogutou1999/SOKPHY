# handlers/admin.py
import logging
import bcrypt
from functools import wraps
from typing import cast,Optional, Sequence
from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,InaccessibleMessage
from aiogram.filters import Command,or_f
from config.settings import settings
from db.session import get_async_session
from db.models import User, Role,Product
from sqlalchemy import select, update
from sqlalchemy.sql import func
from utils.formatting import _safe_reply
from aiogram.fsm.context import FSMContext
from services.user_service import db_get_user
from utils.decorators import db_session, handle_errors
from services.products import create_product_db
from decimal import Decimal
router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = settings.admin_ids or []

# -----------------------------
# 权限校验
# -----------------------------
def require_role(required_roles):
    def deco(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not message.from_user:
                await _safe_reply(message, "⚠️ 用户信息获取失败")
                return
            async with get_async_session() as session:
                res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
                user = res.scalar_one_or_none()
                if not user or user.role not in required_roles:
                    await _safe_reply(message, "🚫 权限不足")
                    return
            return await handler(message, *args, **kwargs)
        return wrapper
    return deco

def require_superadmin(handler):
    return require_role([Role.SUPERADMIN])(handler)

def is_admin_user(user: Optional[User]) -> bool:
    return bool(user and user.role in (Role.ADMIN, Role.SUPERADMIN))


@router.message(or_f(
    Command("admin"),
    F.text.casefold() == "admin",
    F.text == "/admin"
))
@handle_errors
async def admin_menu(message: Message, state: FSMContext):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return
    
    if message.from_user.id not in (ADMIN_IDS or []):
        await _safe_reply(message, "❌ 你没有权限访问此菜单。")
        return
    
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ 你没有权限访问此菜单。")
        return

    user = await db_get_user(message.from_user.id)
    if not is_admin_user(user):
        await _safe_reply(message, "❌ 你不是管理员或权限不足。")
        return

    text = (
        "👮 欢迎进入管理员面板\n\n可用命令：\n"
        "/ban <用户ID> - 封禁用户\n"
        "/unban <用户ID> - 解封用户\n"
        "/setadmin <用户ID> <角色> - 设置管理员（ADMIN/SUPERADMIN）\n"
        "/resetpw <用户ID> <新密码> - 重置密码\n\n请选择操作或使用下方按钮："
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ 新增商品", callback_data="admin_add_product")],
            [InlineKeyboardButton(text="📝 修改商品", callback_data="admin_edit_product")],
            [InlineKeyboardButton(text="❌ 下架商品", callback_data="admin_delete_product")],
            [InlineKeyboardButton(text="🛒 打开商城", url="https://shop-frontend-5p36.onrender.com")],
        ]
    )

    await _safe_reply(message, text, reply_markup=kb)
  
@router.message(F.text == "下一步")
async def handle_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(step_done=True)
  

# -----------------------------
# /ban / /unban / /setadmin / /resetpw / /userinfo
# 这些命令均做基础参数校验并用 DB 会话修改
# -----------------------------
@router.message(F.text.startswith("/ban"))
@handle_errors
async def ban_user(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await _safe_reply(message, "❌ 格式：/ban <用户ID>")
    target = int(parts[1])
    async with get_async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == target))
        u = res.scalar_one_or_none()
        if not u:
            return await _safe_reply(message, "⚠️ 用户不存在")
        u.is_blocked = True
        await session.commit()
    await _safe_reply(message, f"✅ 用户 {target} 已被封禁")


@router.message(F.text.startswith("/unban"))
@handle_errors
async def unban_user(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await _safe_reply(message, "❌ 格式：/unban <用户ID>")
    target = int(parts[1])
    async with get_async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == target))
        u = res.scalar_one_or_none()
        if not u:
            return await _safe_reply(message, "⚠️ 用户不存在")
        u.is_blocked = False
        await session.commit()
    await _safe_reply(message, f"✅ 用户 {target} 已解封")


@router.message(F.text.startswith("/setadmin"))
@handle_errors
async def set_admin(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        return await _safe_reply(message, "❌ 格式：/setadmin <用户ID> <角色>")
    target_str, role_str = parts[1], parts[2].upper()
    if not target_str.isdigit() or role_str not in ("ADMIN", "SUPERADMIN"):
        return await _safe_reply(message, "❌ 参数错误：ID 必须为数字，角色为 ADMIN 或 SUPERADMIN")
    target = int(target_str)
    async with get_async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == target))
        u = res.scalar_one_or_none()
        if not u:
            return await _safe_reply(message, "⚠️ 用户不存在")
        u.role = Role[role_str]
        await session.commit()
    await _safe_reply(message, f"✅ 用户 {target} 已设为 {role_str}")


@router.message(F.text.startswith("/resetpw"))
@handle_errors
async def reset_password(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        return await _safe_reply(message, "❌ 格式：/resetpw <用户ID> <新密码>")
    target = int(parts[1])
    newpw = parts[2]
    hashed = bcrypt.hashpw(newpw.encode(), bcrypt.gensalt()).decode()
    async with get_async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == target))
        u = res.scalar_one_or_none()
        if not u:
            return await _safe_reply(message, "⚠️ 用户不存在")
        u.password = hashed
        await session.commit()
    await _safe_reply(message, f"🔑 用户 {target} 密码已重置")


@router.message(F.text.startswith("/userinfo"))
@handle_errors
async def user_info(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await _safe_reply(message, "❌ 格式应为：/userinfo <用户ID>")
    uid = int(parts[1])
    async with get_async_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == uid))
        u = res.scalar_one_or_none()
        if not u:
            return await _safe_reply(message, "⚠️ 用户不存在")
        txt = (
            f"👤 用户信息\nID: {u.telegram_id}\n用户名: @{u.username or '无'}\n"
            f"邮箱: {u.email or '未绑定'}\n状态: {'✅ 正常' if not u.is_blocked else '🚫 已封禁'}"
        )
        await _safe_reply(message, txt)
