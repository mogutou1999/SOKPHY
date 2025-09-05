# services/products.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Product
from typing import Sequence,Any,List
from uuid import UUID
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.session import get_async_session
from utils.formatting import format_product_detail
from utils.formatting import _safe_reply





def translate(key: str, lang: str = "zh") -> str:
    translations = {
        "price": {"zh": "价格", "en": "Price"},
        "discount": {"zh": "折扣", "en": "Discount"},
        "sales": {"zh": "销量", "en": "Sales"},
        "stock": {"zh": "库存", "en": "Stock"},
    }
    return translations.get(key, {}).get(lang, key)

# ✅ 获取所有上架商品（传入 session 版本）
async def get_all_products() -> List[Product]:
    """获取所有上架商品"""
    async with get_async_session() as session:
        stmt = select(Product).where(Product.is_active == True)
        result = await session.execute(stmt)
        products = list(result.scalars().all())
        return products

def build_product_keyboard(product: Product) -> InlineKeyboardMarkup:
    buttons = []
    if product.stock > 0:
        buttons.append([InlineKeyboardButton(text="🛒 加入购物车", callback_data=f"addcart:{product.id}")])
        buttons.append([InlineKeyboardButton(text=f"💳 立即购买 {product.price} 元", callback_data=f"buy:{product.id}")])
    else:
        buttons.append([InlineKeyboardButton(text="❌ 已售罄", callback_data="soldout")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_product_caption(product: Product) -> str:
    return (
        f"📦 <b>{product.name}</b>\n"
        f"💰 价格: {product.price} 元\n"
        f"📦 库存: {product.stock}\n\n"
        f"{product.description or ''}"
    )

# ✅ 获取商品详情（字典格式）
async def list_active_products(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(Product).where(Product.is_active == True))
    products = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "price": float(p.price),
            "stock": p.stock,
            "description": p.description,
            "image_url": getattr(p, "image_url", None),
        }
        for p in products
    ]    

# ✅ 根据 ID 获取商品
async def get_product_by_id(db: AsyncSession, product_id: UUID) -> dict[str, Any] | None:
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

# ✅ 商品菜单展示
async def show_main_menu(callback: CallbackQuery):
    """展示商品菜单"""
    msg = callback.message
    if not isinstance(msg, Message):
        await _safe_reply(callback,"消息不可用", show_alert=True)
        return  

    async with get_async_session() as session:
        products = (await session.execute(select(Product))).scalars().all()

    if not products:
        await _safe_reply(msg or callback,"📭 暂无商品")
        return

    for product in products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛒 加入购物车", callback_data=f"addcart:{product.id}")],
                [InlineKeyboardButton(text=f"💳 立即购买 {product.price} 元", callback_data=f"buy:{product.id}")]
            ]
        )
        caption = (
            f"📦 <b>{product.name}</b>\n"
            f"💰 价格: {product.price} 元\n"
            f"📉 折扣: {getattr(product, 'discount', '无')}\n"
            f"🔥 销量: {getattr(product, 'sales', 0)} 件\n"
            f"📦 库存: {product.stock}\n\n"
            f"{product.description or ''}"
        )
        if product.image_url:
            await msg.answer_photo(photo=product.image_url, caption=caption, reply_markup=keyboard)
        else:
            await _safe_reply(msg or callback,caption, reply_markup=keyboard)

# ✅ 创建商品
async def create_product_db(name: str, price: float, stock: int) -> Product:
    """在数据库中创建商品"""
    async with get_async_session() as session:
        new_product = Product(name=name, price=price, stock=stock, is_active=True)
        session.add(new_product)
        await session.commit()
        await session.refresh(new_product)
        return new_product

# ✅ 更新商品库存
async def update_product_stock(product_id: UUID, stock: int) -> None:
    """更新商品库存"""
    async with get_async_session() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if product:
            product.stock = stock
            await session.commit()
