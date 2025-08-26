# handlers/carts.py
import logging
from aiogram import Router, types, Dispatcher
from aiogram.filters import Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from db.models import CartItem
from utils.decorators import db_session, handle_errors
from services.carts import CartService

logger = logging.getLogger(__name__)
router = Router()


def setup_cart_handlers(router_: Router):
    router_.include_router(router)


@router.message(Command("cart"))
@handle_errors
@db_session
async def view_cart(message: types.Message, db: AsyncSession):
    user_id = getattr(message.from_user, "id", 0)
    if not user_id:
        await message.answer("⚠️ 无法获取用户ID")
        return

    result = await db.execute(select(CartItem).where(CartItem.user_id == user_id))
    items = result.scalars().all()

    if not items:
        await message.answer("🛒 你的购物车是空的，发送 /products 查看商品列表。")
        return

    total = Decimal("0")
    lines = ["🛒 <b>你的购物车</b>:\n"]
    for item in items:
        subtotal = Decimal(item.unit_price) * item.quantity
        total += subtotal
        lines.append(f"{item.product_name} × {item.quantity} = ¥{subtotal:.2f}")

    lines.append(f"\n💰 <b>总计：</b> ¥{total:.2f}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("add"))
@handle_errors
@db_session
async def add_to_cart(message: types.Message, command: CommandObject, db: AsyncSession):
    if not message.from_user:
        await message.answer("⚠️ 无法获取用户信息")
        return
    user_id = message.from_user.id
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

    msg = await CartService.add_product_to_cart(
        db=db, user_id=user_id, product_id=product_id, quantity=quantity
    )
    await message.answer(msg)


@router.message(Command("remove"))
@handle_errors
@db_session
async def remove_from_cart(
    message: types.Message, command: CommandObject, db: AsyncSession
):
    user_id = getattr(message.from_user, "id", 0)
    if not user_id:
        await message.answer("⚠️ 无法获取用户ID")
        return

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
