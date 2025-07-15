import logging
from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import CartItem, Product
from utils.decorators import db_session, handle_errors
from config.settings import settings
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()


ADMIN_IDS = settings.admin_ids


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def setup_cart_handlers(router: Router) -> None:
    cart_router = Router()

    @cart_router.message(F.text == "/cart")
    async def handle_cart(message: Message) -> None:
        await message.answer("✅ Carts handler: /cart 命令收到。")

    router.include_router(cart_router)


@router.message(Command("cart"))
@handle_errors
@db_session
async def view_cart(message: types.Message, db: AsyncSession):
    user_id = message.from_user.id  # type: ignore[attr-defined]

    result = await db.execute(select(CartItem).where(CartItem.user_id == user_id))
    items = result.scalars().all()

    if not items:
        await message.answer("🛒 你的购物车是空的，发送 /menu 查看商品列表。")
        return

    text_lines = ["🛒 <b>你的购物车</b>:\n"]
    total = 0.0
    for item in items:
        subtotal = item.quantity * item.unit_price
        total += subtotal
        text_lines.append(f"{item.product_name} × {item.quantity} = ¥{subtotal:.2f}")

    text_lines.append(f"\n💰 <b>总计：</b> ¥{total:.2f}")
    await message.answer("\n".join(text_lines), parse_mode="HTML")


@router.message(Command("add"))
@handle_errors
@db_session
async def add_to_cart(message: types.Message, command: CommandObject, db: AsyncSession):
    user_id = message.from_user.id  # type: ignore[attr-defined]
    args = command.args.split() if command.args else []

    try:
        product_id = int(args[0])
        quantity = int(args[1])
        if not (1 <= quantity <= 100):
            raise ValueError()
    except (IndexError, ValueError):
        await message.answer(
            "❌ 无效参数。请使用正确格式：/add <商品ID> <数量>（1-100）"
        )
        return

    product = await db.get(Product, product_id)
    if not product:
        await message.answer("❌ 没有找到该商品。")
        return

    result = await db.execute(
        select(CartItem).where(
            CartItem.user_id == user_id, CartItem.product_id == product_id
        )
    )
    cart_item = result.scalar_one_or_none()

    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(
            user_id=user_id,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
        )
        db.add(cart_item)

    await db.commit()
    await message.answer(f"✅ 已添加 {product.name} × {quantity} 到购物车。")


@router.message(Command("remove"))
@handle_errors
@db_session
async def remove_from_cart(
    message: types.Message, command: CommandObject, db: AsyncSession
):
    user_id = message.from_user.id  # type: ignore[attr-defined]
    args = command.args.split() if command.args else []

    if not args:
        await message.answer("用法：/remove <商品ID>")
        return

    try:
        product_id = int(args[0])
    except ValueError:
        await message.answer("❌ 无效的商品ID。")
        return

    result = await db.execute(
        select(CartItem).where(
            CartItem.user_id == user_id, CartItem.product_id == product_id
        )
    )
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        await message.answer("❌ 购物车中没有这个商品。")
        return

    await db.delete(cart_item)
    await db.commit()
    await message.answer(f"🗑️ 已从购物车移除商品 ID: {product_id}。")
