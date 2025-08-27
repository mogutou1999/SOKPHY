# handlers/orders.py
import logging
from uuid import UUID
from decimal import Decimal
from typing import Optional, Union

from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.session import get_async_session
from db.models import User, CartItem, Order, OrderItem
from config.settings import settings
from services import orders as order_service
from utils.formatter import format_order_detail
from utils.decorators import handle_errors, db_session

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in (settings.admin_ids or [])


async def _safe_reply(
    event: Union[Message, CallbackQuery],
    text: str,
    reply_markup=None,
    show_alert: bool = False,
):
    if isinstance(event, Message):
        await event.answer(text, reply_markup=reply_markup)
    elif isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            try:
                await event.message.edit_text(text, reply_markup=reply_markup)
            except Exception:
                await event.answer("⚠️ 无法修改消息", show_alert=True)
        else:
            await event.answer(text, show_alert=show_alert)


def parse_callback_parts(data: str, prefix: str) -> Optional[Union[int, UUID]]:
    """解析 callback_data，返回 int 或 UUID 或 None"""
    if not data or not data.startswith(prefix):
        return None
    parts = data.split(":")
    if len(parts) < 2:
        return None
    val = parts[1]
    if val.isdigit():
        return int(val)
    try:
        return UUID(val)
    except ValueError:
        return None


def setup_orders_handlers(router: Router) -> None:

    @router.message(lambda m: m.text == "orders")
    @handle_errors
    @db_session
    async def view_orders(message: types.Message, db: AsyncSession):
        user_id = getattr(message.from_user, "id", 0)
        if not user_id:
            await message.answer("⚠️ 无法获取用户ID")
            return

        result = await db.execute(select(Order).where(Order.user_id == user_id))
        orders = result.scalars().all()

        if not orders:
            await message.answer("📦 你还没有订单。")
            return

        lines = ["📦 <b>你的订单列表</b>:\n"]
        for order in orders:
            lines.append(
                f"订单ID: {order.id} | 状态: {order.status.value} | 总额: ¥{order.total_amount:.2f}"
            )

        await message.answer("\n".join(lines), parse_mode="HTML")

    @router.callback_query(F.data.startswith("order_detail:"))
    async def show_order_detail(callback: CallbackQuery):
        data = callback.data
        if not data:
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return

        order_id = parse_callback_parts(data, "order_detail")
        if not order_id:
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return

        async with get_async_session() as session:
            order = await order_service.get_order_by_id(session, order_id)

        if not order:
            await callback.answer("❌ 订单不存在", show_alert=True)
            return

        detail = format_order_detail(order)
        await _safe_reply(callback, f"📦 订单详情：\n\n{detail}")

    @router.callback_query(F.data.startswith("refund_order:"))
    async def handle_refund_order(callback: CallbackQuery):
        if not callback.data:
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return

        order_id = parse_callback_parts(callback.data, "refund_order")
        if not isinstance(order_id, int):
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return

        async with get_async_session() as session:
            success = await order_service.mark_order_as_refunded(order_id, session)

        if success:
            await callback.answer("✅ 已标记为已退款")
        else:
            await callback.answer("⚠️ 退款失败", show_alert=True)


    @router.callback_query(F.data.startswith("ship_order:"))
    async def handle_ship_order(callback: CallbackQuery):
        if not callback.from_user or not is_admin(callback.from_user.id):
            await callback.answer("🚫 无权限", show_alert=True)
            return

        if not callback.data:
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return

        order_id = parse_callback_parts(callback.data, "ship_order")
        if not isinstance(order_id, int):
            await callback.answer("❌ 参数错误", show_alert=True)
            return

        async with get_async_session() as session:
            success = await order_service.mark_order_as_shipped(order_id, session)

        if success:
            await callback.answer(f"✅ 订单 {order_id} 已发货")
        else:
            await callback.answer("❌ 标记失败", show_alert=True)

    @router.message(Command("checkout"))
    async def checkout(message: types.Message):
        if not message.from_user:
            await message.answer("⚠️ 用户信息获取失败")
            return

        async with get_async_session() as session:
            stmt = select(User).where(User.telegram_id == message.from_user.id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                await message.answer("用户未注册")
                return

            stmt = select(CartItem).where(CartItem.user_id == user.id)
            result = await session.execute(stmt)
            cart_items = result.scalars().all()

            if not cart_items:
                await message.answer("购物车为空")
                return

            total = sum(Decimal(item.unit_price) * item.quantity for item in cart_items)
            order = Order(user_id=user.id, total_amount=float(total))
            session.add(order)
            await session.flush()

            for item in cart_items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=float(item.unit_price),
                )
                session.add(order_item)
                await session.delete(item)

            await session.commit()
            await message.answer(f"✅ 下单成功，总金额 ¥{total:.2f}")
