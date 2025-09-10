
# handlers/admin_users.py
from utils.decorators import db_session, handle_errors
from aiogram import Router, F
import logging
from functools import wraps
from typing import cast,Optional, Sequence
from aiogram.types import Message,  InlineKeyboardMarkup, InlineKeyboardButton,InaccessibleMessage
from config.settings import settings
from db.session import get_async_session
from db.models import User, Role
from sqlalchemy import select, update

from sqlalchemy.sql import func
from utils.formatting import _safe_reply
from services.user_service import db_get_user

logger = logging.getLogger(__name__)
router = Router()
ADMIN_IDS = settings.admin_ids or []

@router.message(F.text.startswith("/users"))
async def list_or_show_user(message: Message):
    # 参数解析与分页
    parts = (message.text or "").strip().split()
    per_page = getattr(settings, "items_per_page", 10)
    async with get_async_session() as session:
        # 单用户查询 /users <tg_id>
        if len(parts) == 2 and parts[1].isdigit():
            user_id = int(parts[1])
            res = await session.execute(select(User).where(User.telegram_id == user_id))
            u = res.scalar_one_or_none()
            if not u:
                return await _safe_reply(message, "⚠️ 用户不存在")
            txt = (
                f"👤 用户信息\nID: {u.telegram_id}\n用户名: @{u.username or '无'}\n"
                f"状态: {'✅' if not u.is_blocked else '🚫 封禁'}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="设置为管理员", callback_data=f"setadmin:{u.telegram_id}")]
            ])
            await _safe_reply(message, txt, reply_markup=kb)
            return

        # 列表（分页）
        page = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 1
        total = await session.scalar(select(func.count()).select_from(User)) or 0
        max_page = (total + per_page - 1) // per_page if total else 1
        if page < 1: page = 1
        if page > max_page: page = max_page
        offset = (page - 1) * per_page
        res = await session.execute(select(User).offset(offset).limit(per_page))
        users = res.scalars().all()
        if not users:
            return await _safe_reply(message, f"📭 没有用户 (第 {page} 页)")
        lines = [f"ID:{u.telegram_id} 用户名:@{u.username or '无'} 状态:{'🚫' if u.is_blocked else '✅'}" for u in users]
        await _safe_reply(message, f"👥 用户列表 (第 {page} 页):\n" + "\n".join(lines))
