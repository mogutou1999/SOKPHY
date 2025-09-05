# services/orders.py
from __future__ import annotations
from typing import List,Union, Optional, Dict, Any
from uuid import UUID
import logging
from decimal import Decimal
from datetime import datetime, timezone
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from sqlalchemy import update, select, insert
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_async_session
from config.settings import settings
from db.models import Order, OrderItem,OrderStatus
from utils.formatting import format_order_detail, format_product_list, format_order_status,_safe_reply,parse_order_id
from utils.callback_utils import parse_callback_uuid, parse_callback_int

from db.crud import UserCRUD,OrderCRUD, ProductCRUD, CartCRUD
from handlers.payment import PaymentService
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.env != "prod" else logging.INFO)

router = Router(name="orders")

payment_service = PaymentService(sandbox=False)  # ⚠️ sandbox 生产安全

def is_admin(user_id: int) -> bool:
    return user_id in (settings.admin_ids or [])

# -------------------------------
# ✅ 查询订单
# -------------------------------
#
async def get_order_by_id(session: AsyncSession, order_id: UUID):
    """获取单个订单详情"""
    try:
        order = await OrderCRUD.get_by_id(session, order_id)
        return order
    except ValueError as e:
        logger.exception(f"查询订单失败: {e}")
        return None
#
async def get_latest_unpaid_order(user_id: UUID, db: AsyncSession) -> Optional[Order]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id, Order.status != OrderStatus.PAID.value)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
#
async def get_orders_by_user(user_id: UUID, session: AsyncSession) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .options(selectinload(Order.items))
    )
    return list(result.scalars().all())
    
# ✅ 创建订单#
async def create_order(
    db: AsyncSession,
    user_id: UUID,
    items: List[Dict[str, Any]],
) -> dict:
    """创建包含商品项的订单"""
    if not items:
        raise ValueError("订单项不能为空")

    total_amount = sum(
        Decimal(str(item["price"])) * item["quantity"] for item in items
    )

    order_items = [
        OrderItem(
            product_id=item["product_id"],
            quantity=item["quantity"],
            price=Decimal(str(item["price"])),
        )
        for item in items
    ]

    order = Order(
        user_id=user_id,
        items=order_items,
        total_amount=total_amount,
        status=OrderStatus.PENDING,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "id": order.id,
        "user_id": order.user_id,
        "total_amount": float(order.total_amount),
        "status": order.status.value,
    }
# -------------------------------
# ✅ 购物车结算 → Stripe
# -------------------------------
#
async def checkout_cart(user, cart_items: List[Dict], db: AsyncSession) -> Dict:
    if not cart_items:
        raise ValueError("购物车为空，无法结算")

    total_amount_cents = sum(int(Decimal(item["price"]) * 100) * item["quantity"] for item in cart_items)
    logger.info(f"用户 {user.id} 结算，总金额 {total_amount_cents} 美分")

    # 构建 OrderItem 列表
    order_items = [
        OrderItem(
            product_id=item["product_id"],
            quantity=item["quantity"],
            price=Decimal(item["price"]),
        ) for item in cart_items
    ]

    # 创建订单对象
    order = Order(
        user_id=user.id,
        items=order_items,
        total_amount=Decimal(total_amount_cents) / 100,  # 保持数据库 Decimal 单位
        currency=settings.currency,
        status=OrderStatus.PENDING.value
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)
    logger.info(f"订单已创建，ID={order.id}")

    try:
        stripe_link = await payment_service.create_stripe_checkout_session(
            amount=total_amount_cents,
            user_id=user.id  # ⚠️ int 主键
        )
        logger.info(f"Stripe Checkout 链接生成: {stripe_link}")
    except ValueError as e:
        logger.exception(f"Stripe 会话生成失败: {e}")
        stripe_link = None

    return {
        "order_id": order.id,
        "total_amount_cents": total_amount_cents,
        "currency": settings.currency,
        "stripe_link": stripe_link
    }
# -------------------------------
# ✅ 标记订单支付
# -------------------------------
#
async def mark_order_paid(order_id: UUID, payment_id: str, db: AsyncSession) -> bool:
    async with db.begin():
        result = await db.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(
                status=OrderStatus.PAID.value,
                payment_id=payment_id,
                paid_at=datetime.now(timezone.utc)
            )
            .execution_options(synchronize_session="fetch")
        )
    return result.rowcount > 0
#
async def mark_order_as_refunded(order_id: UUID, session: AsyncSession) -> bool:
    """标记订单为已退款"""
    try:
        result = await OrderCRUD._execute_commit(
            session,
            OrderCRUD.get_by_id.__func__(session, order_id),  # 先获取订单对象再更新
            "订单退款失败"
        )
        return result
    except ValueError as e:
        logger.exception(f"退款操作失败: {e}")
        return False
#
async def mark_order_as_shipped(order_id: UUID, session: AsyncSession) -> bool:
    """标记订单已发货"""
    try:
        return await OrderCRUD.mark_shipped(session, order_id)
    except ValueError as e:
        logger.exception(f"发货操作失败: {e}")
        return False

