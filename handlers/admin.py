import logging
import bcrypt
import secrets
import hashlib
from functools import wraps

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from db.session import async_session_maker
from db.models import User, Role
from sqlalchemy.exc import SQLAlchemyError

from services import cart, order, start
from sqlalchemy import select, update

router = Router()
logger = logging.getLogger(__name__)


ADMIN_IDS = settings.admin_ids
def is_admin(user_id: int) -> bool:
    return (user_id in ADMIN_IDS) 

async def db_check_is_admin(user_id: int) -> bool:
    async with async_session_maker() as session:
        result = await session.execute(
            select(User.is_admin).where(User.telegram_id == user_id)
        )
        is_admin = result.scalar_one_or_none()
        return bool(is_admin)

def setup_admin_handlers(router: Router) -> None:
    admin_router = Router()

    @admin_router.message(F.text == "/admin")
    async def handle_admin(message: Message) -> None:
        await message.answer("✅ Admin handler: /admin 命令收到。")

    router.include_router(admin_router)


@router.message(F.text.startswith("/ban"))
async def ban_user(message: Message):
    if not message.text or len(message.text.strip().split()) != 2:
        return await message.answer("❌ 格式：/ban <用户ID>")
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.answer("🚫 无权限")
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("❌ 格式：/ban <用户ID>")
    target_id = int(parts[1])
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return await message.answer("⚠️ 用户不存在")
        user.is_blocked = True
        await session.commit()
    await message.answer(f"🚫 已封禁 {target_id}")


@router.message(F.text.startswith("/unban"))
async def unban_user(message: Message):
    if not message.text or len(message.text.strip().split()) != 2:
        return await message.answer("❌ 格式：/ban <用户ID>")
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.answer("🚫 无权限")
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("❌ 格式：/unban <用户ID>")
    target_id = int(parts[1])
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return await message.answer("⚠️ 用户不存在")
        user.is_blocked = False
        await session.commit()
    await message.answer(f"✅ 已解封 {target_id}")


@router.message(F.text.startswith("/setadmin"))
async def set_admin(message: Message):
    if not message.text or len(message.text.strip().split()) != 2:
        return await message.answer("❌ 格式：/ban <用户ID>")
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.answer("🚫 无权限")
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("❌ 格式：/setadmin <用户ID>")
    target_id = int(parts[1])
    async with async_session_maker() as session:

        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )

        user = result.scalar_one_or_none()
        if not user:
            return await message.answer("⚠️ 用户不存在")
        user.role = Role.SUPERADMIN
    await session.commit()
    await message.answer(f"✅ 已设为管理员 {target_id}")


@router.message(F.text.startswith("/resetpw"))
async def reset_password(message: Message):
    if not message.text or len(message.text.strip().split()) != 2:
        return await message.answer("❌ 格式：/ban <用户ID>")
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.answer("🚫 无权限")
    parts = message.text.strip().split()
    if len(parts) != 3 or not parts[1].isdigit():
        return await message.answer("❌ 格式：/resetpw <用户ID> <新密码>")
    target_id = int(parts[1])
    new_password = parts[2]
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return await message.answer("⚠️ 用户不存在")
        new_pw = "xxxx"
        hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        await session.commit()
    await message.answer(f"🔑 已重置密码 {target_id}")


