# utils/formatting.py
from datetime import datetime
import logging
from typing import Any, Dict, Optional, Union, List
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from db.models import Product, Order, OrderStatus
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
)


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
        "pending": "⌛ 待支付",
        "paid": "✅ 已支付",
        "shipped": "📦 已发货",
        "refunded": "💸 已退款",
        "cancelled": "❌ 已取消",
    }
    return mapping.get(status.value, f"❓ 未知状态: {status.value}")


def format_product_detail(product: Product) -> str:
    return (
        f"🛍️ <b>{product.name}</b>\n"
        f"💰 价格: ¥{product.price:.2f}\n"
        f"📦 描述: {product.description or '暂无'}\n"
    )


def format_order_detail(order: Order) -> str:
    return (
        f"🧾 <b>订单详情</b>\n"
        f"🆔 ID: {order.id}\n"
        f"👤 用户: {order.user_id}\n"
        f"💵 金额: ¥{order.total_amount:.2f}\n"
        f"📦 状态: {format_order_status(order.status)}\n"
        f"📅 创建时间: {format_datetime(order.created_at)}"
    )


# ===============================
# 📌 5️⃣ 安全回复工具
# ===============================

ReplyMarkup = Union[ReplyKeyboardMarkup, InlineKeyboardMarkup]


async def _safe_reply(
    event: Union[Message, CallbackQuery],
    text: str,
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
    show_alert: bool = False,
) -> None:
    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=reply_markup)
        elif isinstance(event, CallbackQuery):
            msg = getattr(event, "message", None)
            if isinstance(msg, Message) and (
                reply_markup is None or isinstance(reply_markup, InlineKeyboardMarkup)
            ):

                try:
                    await msg.edit_text(text, reply_markup=reply_markup)
                except Exception:
                    await event.answer(text, show_alert=show_alert)
            else:
                # 如果 message 不可访问或者 reply_markup 是 ReplyKeyboardMarkup，用 answer
                await event.answer(text, show_alert=show_alert)
    except Exception:
        logging.exception("❌ _safe_reply 执行失败")


# ===============================
# 📌 6️⃣ 菜单生成工具
# ===============================


async def build_product_menu(products: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in products:
        kb.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{p['name']} ￥{p['price']}",
                    callback_data=f"product_detail:{p['id']}",
                )
            ]
        )
    return kb


async def build_product_detail_kb(product_id: int) -> InlineKeyboardMarkup:
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


async def build_pay_kb(order_id: int) -> InlineKeyboardMarkup:
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

    # === 核心异步格式化器 ===
