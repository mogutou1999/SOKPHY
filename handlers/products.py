# handlers/products.py
import logging
from aiogram import Router, F
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_async_session,settings
from db.models import Product, User
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, BufferedInputFile
from utils.decorators import handle_errors, db_session
from db.crud import ProductCRUD, OrderCRUD, CartCRUD
from utils.formatting import format_product_detail, _safe_reply
from uuid import UUID
from decimal import Decimal
from services.products import get_all_products
from handlers.payment import generate_payment_qr
from services.payment_service import PaymentService
logger = logging.getLogger(__name__)
router = Router()
admin_ids = settings.admin_ids 
# 临时存储管理员输入信息
admin_product_data: dict[int, dict] = {}
price_temp: dict[int, float] = {}
stock_temp: dict[int, int] = {}



@router.message(Command("products"))
async def list_products(message: Message):
    products = await get_all_products()
    if not products:
        return await _safe_reply(message, "📭 目前没有商品")
    for p in products:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛒 加入购物车", callback_data=f"add_cart:{p.id}"),
            InlineKeyboardButton(text="💰 立即购买", callback_data=f"buy:{p.id}")
        ]])
        await _safe_reply(message, format_product_detail(p), reply_markup=kb)



# -----------------------------
# 购买回调
# -----------------------------
@router.callback_query(F.data.startswith("buy:"))
@handle_errors
async def handle_buy(callback: CallbackQuery):
    if not callback.data:
        await _safe_reply(callback,"⚠️ 参数错误", show_alert=True)
        return

    try:
        product_id = UUID(callback.data.split(":")[1])
    except Exception:
        await _safe_reply(callback,"⚠️ 商品ID格式错误", show_alert=True)
        return

    async with get_async_session() as db:
        product = await ProductCRUD.get_by_id(db, product_id)
        if not product:
            await _safe_reply(callback,"❌ 商品不存在", show_alert=True)
            return

        # 获取用户
        result = await db.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await _safe_reply(callback, "⚠️ 用户未注册", show_alert=True)
            return

        # 创建订单和订单项
        items = [{"product_id": product.id, "quantity": 1, "unit_price": product.price}]
        order = await OrderCRUD.create_with_items(db, user.id, items)
        if not order:
            await _safe_reply(callback, "❌ 创建订单失败", show_alert=True)
            return
   
        # 生成支付链接
        payment_url = PaymentService.create_payment(str(order.id), float(product.price))
        qr_img = await generate_payment_qr(payment_url)
        photo = BufferedInputFile(qr_img.getvalue(), filename="qrcode.png")
  

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="去支付", callback_data=f"pay:{order.id}")]
        ])
        
        msg = callback.message
        caption = f"✅ 下单成功！\n🧾 订单号: {order.id}\n📦 商品: {product.name}\n💵 金额: ¥{product.price:.2f}"

        if isinstance(msg, Message):
            await _safe_reply(callback, caption, reply_markup=kb)
          
        else:       
            await _safe_reply(callback, 
                f"✅ 下单成功！\n🧾 订单号: {order.id}\n📦 商品: {product.name}\n💵 金额: ¥{product.price:.2f}",
                reply_markup=kb,
                show_alert=False
            )

# -----------------------------
# 添加到购物车
# -----------------------------
@router.callback_query(F.data.startswith("add_cart:"))
@handle_errors
@db_session
async def add_to_cart(callback: CallbackQuery, db: AsyncSession):
    if not callback.data:
        await _safe_reply(callback, "⚠️ 参数错误", show_alert=True)
        return

    # 解析 product_id
    try:
        product_id = UUID(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await _safe_reply(callback, "⚠️ 商品ID格式错误", show_alert=True)
        return

    tg_id = callback.from_user.id

    # 查询用户
    result = await db.execute(select(User).where(User.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        await _safe_reply(callback, "⚠️ 用户未注册", show_alert=True)
        return

    # 查询商品
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        await _safe_reply(callback, "⚠️ 商品不存在", show_alert=True)
        return

    # ✅ 这里 product.price 就是 Decimal 类型
    unit_price: Decimal = product.price

    # 添加到购物车
    try:
        cart_item = await CartCRUD.add_item(
            session=db,
            user_id=user.id,
            product_id=product.id,
            quantity=1,
            product_name=product.name,
            unit_price=unit_price,
        )
    except Exception as e:
        logger.error(f"加入购物车失败: {e}", exc_info=True)
        await _safe_reply(callback, "❌ 加入购物车失败", show_alert=True)
        return

    await _safe_reply(callback, f"✅ 已加入购物车：{product.name}", show_alert=False)
