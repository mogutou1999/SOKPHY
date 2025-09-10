# admin_config.py
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import Router, F, types
from utils.decorators import db_session, handle_errors
from utils.formatting import _safe_reply
from .admin import require_superadmin
from db.session import get_async_session
from db.models import Config ,Role
from sqlalchemy import select, update
from .admin import require_role 
router = Router()

@router.message(Command("setconfig"))
@require_superadmin
@handle_errors
async def set_config(message: Message):
    parts = (message.text or "").strip().split(maxsplit=2)
    if len(parts) != 3:
        return await _safe_reply(message, "❌ 格式应为：/setconfig <key> <value>")
    key, value = parts[1], parts[2]
    async with get_async_session() as session:
        res = await session.execute(select(Config).where(Config.key == key))
        cfg = res.scalar_one_or_none()
        if cfg:
            cfg.value = value
        else:
            cfg = Config(key=key, value=value)
            session.add(cfg)
        await session.commit()
    await _safe_reply(message, f"✅ 已设置配置 {key} = {value}")


@router.message(Command("getconfig"))
@require_role([Role.ADMIN, Role.SUPERADMIN])  # 或 @require_admin
@handle_errors
async def get_config(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        return await _safe_reply(message, "❌ 格式应为：/getconfig <key>")
    key = parts[1]
    async with get_async_session() as session:
        res = await session.execute(select(Config).where(Config.key == key))
        cfg = res.scalar_one_or_none()
        if not cfg:
            return await _safe_reply(message, f"⚠️ 配置 {key} 不存在")
        await _safe_reply(message, f"📌 {cfg.key} = {cfg.value}")


@router.message(Command("listconfig"))
@require_role([Role.ADMIN, Role.SUPERADMIN])
@handle_errors
async def list_config(message: Message):
    async with get_async_session() as session:
        res = await session.execute(select(Config))
        configs = res.scalars().all()
    if not configs:
        return await _safe_reply(message, "📭 当前没有配置")
    text = "\n".join([f"{c.key} = {c.value}" for c in configs])
    await _safe_reply(message, f"📋 配置列表:\n{text}")
