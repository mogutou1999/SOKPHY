# services/orders.py

from typing import Union, Optional, Sequence
import logging
from sqlalchemy import update, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from db.session import async_session_maker

from config.settings import settings
from db.models import Order, OrderStatus

from utils.formatter import format_order_detail

ADMIN_IDS = settings.admin_ids or []


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


router = Router(name="order")
logger = logging.getLogger(__name__)


async def create_order(session: AsyncSession, user_id: int, item_id: int) -> Order:
    # ⏪ 举个例子，自己改
    new_order = Order(user_id=user_id, item_id=item_id)
    session.add(new_order)
    await session.commit()
    await session.refresh(new_order)
    return new_order


# ✅ 标记订单已支付（演示）
@router.callback_query(F.data.startswith("pay_order:"))
async def handle_pay_order(callback: CallbackQuery):
    user_id = callback.from_user.id

    if not is_admin(user_id):
        await callback.answer("🚫 你没有权限操作", show_alert=True)
        return

    parts = (callback.data or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer("⚠️ 参数错误", show_alert=True)
        return

    order_id = int(parts[1])
    async with async_session_maker() as session:
        success = await mark_order_paid(db=session, order_id=order_id)

    if success:
        await callback.answer("✅ 已标记为已支付")
    else:
        await callback.answer("❌ 更新失败", show_alert=True)


# ✅ 创建一个测试订单
@router.message(Command("new_order"))
async def handle_new_order(message: Message):
    if not message.from_user:
        await message.answer("❌ 无法识别用户信息")
        return
    user_id = message.from_user.id

    async with async_session_maker() as db:
        new_order = await create_order(db, user_id, total_amount=99.99)

    await message.answer(
        f"✅ 已创建新订单 ID={new_order.id}，金额 ¥{new_order.total_amount:.2f}"
    )


async def get_user_order(session: AsyncSession, user_id: int):
    stmt = select(Order).where(Order.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalars().all()


# ✅ 命令处理
@router.message(Command("orders"))
async def handle_list_orders(message: Message):
    if not message.from_user:
        await message.answer("❌ 无法识别用户信息")
        return

    user_id = message.from_user.id

    async with async_session_maker() as db:
        orders = await get_user_order(db, user_id)

    if not orders:
        await message.answer("📭 你还没有订单")
        return

    text = "📦 <b>你的订单</b>\n\n"
    for order in orders:
        text += (
            f"- 订单号: <b>{order.id}</b>, "
            f"金额: ¥{order.total_amount:.2f}, "
            f"状态: {order.status}\n"
        )

    await message.answer(text, parse_mode="HTML")


async def _safe_reply(
    event: Union[Message, CallbackQuery], text: str, reply_markup=None
) -> None:
    if isinstance(event, Message):
        await event.answer(text, reply_markup=reply_markup)
    elif isinstance(event, CallbackQuery):
        if event.message:
            await event.message.answer(text, reply_markup=reply_markup)
        await event.answer()


# ----------------------------- 数据库操作函数 -----------------------------


async def get_order_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
    stmt = select(Order).where(Order.id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_unpaid_order(user_id: int, db: AsyncSession) -> Optional[Order]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id, Order.is_paid == False)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def mark_order_as_refunded(order_id: int, db: AsyncSession) -> bool:
    async with db.begin():
        result = await db.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status=OrderStatus.REFUNDED.value)
            .execution_options(synchronize_session="fetch")
        )
    return result.rowcount > 0


async def mark_order_paid(order_id: int, db: AsyncSession) -> bool:
    async with db.begin():
        result = await db.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status=OrderStatus.PAID.value)
            .execution_options(synchronize_session="fetch")
        )
    return result.rowcount > 0


async def mark_order_as_shipped(order_id: int, db: AsyncSession) -> bool:
    async with db.begin():
        result = await db.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.PAID.value)
            .values(status=OrderStatus.SHIPPED.value)
            .execution_options(synchronize_session="fetch")
        )
    return result.rowcount > 0


async def get_all_order(session: AsyncSession) -> Sequence[Order]:
    stmt = select(Order).order_by(desc(Order.created_at))
    result = await session.execute(stmt)
    return result.scalars().all()


# ----------------------------- Bot 处理函数 -----------------------------


@router.message(Command("pay"))
async def handle_payment(message: Message, bot: Bot):
    try:
        if not message.from_user:
            await message.answer("⚠️ 用户信息获取失败")
            return
        user_id = message.from_user.id

        async with async_session_maker() as session:
            order = await get_latest_unpaid_order(
                user_id, session
            )  # ✅ 传 user_id 而不是 order_id

        if not order:
            await message.answer("❌ 你没有未支付订单。")
            return

        # 后续处理，比如生成支付二维码等
        await message.answer(
            f"订单号：{order.id}\n金额：¥{order.total_amount:.2f}\n请扫码付款..."
        )
        # ...

    except Exception as e:
        logger.exception(f"处理支付失败: {e}")
        await message.answer("❌ 系统错误，无法获取订单")


@router.callback_query(F.data.startswith("order_detail:"))
async def show_order_detail(callback: CallbackQuery):
    try:
        if not callback.data:
            await callback.answer("⚠️ 回调数据为空", show_alert=True)
            return

        parts = callback.data.split(":")
        if len(parts) != 2 or not parts[1].isdigit():
            await callback.answer("⚠️ 回调格式错误", show_alert=True)
            return

        order_id = int(parts[1])

        async with async_session_maker() as session:
            order = await get_order_by_id(session, order_id)

        if not order:
            await callback.answer("❌ 订单不存在", show_alert=True)
            return

        detail = format_order_detail(order)
        await _safe_reply(callback, f"📦 订单详情：\n\n{detail}")

    except Exception as e:
        logger.exception(f"订单详情加载失败: {e}")
        await callback.answer("⚠️ 加载失败，请稍后再试", show_alert=True)


@router.message(Command("order_detail"))
async def handle_order_detail(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ 用法：/order_detail <订单ID>")
        return

    order_id = int(parts[1])
    async with async_session_maker() as db:
        stmt = await db.execute(select(Order).where(Order.id == order_id))
        order = stmt.scalar_one_or_none()

    if not order:
        await message.answer(f"❌ 未找到订单 {order_id}")
        return

    detail = format_order_detail(order)
    await message.answer(f"📄 订单详情：\n\n{detail}", parse_mode="HTML")


@router.callback_query(F.data.startswith("refund_order:"))
async def handle_refund_order(callback: CallbackQuery):
    try:
        if not callback.data:
            await callback.answer("⚠️ 回调数据为空", show_alert=True)
            return

        parts = callback.data.split(":")
        if len(parts) != 2 or not parts[1].isdigit():
            await callback.answer("⚠️ 回调格式错误", show_alert=True)
            return

        order_id = int(parts[1])

        async with async_session_maker() as session:
            success = await mark_order_as_refunded(order_id, session)

        if success:
            await callback.answer("✅ 已标记为已退款")
        else:
            await callback.answer("⚠️ 退款失败，订单状态不符合条件", show_alert=True)

    except Exception as e:
        logger.exception(f"处理退款失败: {e}")
        await callback.answer("❌ 系统错误", show_alert=True)
