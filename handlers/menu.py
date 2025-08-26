# handlers/menu.py
from uuid import UUID
from typing import List, Optional, Dict, Any, Union, Sequence
from aiogram import Router, types, F
from sqlalchemy import select
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
import logging
from db.session import get_async_session
from db.models import Product, Order, User
from services.carts import CartService
from handlers.products import get_all_products, get_product_by_id
from services.orders import create_order, mark_order_paid, get_order_by_id
from services import orders as order_service

ReplyMarkup = Union[ReplyKeyboardMarkup, InlineKeyboardMarkup]

router = Router()
logger = logging.getLogger(__name__)


async def get_product_by_id(
    db: AsyncSession, product_id: int
) -> Optional[Dict[str, Any]]:
    result = await db.execute(select(Product).where(Product.id == product_id))
    p = result.scalar_one_or_none()
    if not p:
        return None
    return {
        "id": p.id,
        "name": p.name,
        "price": float(p.price),
        "stock": p.stock,
        "description": p.description,
    }


# ----------------------------
# 内联菜单构建
# ----------------------------
async def build_product_menu(products: Sequence[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in products:
        kb.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{p.name} ￥{p.price}", callback_data=f"product_detail:{p.id}"
                )
            ]
        )
    return kb


async def build_pay_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 去支付", callback_data=f"pay:{order_id}")]
        ]
    )


# ----------------------------
# 智能回复
# ----------------------------
async def _safe_reply(
    event: Union[Message, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    show_alert: bool = False,
):
    if isinstance(event, Message):
        await event.answer(text, reply_markup=reply_markup)
    elif isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            try:
                await event.message.edit_text(text, reply_markup=reply_markup)
            except Exception:
                # 例如消息已被修改/删除
                await event.answer("⚠️ 无法修改消息", show_alert=True)
        else:
            await event.answer(text, show_alert=show_alert)


# ----------------------------
# 展示商品菜单
# ----------------------------
@router.message(F.text == "menu")
@router.callback_query(F.data == "open_menu")
async def show_product_menu(event: Union[Message, CallbackQuery]):
    async with get_async_session() as session:
        try:
            stmt = select(Product).where(Product.is_active == True)
            result = await session.execute(stmt)
            products: Sequence[Product] = result.scalars().all()

            if not products:
                await _safe_reply(event, "❌ 暂无商品上架")
                return

            kb = await build_product_menu(products)
            await _safe_reply(event, "🛍️ 请选择商品：", reply_markup=kb)
        except Exception as e:
            logger.exception(f"加载商品菜单失败: {e}")
            await _safe_reply(event, "❌ 商品加载失败，请稍后重试")


# ----------------------------
# 商品详情
# ----------------------------
async def build_product_detail_kb(
    product_id: Union[int, str, UUID],
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 加入购物车", callback_data=f"add_to_cart:{product_id}:1"
                )
            ],
            [InlineKeyboardButton(text="🔙 返回菜单", callback_data="open_menu")],
        ]
    )


@router.callback_query(F.data.startswith("product_detail:"))
async def show_product_detail(callback: types.CallbackQuery):
    if not callback.data:
        await callback.answer("数据异常", show_alert=True)
        return

    async with get_async_session() as session:
        try:
            product_id_str = callback.data.split(":")[1]
            # 支持 UUID 获取
            product = await session.get(Product, UUID(product_id_str))
            if not product:
                await callback.answer("❌ 商品不存在", show_alert=True)
                return

            text = (
                f"📦 商品：{product.name}\n"
                f"💰 价格：¥{product.price}\n"
                f"📝 介绍：{product.description}"
            )

            kb = await build_product_detail_kb(product.id)

            if isinstance(callback.message, Message):
                try:
                    await callback.message.edit_text(text, reply_markup=kb)
                except Exception:
                    await callback.answer("⚠️ 无法修改消息", show_alert=True)
            else:
                await callback.answer(text, show_alert=True)

        except Exception as e:
            logger.exception(f"商品详情展示失败: {e}")
            await callback.answer("❌ 加载失败，请稍后重试", show_alert=True)


# ----------------------------
# 加入购物车（累加）
# ----------------------------
@router.callback_query(F.data.startswith("add_to_cart:"))
async def handle_add_to_cart(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("数据异常", show_alert=True)
        return

    async with get_async_session() as session:
        try:
            parts = callback.data.split(":")
            product_id = int(parts[1])
            quantity = int(parts[2])
            user_id = callback.from_user.id

            msg = await CartService.add_product_to_cart(
                db=session,
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
            )

            await callback.answer(f"✅ 已加入购物车 x{quantity}")
        except Exception as e:
            logger.exception(f"加入购物车失败: {e}")
            await callback.answer("❌ 加入购物车失败", show_alert=True)


# ----------------------------
# 下单并支付
# ----------------------------
@router.callback_query(F.data.startswith("pay:"))
async def handle_pay(callback: CallbackQuery):
    data = callback.data
    if not data:
        await callback.answer("数据异常", show_alert=True)
        return

    order_id = int(data.split(":")[1])

    async with get_async_session() as session:
        try:
            # 标记支付
            success = await mark_order_paid(db=session, order_id=order_id)
            if not success:
                await callback.answer("❌ 订单不存在或支付失败", show_alert=True)
                return

            # 查询订单对象
            order = await get_order_by_id(session=session, order_id=order_id)
            if not order:
                await callback.answer("❌ 无法获取订单详情", show_alert=True)
                return

            # 发送成功消息
            text = f"✅ 支付成功！\n📦 订单号: {order.id}\n💵 总金额: ¥{order.total_amount}"
            if isinstance(callback.message, Message):
                await callback.message.edit_text(text)
        except Exception as e:
            logger.exception(f"支付失败: {e}")
            await callback.answer("❌ 支付失败，请稍后重试", show_alert=True)


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery):
    async with get_async_session() as session:  # 异步上下文会话
        try:
            if not callback.data:
                await callback.answer("数据异常", show_alert=True)
                return

            # 安全解析 product_id
            parts = callback.data.split(":")
            if len(parts) < 2 or not parts[1].isdigit():
                await callback.answer("数据异常", show_alert=True)
                return

            product_id = int(parts[1])
            product = await get_product_by_id(session, product_id)

            if not product:
                await callback.answer("❌ 商品不存在", show_alert=True)
                return

            user_id = callback.from_user.id
            total_amount = Decimal(str(product["price"]))

            # 创建订单，这里 create_order 返回 dict
            order = await create_order(
                user_id=user_id,
                total_amount=total_amount,
                db=session
            )

            text = (
                f"✅ 下单成功！\n"
                f"🧾 订单号: {order['id']}\n"
                f"📦 商品: {product['name']}\n"
                f"💵 金额: ￥{total_amount}\n"
                f"状态: {order['status']}\n\n"
                f"请点击下方按钮完成支付 👇"
            )

            kb = await build_pay_kb(order["id"])

            if isinstance(callback.message, Message):
                await callback.message.edit_text(text, reply_markup=kb)

        except Exception as e:
            logger.exception(f"创建订单失败: {e}")
            await callback.answer("❌ 下单失败，请稍后重试", show_alert=True)
