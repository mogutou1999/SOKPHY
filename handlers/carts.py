# handlers/carts.py
import uuid
from uuid import UUID
import logging
from utils.alipay import generate_alipay_qr, verify_alipay_sign
from aiogram import Router, types, F
from aiogram.types import Message,InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime, timezone
from db.crud import CartCRUD
from db.models import User, Order
from utils.decorators import db_session, handle_errors
from services.carts import CartService
from db.session import get_async_session
from utils.formatting import _safe_reply

logger = logging.getLogger(__name__)
router = Router()


def setup_cart_handlers(router_: Router):
    router_.include_router(router)

@router.message(Command("cart"))
@handle_errors
@db_session
async def show_cart(message: Message):
    if not message.from_user or not getattr(message.from_user, "id", None):
        await _safe_reply(message, "⚠️ 无法获取用户 ID")
        return

    user_id = message.from_user.id
    try:
        user_uuid = UUID(str(user_id))
    except ValueError:
        await _safe_reply(message,"⚠️ 用户 ID 格式错误")
        return

    async with get_async_session() as session:
        items = await CartCRUD.get_cart_items(session, user_uuid)
        if not items:
            await _safe_reply(message,"🛒 你的购物车为空")
            return

        # 文本
        text = "🛒 你的购物车：\n\n"
        for i, item in enumerate(items, start=1):
            text += f"{i}. {item.product_name} — ¥{item.unit_price} x {item.quantity}\n"

        # 构建按钮
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{item.product_name} — ¥{item.unit_price} x {item.quantity}",
                    callback_data=f"buy:{item.product_id}"
                )] for item in items
            ]
        )

        # 添加清空购物车按钮
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text="清空购物车", callback_data="cart_clear")]
        )

        await _safe_reply(message,text, reply_markup=kb)

# ----------------------------
# 添加商品到购物车
# ----------------------------
@router.message(Command("add"))
@handle_errors
async def add_to_cart(message: types.Message, command: CommandObject):
    if not message.from_user:
        await _safe_reply(message,"⚠️ 无法获取用户信息")
        return

    args = command.args.split() if command.args else []
    if len(args) < 2:
        await _safe_reply(message,"❌ 用法: /add <商品ID> <数量>")
        return

    try:
        product_id = UUID(args[0])
        quantity = int(args[1])
        if not (1 <= quantity <= 100):
            raise ValueError()
    except ValueError:
        await _safe_reply(message,"❌ 商品ID或数量无效（数量1-100）")
        return

    async with get_async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await _safe_reply(message,"⚠️ 用户未注册")
            return
        
        msg = await CartService.add_product_to_cart(
            session,
            user_id=user.id,  
            product_id=product_id,
            quantity=quantity  
        )
        await _safe_reply(message,msg["message"])


# ----------------------------
# 从购物车移除商品
# ----------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("cart_remove:"))
@handle_errors
async def remove_item(callback: CallbackQuery):
    if not callback.data:
        await _safe_reply(callback,"⚠️ 参数错误", show_alert=True)
        return
    product_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    try:
        user_uuid = UUID(str(user_id))
        product_uuid = UUID(product_id)
    except ValueError:
        await _safe_reply(callback,"⚠️ ID 格式错误", show_alert=True)
        return

    async with get_async_session() as session:
        success = await CartCRUD.remove_item(session, user_uuid, product_uuid)
        if success:
            await _safe_reply(callback,"✅ 已删除该商品")
        else:
            await _safe_reply(callback,"❌ 删除失败", show_alert=True)
            
@router.callback_query(lambda c: c.data == "cart_clear")
@handle_errors
async def clear_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        user_uuid = UUID(str(user_id))
    except ValueError:
        await _safe_reply(callback,"⚠️ 用户 ID 格式错误", show_alert=True)
        return

    async with get_async_session() as session:
        success = await CartCRUD.clear_cart(session, user_uuid)
        if success:
            await _safe_reply(callback,"✅ 已清空购物车")
        else:
            await _safe_reply(callback,"❌ 清空失败", show_alert=True)           
            
@router.message(F.text == "/checkout")
@handle_errors
async def checkout(message: Message):
    if not message.from_user:
        await _safe_reply(message,"⚠️ 无法获取用户信息")
        return
    
    user_id = message.from_user.id
    async with get_async_session() as session:
        # 查询用户
        stmt = select(User).where(User.telegram_id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            await _safe_reply(message,"⚠️ 请先 /start 注册")
            return

        # TODO: 获取用户购物车内容
        cart_items = [{"id": 1, "name": "Demo Product", "qty": 2, "price": 9.99}]
        total_amount = sum(item["qty"] * item["price"] for item in cart_items)

        # 生成唯一订单号
        out_no = str(uuid.uuid4())

        # 创建订单
        order = Order(
            user_id=user.id,
            products=cart_items,
            total_amount=total_amount,
            status="pending",
            out_no=out_no,
            created_at=datetime.now(timezone.utc)
        )
        session.add(order)
        await session.commit()

        # 调用支付宝生成二维码
        qr_url = generate_alipay_qr(out_no=out_no, amount=total_amount)
        await _safe_reply(message,f"🛒 订单已生成：{out_no}\n请扫码支付：\n{qr_url}")            
