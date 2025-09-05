# handlers/menu.py
from uuid import UUID
from typing import  Union, Sequence
from aiogram import Router, types, F
from sqlalchemy import select
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery,InlineKeyboardMarkup, InlineKeyboardButton,BufferedInputFile
from decimal import Decimal
import logging
from db.session import get_async_session
from db.models import Product, User
from db.crud import ProductCRUD, OrderCRUD, UserCRUD
from services.carts import CartService
from services import orders as order_service
from handlers.payment import PaymentService, generate_payment_qr
from utils.formatting import _safe_reply, build_product_menu, build_product_detail_kb
from utils.decorators import handle_errors

router = Router()
logger = logging.getLogger(__name__)


# ----------------------------
# 展示商品菜单
# ----------------------------
@router.message(Command("menu"))
async def handle_menu_command(message: Message):
    await show_product_menu_logic(message)
    
@router.callback_query(F.data == "open_menu")
async def handle_menu_callback(callback: CallbackQuery):
    await callback.answer()
    await show_product_menu_logic(callback)
    
async def show_product_menu_logic(event: Message | CallbackQuery):
    async with get_async_session() as session:
        stmt = select(Product).where(Product.is_active == True)
        result = await session.execute(stmt)
        products = result.scalars().all()

        if not products:
            await _safe_reply(event, "❌ 暂无商品上架")
            return

        kb = build_product_menu(products)
        await _safe_reply(event, "🛍️ 请选择商品：", reply_markup=kb)
  
@router.message(Command("products"))
@handle_errors
async def handle_products(message: Message):
    async with get_async_session() as session:
        products = await ProductCRUD.get_all(session)
        products = [p for p in products if p.is_active]
        if not products:
            await _safe_reply(message,"目前没有商品")
            return

        # 生成 InlineKeyboardMarkup（二维列表）
        inline_buttons = [
            [InlineKeyboardButton(text=f"{p.name} — ¥{p.price} (库存: {p.stock})", callback_data=f"buy:{p.id}")]
            for p in products
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

        await _safe_reply(message,
            "📦 可选商品列表：点击下方按钮直接购买",
            reply_markup=kb,
        )
# ----------------------------
# 商品详情
# ----------------------------
@router.callback_query(F.data.startswith("product_detail:"))
async def show_product_detail(callback: types.CallbackQuery):
    if not callback.data:
        await _safe_reply(callback, "⚠️ 数据异常", show_alert=True)
        return

    async with get_async_session() as session:
        try:
            product_id = UUID(callback.data.split(":")[1])
            product = await session.get(Product, product_id)

            if not product:
                await _safe_reply(callback, "❌ 商品不存在", show_alert=True)
                return

            text = (
                f"📦 商品：{product.name}\n"
                f"💰 价格：¥{product.price}\n"
                f"📝 介绍：{product.description or '暂无介绍'}"
            )

            # ✅ 同步函数，不需要 await
            kb = build_product_detail_kb(product.id)
            await _safe_reply(callback, text, reply_markup=kb)

        except ValueError as e:
            logger.exception(f"商品详情展示失败: {e}")
            await callback.answer("❌ 加载失败，请稍后重试", show_alert=True)


# ----------------------------
# 直接购买
# ----------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("buy:"))
@handle_errors
async def handle_buy(callback: CallbackQuery):
    if not callback.data:
        await _safe_reply(callback, "⚠️ 参数错误")
        return

    try:
        product_id = UUID(callback.data.split(":")[1])
    except Exception:
        await _safe_reply(callback, "⚠️ 商品ID格式错误")
        return

    async with get_async_session() as session:
        # 获取商品
        product = await ProductCRUD.get_by_id(session, product_id)
        if not product:
            await _safe_reply(callback, "❌ 商品不存在")
            return

        # 获取用户
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        if not user:
            await _safe_reply(callback, "⚠️ 用户未注册")
            return

        # 创建订单和订单项
        items = [{
            "product_id": product.id,
            "quantity": 1,
            "unit_price": product.price
        }]
        order = await OrderCRUD.create_with_items(session, user.id, items)
        if not order:
            await _safe_reply(callback, "❌ 创建订单失败")
            return

        # 生成支付链接和二维码
        payment_url = PaymentService.create_payment(
            order_id=str(order.id),
            amount=float(product.price),  # ✅ Decimal 转 float
        )
        qr_img = await generate_payment_qr(payment_url)
        photo = BufferedInputFile(qr_img.getvalue(), filename="qrcode.png")

        # 回复用户
        if callback.message and not isinstance(callback.message, types.InaccessibleMessage):
            await _safe_reply(callback.message, "✅ 下单成功！...", reply_markup=None)
        else:
            await callback.answer("✅ 下单成功！消息不可用，使用弹窗显示", show_alert=True)
            

# ----------------------------
# 下单并支付（引用 CartService）
# ----------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("pay:"))
async def handle_pay(callback: CallbackQuery):
    data = callback.data
    if not data:
        await _safe_reply(callback, "数据异常")
        return

    parts = data.split(":")
    if len(parts) < 3:
        await _safe_reply(callback, "支付参数不完整")
        return

    try:
        order_id = UUID(parts[1])
        payment_id = parts[2]
    except ValueError:
        await _safe_reply(callback, "支付参数无效")
        return

    async with get_async_session() as session:
        try:
            from services.orders import mark_order_paid, get_order_by_id

            success = await mark_order_paid(db=session, order_id=order_id, payment_id=payment_id)
            if not success:
                await _safe_reply(callback, "❌ 订单不存在或支付失败")
                return

            order = await get_order_by_id(session=session, order_id=order_id)
            if not order:
                await _safe_reply(callback, "❌ 无法获取订单详情")
                return

            text = f"✅ 支付成功！\n📦 订单号: {order.id}\n💵 总金额: ¥{order.total_amount}"
            await _safe_reply(callback, text)

        except Exception as e:
            logger.exception(f"支付失败: {e}")
            await _safe_reply(callback, "❌ 支付失败，请稍后重试")
            
