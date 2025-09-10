# handlers/start.py
import logging
from typing import cast,Optional
from aiogram import Bot,Router
from aiogram.filters import Command
from aiogram.types import Message,InlineKeyboardButton,InlineKeyboardMarkup,User as TelegramUser
from sqlalchemy import select, func, case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_async_session
from db.models import User, Order
from config.settings import settings
from pydantic import BaseModel
from utils.formatting import _safe_reply
from utils.decorators import db_session,user_required
from datetime import datetime, timezone
from db.models import User as DBUser
import asyncio
router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS =[]


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

# --- 路由处理器示例 ---
@router.message(Command("start"))
@db_session
@user_required(check_registration=False)
async def handle_start(message: Message, db: AsyncSession, bot: Bot):
    from handlers.auth import get_or_create_user  # 延迟导入避免循环依赖

    tg_user = message.from_user

    if not tg_user:
        await _safe_reply(message, "⚠️ 无法获取用户信息")
        return

    # 现在 tg_user 肯定不是 None，可以安全使用
    user = await get_or_create_user(db, tg_user)
    if not user:
        await _safe_reply(message, "❌ 注册失败，请稍后重试")
        return

    # 是管理员？显示统计数据
    if is_admin(user.telegram_id):
        total_users = await db.execute(select(func.count(User.id)))
        total_orders = await db.execute(select(func.count(Order.id)))
        total_users = total_users.scalar_one()
        total_orders = total_orders.scalar_one()
        
        stats = await get_site_stats(db)
        text = (
            "📊 <b>系统统计</b>：\n\n"
            f"👥 用户总数：<b>{stats.total_users}</b>\n"
            f"🛒 订单总数：<b>{stats.total_orders}</b>\n"
            f"💰 销售总额：<b>¥{stats.total_revenue:.2f}</b>\n"
            f"📦 已发货订单：<b>{stats.shipped_orders}</b>\n"
            f"💸 已退款订单：<b>{stats.refunded_orders}</b>\n"
        )        
        admin_buttons = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 查看库存", callback_data="admin_inventory")],
            [InlineKeyboardButton(text="➕ 添加商品", callback_data="admin_add_product")],
            [InlineKeyboardButton(text="📝 修改商品", callback_data="admin_edit_product")],
            [InlineKeyboardButton(text="❌ 下架商品", callback_data="admin_delete_product")]
        ])
        await _safe_reply(message, text, reply_markup=admin_buttons)
        return 
    # 普通用户：显示购物相关按钮
    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 查看商品", callback_data="open_menu")],
        [InlineKeyboardButton(text="👤 我的账户", callback_data="open_account")],                     
    ])
    await _safe_reply(message, f"👋 欢迎，{user.first_name or '用户'}！\n点击下方按钮开始购物 ↓", reply_markup=buttons)
    

async def test():
    start = datetime.now(timezone.utc)
    # 模拟100次并发调用
    tasks = [handle_start(message=..., db=...) for _ in range(100)]
    await asyncio.gather(*tasks)
    print(f"耗时: {(datetime.now(timezone.utc) - start).total_seconds():.2f}s")
    
    
    
