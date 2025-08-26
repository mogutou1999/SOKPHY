# handlers/products.py
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from db.session import get_async_session,settings
from db.models import Product, User, Order, OrderItem, CartItem
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from utils.decorators import handle_errors, db_session
from db.crud import ProductCRUD
from config.settings import get_app_settings
from typing import  Any

logger = logging.getLogger(__name__)
router = Router()
settings = get_app_settings()
admin_ids = settings.admin_ids 
__all__ = ["router", "setup_products_handlers", "create_product"]

async def get_product_by_id(db: AsyncSession, product_id: int) -> dict[str, Any] | None:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return None
    return {
        "id": product.id,
        "name": product.name,
        "price": float(product.price),
        "stock": product.stock,
        "description": product.description,
        "is_active": product.is_active,
    }

@router.message(Command("show_products"))
async def show_products(msg: types.Message):
    print("show_products triggered")
    async with get_async_session() as session:
        products = await ProductCRUD.list_active(session)
        print("products:", products)
        if not products:
            await msg.answer("暂无商品上架")
            return
        for p in products:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="加入购物车", callback_data=f"add:{p.id}"),
                        InlineKeyboardButton(text="立即购买", callback_data=f"buy:{p.id}"),
                    ]
                ]
            )
            await msg.answer(f"{p.name} - ¥{p.price}\n库存: {p.stock}", reply_markup=keyboard)

def setup_products_handlers(dp: Router):
    dp.include_router(router)

@router.message(Command("add_product"))
@handle_errors
@db_session
async def add_product(message: types.Message, db: AsyncSession):
    """
    管理员通过 /add_product 名称|价格|库存|描述 添加商品
    示例：
    /add_product 商品C|29.9|20|商品C描述
    """
    if not message.from_user:
        await message.answer("⚠️ 无法获取用户信息")
        return

    # 检查管理员身份
    if message.from_user.id not in settings.admin_ids:
        await message.answer("⚠️ 你没有权限执行此操作")
        return

    # 解析参数
    if not message.text or "|" not in message.text:
        await message.answer("❌ 请提供参数: 名称|价格|库存|描述")
        return

    try:
        _, params = message.text.split(" ", 1)
        name, price, stock, description = params.split("|")
        price = float(price)
        stock = int(stock)
    except ValueError:
        await message.answer("❌ 参数格式错误，请使用：名称|价格|库存|描述")
        return

    # 添加到数据库
    product = Product(
        name=name.strip(),
        price=price,
        stock=stock,
        description=description.strip(),
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    await message.answer(f"✅ 商品已添加：{product.name} ¥{product.price} 库存:{product.stock}")
# -----------------------------
# 创建商品（管理员用）
# -----------------------------
async def create_product(name: str, description: str, price: float, stock: int, session: AsyncSession):
    product = Product(
        name=name,
        description=description,
        price=price,
        stock=stock,
        is_active=True,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


# -----------------------------
# 查询全部商品
# -----------------------------
async def get_all_products(db: AsyncSession):
    result = await db.execute(select(Product).where(Product.is_active == True))
    return result.scalars().all()


# -----------------------------
# 查看商品列表，生成购买按钮
# -----------------------------
@router.message(F.text.in_({"/products", "/show_products"}))
async def list_products(message: types.Message):
    async with get_async_session() as session:
        result = await session.execute(
            select(Product).where(Product.is_active == True)
        )
        products = result.scalars().all()
        return products
    if not products:
        await message.answer("📭 当前没有上架的商品")
        return

    for p in products:
        # 按钮：加入购物车 / 立即购买
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"🛒 加入购物车", callback_data=f"addcart:{p.id}")],
                [InlineKeyboardButton(text=f"💳 立即购买 {p.price} 元", callback_data=f"buy:{p.id}")]
            ]
        )

        caption = f"📦 <b>{p.name}</b>\n💰 价格: {p.price} 元\n📦 库存: {p.stock}\n\n{p.description or ''}"

        if p.image_url:  # 如果商品有图片
            await message.answer_photo(photo=p.image_url, caption=caption, reply_markup=keyboard)
        else:
            await message.answer(caption, reply_markup=keyboard)

# -----------------------------
# 购买回调
# -----------------------------
@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    @handle_errors
    async def _inner(callback: types.CallbackQuery):
        if not callback.data:
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return       
        product_id = int(callback.data.split(":")[1])
        async with get_async_session() as db:
            product = await db.get(Product, product_id)
            user = await db.get(User, callback.from_user.id)
            if not product or not user:
                await callback.answer("❌ 商品不存在", show_alert=True)
                return
            # 创建订单
            total_amount = Decimal(str(product.price))
            order = Order(user_id=user.id, total_amount=total_amount)
            db.add(order)
            await db.flush()
            db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1, unit_price=total_amount))
            await db.commit()

            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=1,
                unit_price=total_amount,
            )
            db.add(order_item)
            await db.commit()

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="去支付", callback_data=f"pay:{order.id}")]
            ])

            msg = getattr(callback, "message", None)
            if msg and hasattr(msg, "edit_text"):
                await msg.edit_text(
                    f"✅ 下单成功！\n🧾 订单号: {order.id}\n📦 商品: {product.name}\n💵 金额: ¥{total_amount:.2f}",
                    reply_markup=kb,
                )
            elif callback.bot:
                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text=f"✅ 下单成功！\n🧾 订单号: {order.id}\n📦 商品: {product.name}\n💵 金额: ¥{total_amount:.2f}",
                )

    return await _inner(callback)


# -----------------------------
# 添加到购物车
# -----------------------------
@router.callback_query(F.data.startswith("add_cart:"))
async def add_to_cart(callback: types.CallbackQuery):
    @handle_errors
    @db_session
    async def _inner(callback: types.CallbackQuery, db: AsyncSession):
        if not callback.data:
            await callback.answer("⚠️ 参数错误", show_alert=True)
            return

        parts = callback.data.split(":")
        product_id = int(parts[1])
        tg_id = callback.from_user.id

        result = await db.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("⚠️ 用户未注册", show_alert=True)
            return

        product = await db.get(Product, product_id)
        if not product:
            await callback.answer("⚠️ 商品不存在", show_alert=True)
            return

        cart_item = CartItem(
            user_id=user.id,
            product_id=product.id,
            product_name=product.name,
            unit_price=float(product.price),
            quantity=1,
        )
        db.add(cart_item)
        await db.commit()

        await callback.answer(f"✅ 已加入购物车：{product.name}", show_alert=False)

    return await _inner(callback)