@router.message(F.text.startswith("/user"))
async def list_or_show_user(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
    if not message.text or len(message.text.strip().split()) != 2:
        return await message.answer("❌ 格式：/ban <用户ID>")

    try:
        parts = message.text.strip().split()

        # 👉 1️⃣ 只写 "/user" 或 "/user 页码"
        if len(parts) == 1 or (
            len(parts) == 2 and parts[1].isdigit() and int(parts[1]) < 10000
        ):
            page = int(parts[1]) if len(parts) == 2 else 1
            per_page = 5
            offset = (page - 1) * per_page

            async with async_session_maker() as session:
                result = await session.execute(
                    select(User).offset(offset).limit(per_page)
                )
                users = result.scalars().all()

                if not users:
                    await message.answer(f"📭 没有用户 (第 {page} 页)")
                    return

                text = "\n".join(
                    [
                        f"ID: {u.telegram_id} | 用户名: @{u.username or '无'} | 状态: {'🚫 封禁' if u.is_blocked else '✅ 正常'}"
                        for u in users
                    ]
                )

                await message.answer(f"👥 用户列表 (第 {page} 页):\n{text}")

        # 👉 2️⃣ "/user <用户ID>" → 查询详情
        elif len(parts) == 2 and parts[1].isdigit():
            user_id = int(parts[1])

            async with async_session_maker() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == user_id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    await message.answer("⚠️ 用户不存在")
                    return

                text = (
                    f"👤 <b>用户信息</b>\n"
                    f"ID: {user.telegram_id}\n"
                    f"用户名: @{user.username or '无'}\n"
                    f"姓名: {getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}\n"
                    f"语言: {getattr(user, 'language', '未设置')}\n"
                    f"手机号: {getattr(user, 'phone', '未绑定')}\n"
                    f"邮箱: {getattr(user, 'email', '未绑定')}\n"
                    f"注册时间: {user.created_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(user, 'created_at', None) else '未知'}\n"
                    f"状态: {'✅ 正常' if not user.is_blocked else '🚫 已封禁'}"
                )

                await message.answer(text, parse_mode="HTML")

        else:
            await message.answer("❌ 格式应为：/user 或 /user <页码> 或 /user <用户ID>")

    except Exception as e:
        logger.error(f"/user 命令执行失败: {e}")
        await message.answer("❌ 操作失败，请稍后重试")


@router.message(F.text.startswith("/userinfo"))
async def user_info(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return

    if not message.text:
        await message.answer("⚠️ 指令格式不正确")
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ 格式应为：/userinfo <用户ID>")
        return

    user_id = int(parts[1])

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await message.answer("⚠️ 用户不存在")
                return

            text = (
                f"👤 <b>用户信息</b>\n"
                f"ID: {user.telegram_id}\n"
                f"用户名: @{user.username or '无'}\n"
                f"姓名: {getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}\n"
                f"语言: {getattr(user, 'language', '未设置')}\n"
                f"手机号: {getattr(user, 'phone', '未绑定')}\n"
                f"邮箱: {getattr(user, 'email', '未绑定')}\n"
                f"注册时间: {user.created_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(user, 'created_at', None) else '未知'}\n"
                f"状态: {'✅ 正常' if not user.is_blocked else '🚫 已封禁'}"
            )

            await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"查询用户信息失败: {e}")
        await message.answer("❌ 查询失败，请稍后重试")




@router.message(F.text.startswith("/setconfig"))
async def set_config(message: Message):
    if not message.from_user:
        return await message.answer("⚠️ 用户信息获取失败")

    if not is_admin(message.from_user.id):
        return await message.answer("🚫 无权限操作")

    if not message.text:
        return await message.answer("❌ 格式：/ban <用户ID>")
    parts = message.text.strip().split()

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("❌ 格式应为：/setconfig <key> <value>")
        return


@router.message(F.text.startswith("/getconfig"))
async def get_config(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return

    if not is_admin(message.from_user.id):
        await message.answer("🚫 无权限操作")
        return

    if not message.text:
        return await message.answer("❌ 格式：/ban <用户ID>")
    parts = message.text.strip().split()

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ 格式应为：/getconfig <key>")
        return


@router.message(F.text.startswith("/listconfig"))
async def list_config(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return

    if not is_admin(message.from_user.id):
        await message.answer("🚫 无权限操作")
        return


@router.message(F.text.startswith("/shutdown"))
async def shutdown_system(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        def is_superadmin(user: User) -> bool:
            return user.role == Role.SUPERADMIN

        if not user or not is_superadmin(user):
            await message.answer("🚫 只有超级管理员可以执行此操作")
            return

        await message.answer("💥 系统关机指令已执行（示例）")


def require_role(required_roles):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not message.from_user:
                await message.answer("⚠️ 用户信息获取失败")
                return

            async with async_session_maker() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == message.from_user.id)
                )
                user = result.scalar_one_or_none()

                if not user or user.role not in required_roles:
                    await message.answer(
                        f"🚫 权限不足，需角色: {', '.join(required_roles)}"
                    )
                    return

            return await handler(message, *args, **kwargs)

        return wrapper

    return decorator


# 用法示例:
@router.message(F.text.startswith("/somecommand"))
@require_role(["superadmin"])
async def only_superadmins_can_do(message: Message):
    await message.answer("✅ 你是超级管理员，可以执行！")
