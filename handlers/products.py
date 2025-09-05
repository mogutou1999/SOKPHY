# handlers/products.py
import logging
from aiogram import Router, types,F
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_async_session,settings
from db.models import Product, User
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, BufferedInputFile
from utils.decorators import handle_errors, db_session,user_required
from db.crud import ProductCRUD, OrderCRUD, CartCRUD
from config.settings import get_app_settings
from typing import  Any,cast
from utils.formatting import format_product_detail, _safe_reply
from uuid import UUID
from services.products import get_all_products, get_product_by_id
from services.orders import create_order
from utils.admin_session import AdminProductSession
from handlers.payment import generate_payment_qr
from services.payment_service import PaymentService
logger = logging.getLogger(__name__)
router = Router()
admin_ids = settings.admin_ids 
# 临时存储管理员输入信息
admin_product_data: dict[int, dict] = {}
price_temp: dict[int, float] = {}
stock_temp: dict[int, int] = {}
__all__ = ["router"]




# ----------------------------
# 1️⃣ 管理员发送 
# ----------------------------
@router.message(Command("add_product"))
@user_required(admin_only=True)
async def add_product_start(message: Message):
    if not message.from_user:
        await _safe_reply(message,"⚠️ 无法获取用户信息")
        return

    if message.from_user.id not in settings.admin_ids:
        await _safe_reply(message,"⚠️ 你没有权限执行此操作")
        return

    text = message.text
    if not text or " " not in text:
        await _safe_reply(message,"❌ 请提供商品名称（可选描述）：名称|描述")
        return

    try:
        _, params = text.split(" ", 1)
        parts = params.split("|")
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
    except Exception:
        await _safe_reply(message,"❌ 参数格式错误，请使用：名称|可选描述")
        return


    admin_product_data[message.from_user.id] = {
        "name": name,
        "description": description
    }

    # 构建价格选择和库存选择按钮
    price_buttons = [
        InlineKeyboardButton(text=f"¥{p}", callback_data=f"set_price:{name}:{p}")
        for p in [0.5, 1, 5, 10, 20, 50, 100]
    ]
    stock_buttons = [
        InlineKeyboardButton(text=f"{s}", callback_data=f"set_stock:{name}:{s}")
        for s in [1, 5, 10, 20, 50, 100]
    ]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            price_buttons,
            stock_buttons,
        ]
    )

    await _safe_reply(message, f"🛠️ 添加商品：{name}\n请选择价格和库存:", reply_markup=kb)

@router.message(Command("products"))
async def list_products(msg: types.Message):
    products = await get_all_products()
    for product in products:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🛒 加入购物车", callback_data=f"add_cart:{product.id}"),
                InlineKeyboardButton(text="💰 立即购买", callback_data=f"buy:{product.id}")
            ]]
        )
        await msg.answer(format_product_detail(product), reply_markup=kb)


# ----------------------------
# 回调选择价格\ 
# ----------------------------
@router.callback_query(F.data.startswith("set_stock:"))
async def handle_set_stock(callback: CallbackQuery):
    try:
        if not callback.data:
            await _safe_reply(callback,"数据异常", show_alert=True)
            return

        parts = callback.data.split(":")
        if len(parts) != 3:
            await _safe_reply(callback,"数据异常", show_alert=True)
            return
        
        _, name, stock = parts
        stock_temp[callback.from_user.id] = int(stock)
        await _safe_reply(callback,f"✅ 已选择库存 {stock}", show_alert=True)

        price = price_temp.get(callback.from_user.id)
        if price is None:
            await _safe_reply(callback,"⚠️ 请先选择价格", show_alert=True)
            return

        info = admin_product_data.get(callback.from_user.id, {})
        description = info.get("description", "")
        
        async with get_async_session() as session:
            product = Product(
                name=name,
                price=price,
                stock=int(stock),
                description=description,
                is_active=True,
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)

        # 使用 _safe_reply 代替直接 edit_text，兼容更多场景
        msg = callback.message
        if isinstance(msg, Message):
            await _safe_reply(callback, f"✅ 商品已添加：{product.name} ¥{product.price} 库存:{product.stock}")
        else:
            # 如果消息不可访问，改用 callback.answer 弹窗提示用户
            await callback.answer(f"✅ 商品已添加：{product.name} ¥{product.price} 库存:{product.stock}", show_alert=True)          
        price_temp.pop(callback.from_user.id, None)
        stock_temp.pop(callback.from_user.id, None)
        admin_product_data.pop(callback.from_user.id, None)
              
        AdminProductSession.set_stock(callback.from_user.id, int(stock))
        
    except Exception as e:
        logger.exception(f"添加商品失败: {e}")
        await _safe_reply(callback,"❌ 添加商品失败", show_alert=True)

@router.callback_query(lambda c: c.data and c.data.startswith("set_price:"))
async def set_price_callback(cb: types.CallbackQuery):
    data = cb.data
    if not data:
        await _safe_reply(cb, "❌ 数据为空", show_alert=True)
        return

    try:
        # 解析数据
        _, name, price = data.split(":")
        user_id = cb.from_user.id
        price_float = float(price)
        price_temp[cb.from_user.id] = price_float
        # 设置价格到临时 session
        AdminProductSession.set_price(cb.from_user.id, float(price))
        # ✅ 获取用户会话（如已有数据）
        session = AdminProductSession.get(user_id)
        
        await _safe_reply(cb,f"✅ 价格已设置: ¥{price}")
        # 你也可以在这里判断：如果库存也设置了，就可以入库
        if session and "stock" in session:
            stock = session["stock"]
            description = session.get("description", "")
            async with get_async_session() as db:
                product = Product(
                    name=name,
                    price=float(price),
                    stock=stock,
                    description=description,
                    is_active=True
                )
                db.add(product)
                await db.commit()
                await _safe_reply(cb,f"✅ 商品添加成功：{name} ¥{price} 库存:{stock}")
                AdminProductSession.clear(user_id)
    except ValueError:
        await _safe_reply(cb, "❌ 数据格式错误", show_alert=True)

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
        await _safe_reply(callback,"⚠️ 参数错误", show_alert=True)
        return

    try:
        product_id = UUID(callback.data.split(":")[1])
    except Exception:
        await _safe_reply(callback,"⚠️ 商品ID格式错误", show_alert=True)
        return

    tg_id = callback.from_user.id

    result = await db.execute(select(User).where(User.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        await _safe_reply(callback,"⚠️ 用户未注册", show_alert=True)
        return

    product = await ProductCRUD.get_by_id(db, product_id)
    if not product:
        await _safe_reply(callback,"⚠️ 商品不存在", show_alert=True)
        return

    # 调用统一的 CartCRUD.add_item 方法，避免重复添加商品
    try:
        cart_item = await CartCRUD.add_item(
            db,
            user_id=user.id,
            product_id=product.id,
            quantity=1,
            product_name=product.name,
            unit_price=product.price,
        )
    except Exception as e:
        logger.error(f"加入购物车失败: {e}")
        await _safe_reply(callback,"❌ 加入购物车失败", show_alert=True)
        return

    await _safe_reply(callback,f"✅ 已加入购物车：{product.name}", show_alert=False)