# -------------------------------
# ✅ 消息处理（示例：查询订单）
# -------------------------------
@router.message(Command("orders"))
async def handle_list_orders(message: Message):
    if not message.from_user:
        await _safe_reply(message,"❌ 无法识别用户信息")
        return

    async with get_async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await _safe_reply(message,"❌ 用户不存在")
            return
        user_id = user.id

        orders = await get_orders_by_user(user_id, session)

    if not orders:
        await _safe_reply(message,"📭 你还没有订单")
        return

    text = "📦 <b>你的订单</b>\n\n"
    for o in orders:
        text += f"- 订单号: <b>{o.id}</b>, 状态: {o.status}\n"

    await _safe_reply(message,text)

# ✅ 消息处理（支付命令 /pay）
# -------------------------------
@router.message(Command("pay"))
async def handle_payment(message: Message, bot: Bot):
    try:
        if not message.from_user:
            await _safe_reply(message,"⚠️ 用户信息获取失败")
            return

        async with get_async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
            if not user:
                await _safe_reply(message,"❌ 用户不存在")
                return
            user_id = user.id    

            order = await get_latest_unpaid_order(user_id, session)

        if not order:
            await _safe_reply(message,"❌ 你没有未支付订单。")
            return

        await _safe_reply(message,
            f"订单号：{order.id}\n金额：¥{order.total_amount:.2f}\n请扫码付款..."
        )

    except ValueError as e:
        logger.exception(f"处理支付失败: {e}")
        await _safe_reply(message,"❌ 系统错误，无法获取订单")
        
# -------------------------------
# ✅ 回调处理：订单详情
# -------------------------------
@router.callback_query(F.data.startswith("order_detail"))
async def show_order_detail(callback: CallbackQuery):
    if not callback.data:
        await _safe_reply(callback,"⚠️ 回调参数错误", show_alert=True)
        return
    
    order_id = parse_order_id(callback, "order_detail")
    if not order_id:
        await _safe_reply(callback,"⚠️ 回调参数错误", show_alert=True)
        return
    try:
        async with get_async_session() as session:
            order = await get_order_by_id(session, order_id)

        if not order:
            await _safe_reply(callback,"❌ 订单不存在", show_alert=True)
            return

        detail = format_order_detail(order)
        await _safe_reply(callback, f"📦 订单详情：\n\n{detail}")

    except ValueError as e:
        logger.exception(f"订单详情加载失败: {e}")
        await _safe_reply(callback,"⚠️ 加载失败，请稍后再试", show_alert=True)

        
# -------------------------------
# ✅ 回调处理：退款
# -------------------------------
@router.callback_query(F.data.startswith("refund_order"))
async def handle_refund_order(callback: CallbackQuery):
    if not callback.data:
        await _safe_reply(callback,"⚠️ 回调参数错误", show_alert=True)
        return
    order_id = parse_order_id(callback, "refund_order")
    if not order_id:
        await _safe_reply(callback,"⚠️ 回调参数错误", show_alert=True)
        return
    try:
        async with get_async_session() as session:
            success = await mark_order_as_refunded(order_id, session)

        if success:
            await _safe_reply(callback,"✅ 已标记为已退款")
        else:
            await _safe_reply(callback,"⚠️ 退款失败，订单状态不符合条件", show_alert=True)

    except ValueError as e:
        logger.exception(f"处理退款失败: {e}")
        await _safe_reply(callback,"❌ 系统错误", show_alert=True)

    
# -------------------------------
# ✅ 管理员回调处理
# -------------------------------
@router.callback_query(F.data.startswith("pay_order"))
async def handle_pay_order(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await _safe_reply(callback,"🚫 你没有权限操作", show_alert=True)
        return
    if not callback.data:
        await _safe_reply(callback,"⚠️ 回调参数错误", show_alert=True)
        return
    
    order_id = parse_order_id(callback, "pay_order")
    if not order_id:
        await _safe_reply(callback,"⚠️ 参数错误", show_alert=True)
        return
    async with get_async_session() as session:
        success = await mark_order_paid(order_id, payment_id="manual", db=session)
        if not success:
            await _safe_reply(callback,"❌ 标记失败")
            return
        order = await get_order_by_id(session=session, order_id=order_id)
    if order:
        await _safe_reply(callback,f"✅ 已标记为已支付，订单状态：{order.status}")
    else:
        await _safe_reply(callback,"❌ 找不到该订单")

@router.callback_query(F.data.startswith("ship_order"))
async def handle_ship_order(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await _safe_reply(callback,"🚫 你没有权限执行发货", show_alert=True)
        return
    if not callback.data:
        await _safe_reply(callback,"⚠️ 回调参数错误", show_alert=True)
        return
    order_id = parse_order_id(callback, "ship_order")
    if not order_id:
        await _safe_reply(callback,"⚠️ 参数错误", show_alert=True)
        return
    async with get_async_session() as session:
        success = await mark_order_as_shipped(order_id, session)
    if success:
        await _safe_reply(callback,f"✅ 订单 {order_id} 已标记为已发货")
    else:
        await _safe_reply(callback,f"❌ 标记失败（订单状态不是已支付）", show_alert=True)
