# handlers/orders.py
import logging
from uuid import UUID
from fastapi import APIRouter, Depends
from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from utils.formatting import _safe_reply,format_order_detail,parse_order_id
from utils.decorators import handle_errors, db_session
from db import get_async_session
from db.crud import OrderCRUD
from config.settings import settings
from services import orders as order_service

logger = logging.getLogger(__name__)
router = Router()

def is_admin(user_id: int) -> bool:
    """检查是否为管理员"""
    return user_id in (settings.admin_ids or [])

# -----------------------------
# 用户查询订单详情
# -----------------------------
@router.message(Command("order"))
async def get_order_handler(message: types.Message):
    """
    用户输入 /order <订单ID> 查询订单详情
    """
    text = message.text or ""
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await _safe_reply(message,"❌ 请提供订单ID，例如：/order 123e4567-e89b-12d3-a456-426614174000")
        return

    try:
        order_id = UUID(parts[1])
    except ValueError:
        await _safe_reply(message,"❌ 订单ID格式不正确")
        return

    async with get_async_session() as session:
        order = await order_service.get_order_by_id(session, order_id)
        if not order:
            await _safe_reply(message,"❌ 未找到该订单")
            return

        await _safe_reply(message,
            f"📦 订单详情:\n"
            f"订单ID: {order.id}\n"
            f"用户ID: {order.user_id}\n"
            f"总金额: ¥{order.total_amount}\n"
            f"状态: {getattr(order.status, 'value', order.status)}"
        )

# -----------------------------
# 用户查询自己的所有订单
# -----------------------------
@router.message(Command("myorders"))
async def list_user_orders(message: types.Message):
    """
    用户输入 /myorders 查询自己所有订单
    """
    user_id = getattr(message.from_user, "id", None)
    if not user_id:
        await _safe_reply(message,"❌ 无法识别用户")
        return

    async with get_async_session() as session:
        orders = await order_service.get_orders_by_user(user_id, session)
        if not orders:
            await _safe_reply(message,"📭 你还没有订单")
            return

        lines = ["📦 <b>你的订单列表</b>:\n"]
        for o in orders:
            lines.append(
                f"订单ID: {o.id} | 总金额: ¥{o.total_amount:.2f} | 状态: {getattr(o.status, 'value', o.status)}"
            )
        await _safe_reply(message,"\n".join(lines))
    
# -----------------------------
# Telegram 内部回调注册统一函数
# -----------------------------
def setup_orders_handlers(dp: Router) -> None:
    # 查看订单列表（测试按钮或文本触发）
    @dp.message(lambda m: m.text == "orders")
    @handle_errors
    @db_session
    async def view_orders(message: Message, db: AsyncSession):
        user_id = getattr(message.from_user, "id", None)
        if not user_id:
            await _safe_reply(message,"⚠️ 无法获取用户ID")
            return

        orders = await OrderCRUD.get_by_user_id(user_id, db)
        if not orders:
            await _safe_reply(message,"📦 你还没有订单。")
            return

        lines = ["📦 <b>你的订单列表</b>:\n"]
        for order in orders:
            lines.append(
                f"订单ID: {order.id} | 状态: {order.status.value} | 总额: ¥{order.total_amount:.2f}"
            )

        await _safe_reply(message,"\n".join(lines))

    # 查看订单详情回调
    @dp.callback_query(F.data.startswith("order_detail:"))
    async def show_order_detail(callback: CallbackQuery):
        order_id = parse_order_id(callback, "order_detail")
        if not order_id:
            await _safe_reply(callback, "⚠️ 回调参数错误", show_alert=True)
            return

        try:
            async with get_async_session() as session:
                order = await order_service.get_order_by_id(session, order_id)

            if not order:
                await _safe_reply(callback, "❌ 订单不存在", show_alert=True)
                return

            detail = format_order_detail(order)
            await _safe_reply(callback, f"📦 订单详情：\n\n{detail}")

        except Exception as e:
            logger.exception(f"订单详情加载失败: {e}")
            await _safe_reply(callback, "⚠️ 加载失败，请稍后再试", show_alert=True)

    # 订单退款回调
    @dp.callback_query(F.data.startswith("refund_order:"))
    async def handle_refund_order(callback: CallbackQuery):
        order_id = parse_order_id(callback, "refund_order")
        if not order_id:
            await _safe_reply(callback, "⚠️ 参数错误", show_alert=True)
            return

        async with get_async_session() as session:
            success = await order_service.mark_order_as_refunded(order_id, session)

        if success:
            await _safe_reply(callback, "✅ 已标记为已退款")
        else:
            await _safe_reply(callback, "⚠️ 退款失败", show_alert=True)

    # 订单发货回调（仅管理员）
    @dp.callback_query(F.data.startswith("ship_order:"))
    async def handle_ship_order(callback: CallbackQuery):
        if not callback.from_user or not is_admin(callback.from_user.id):
            await _safe_reply(callback, "🚫 无权限", show_alert=True)
            return

        order_id = parse_order_id(callback, "ship_order")
        if not order_id:
            await _safe_reply(callback, "❌ 参数错误", show_alert=True)
            return

        async with get_async_session() as session:
            success = await order_service.mark_order_as_shipped(order_id, session)

        if success:
            await _safe_reply(callback, f"✅ 订单 {order_id} 已发货")
        else:
            await _safe_reply(callback, "❌ 标记失败", show_alert=True)
