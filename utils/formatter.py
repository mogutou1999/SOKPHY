# utils/formatting.py
from datetime import datetime
import logging
from typing import Any, Dict, Optional, Union, List,Sequence,cast
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from db.models import Product, Order, OrderStatus
from aiogram.types import Message as TgMessage, Message , CallbackQuery, InlineKeyboardButton,InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove,InaccessibleMessage
from sqlalchemy import update, select, insert
from db.session import get_async_session
from db.models import User, Product, CartItem, Order, OrderItem, OrderStatus, Role
from aiogram import types



logger = logging.getLogger(__name__)

ReplyMarkup = Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, None]

def parse_order_id(callback: CallbackQuery, prefix: str) -> Optional[UUID]:
    if not callback.data:
        return None
    parts = callback.data.split(":")
    if len(parts) != 2 or parts[0] != prefix:
        return None
    try:
        return UUID(parts[1])
    except ValueError:
        return None
    
def format_product_list(products: List[Dict]) -> str:
    """
    将商品列表格式化成字符串，用于发送给 Telegram 用户
    products: [{'id': 1, 'name': 'xxx', 'price': 10.0, 'stock': 5}, ...]
    """
    if not products:
        return "📦 当前没有商品。"

    lines = ["📦 <b>商品列表</b>:\n"]
    for p in products:
        lines.append(
            f"ID: {p['id']} | 名称: {p['name']} | 价格: ¥{p['price']} | 库存: {p['stock']}"
        )
    return "\n".join(lines)


def format_datetime(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_order_status(status: OrderStatus) -> str:
    mapping = {
        OrderStatus.PENDING: "⌛ 待支付",
        OrderStatus.UNPAID: "💤 未支付",
        OrderStatus.PAID: "✅ 已支付",
        OrderStatus.SHIPPED: "📦 已发货",
        OrderStatus.REFUNDED: "💸 已退款",
        OrderStatus.CANCELLED: "❌ 已取消",
    }
    return mapping.get(status, f"❓ 未知状态: {status}")


def format_product_detail(product: Product) -> str:
    return (
        f"🛍️ <b>{product.name}</b>\n"
        f"💰 价格: ¥{float(product.price):.2f}\n"
        f"📦 描述: {product.description or '暂无'}\n"
    )


def format_order_detail(order: Order) -> str:
    return (
        f"🧾 <b>订单详情</b>\n"
        f"🆔 ID: {order.id}\n"
        f"👤 用户: {order.user_id}\n"
        f"💵 金额: ¥{float(order.total_amount):.2f}\n"
        f"📦 状态: {format_order_status(order.status)}\n"
        f"📅 创建时间: {format_datetime(order.created_at)}"
    )

# ===============================
# 📌 5️⃣ 安全回复工具
# ===============================
ReplyMarkup = Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, None]

async def _safe_reply(
    target: Union[TgMessage, CallbackQuery, InaccessibleMessage],
    text: str,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None,
    show_alert: bool = False,
) -> None:
    try:
        if isinstance(target, TgMessage):
            await target.answer(text, reply_markup=reply_markup)
            return

        if isinstance(target, CallbackQuery):
            msg = target.message
            if msg is None:
                await target.answer(text, show_alert=show_alert)
                return

            # 强制告诉类型检查器 msg 是 Message 类型，避免报错
            msg = cast(TgMessage, msg)

            if reply_markup is None or isinstance(reply_markup, InlineKeyboardMarkup):
                try:
                    # 忽略编辑消息时的类型警告
                    await msg.edit_text(text, reply_markup=reply_markup)  # type: ignore
                    return
                except Exception as e_edit:
                    logger.warning(f"[edit_text 失败] {e_edit}, 尝试发送新消息")
                    bot = target.bot
                    assert bot is not None
                    await bot.send_message(
                        chat_id=msg.chat.id,
                        text=text,
                        reply_markup=reply_markup
                    )
                    return
            else:
                bot = target.bot
                assert bot is not None
                await bot.send_message(
                    chat_id=msg.chat.id,
                    text=text,
                    reply_markup=reply_markup
                )
                return

        logger.warning(f"_safe_reply: unsupported target type: {type(target)}")
    except Exception:
        logger.exception("❌ _safe_reply 执行失败（捕获异常）")

# ===============================
# 📌 6️⃣ 菜单生成工具
# ===============================
def build_product_detail_kb(product_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 立即购买", callback_data=f"buy:{product_id}"
                )
            ],
            [InlineKeyboardButton(text="🔙 返回菜单", callback_data="open_menu")],
        ]
    )

def build_product_menu(products: Sequence[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in products:
        kb.inline_keyboard.append(
            [InlineKeyboardButton(
                text=f"{p.name} ￥{p.price}",
                callback_data=f"product_detail:{p.id}"
            )]
        )
    return kb

async def build_pay_kb(order_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 去支付", callback_data=f"pay:{order_id}")]
        ]
    )

# === 配置模型 ===
class FormatterConfig(BaseModel):
    """格式化配置"""

    date_format: str = Field(default="%Y-%m-%d")
    max_decimal_places: int = Field(default=2, ge=0, le=6)
    phone_regex: str = Field(default=r"^1[3-9]\d{9}$")

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not any(x in v for x in ("%Y", "%m", "%d")):
            raise ValueError("必须包含年月日格式符")
        return v
# === 请求体模型 ===

class FormatRequest(BaseModel):
    """格式化请求"""

    data: Dict[str, Any]
    config: FormatterConfig = FormatterConfig()

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) > 100:
            raise ValueError("数据量超过100条")
        return v

# === 响应体模型 ===
class FormatResponse(BaseModel):
    """格式化响应"""

    formatted_data: Dict[str, Any]
    log_id: Optional[int] = None
    status: str = "success"

async def set_user_as_admin(target_id: int) -> str:
    """
    将用户设为管理员（Role.ADMIN 或 Role.SUPERADMIN）
    返回操作结果文本，同时记录日志
    """
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == target_id)
            )
            user: User | None = result.scalar_one_or_none()
            if not user:
                logger.warning(f"尝试设管理员失败: 用户 {target_id} 不存在")
                return f"⚠️ 用户 {target_id} 不存在"

            old_role = user.role
            user.role = Role.SUPERADMIN  # 或 Role.ADMIN，根据需求
            await session.commit()
            
            logger.info(f"用户 {target_id} 角色从 {old_role} 更新为 {user.role}")
            return f"✅ 已设用户 {target_id} 为管理员"

    except ValueError as e:
        logger.exception(f"设置用户 {target_id} 为管理员失败: {e}")
        return f"❌ 操作失败，请稍后重试"

# ----------------------------
# 按钮工具
# ----------------------------
def build_set_admin_button(user_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="设置为管理员", callback_data=f"setadmin:{user_id}")]]
    )
    return keyboard


def stock_keyboard():
    buttons = [InlineKeyboardButton(text=str(n), callback_data=f"stock:{n}") for n in [1, 5, 10, 20, 50]]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

