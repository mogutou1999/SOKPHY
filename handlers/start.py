# services/start.py
import logging
from typing import Optional
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func, case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_async_session
from db.models import User, Order
from config.settings import settings
from pydantic import BaseModel
from utils.formatting import _safe_reply

router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = settings.admin_ids or []


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class SiteStats(BaseModel):
    total_users: int
    total_orders: int
    total_revenue: float
    shipped_orders: int
    refunded_orders: int

async def get_site_stats(db: AsyncSession) -> SiteStats:
    total_users_q = select(func.coalesce(func.count(User.id), 0))
    total_orders_q = select(func.coalesce(func.count(Order.id), 0))
    total_revenue_q = select(func.coalesce(func.sum(Order.total_amount), 0.0)) \
        .where(Order.status.in_(["paid", "shipped"]))
    shipped_orders_q = select(func.coalesce(func.count(Order.id), 0)) \
        .where(Order.status == "shipped")
    refunded_orders_q = select(func.coalesce(func.count(Order.id), 0)) \
        .where(Order.status == "refunded")

    total_users = (await db.execute(total_users_q)).scalar_one()
    total_orders = (await db.execute(total_orders_q)).scalar_one()
    total_revenue = (await db.execute(total_revenue_q)).scalar_one()
    shipped_orders = (await db.execute(shipped_orders_q)).scalar_one()
    refunded_orders = (await db.execute(refunded_orders_q)).scalar_one()

    return SiteStats(
        total_users=total_users,
        total_orders=total_orders,
        total_revenue=float(total_revenue),
        shipped_orders=shipped_orders,
        refunded_orders=refunded_orders,
    )

async def get_user_by_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
    try:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await db.execute(stmt)
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"获取用户失败 telegram_id={telegram_id}: {e}")
        return None

@router.message(Command("start"))
async def handle_stats(message: Message):
    if not message.from_user:
        await _safe_reply(message,"⚠️ 用户信息获取失败")
        return
    user_id = message.from_user.id

    async with get_async_session() as db:
        user = await get_user_by_id(db, user_id)

        if not is_admin(user_id):
            await _safe_reply(message,"🚫 无权限查看统计数据")
            return

        try:
            stats = await get_site_stats(db)
            text = (
                "📊 <b>系统统计</b>：\n\n"
                f"👥 用户总数：<b>{stats.total_users}</b>\n"
                f"🛒 订单总数：<b>{stats.total_orders}</b>\n"
                f"💰 销售总额：<b>¥{stats.total_revenue:.2f}</b>\n"
                f"📦 已发货订单：<b>{stats.shipped_orders}</b>\n"
                f"💸 已退款订单：<b>{stats.refunded_orders}</b>\n"
            )
            await _safe_reply(message,text)
        except ValueError as e:
            logger.exception(f"获取统计数据失败: {e}")
            await _safe_reply(message,"❌ 无法加载统计数据，请稍后再试")
