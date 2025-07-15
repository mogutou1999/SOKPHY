# utils/formatting.py

from datetime import datetime

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from db.models import Product, Order


# === 工具函数 ===


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


def format_order_status(status: str) -> str:
    mapping = {
        "PENDING": "⌛ 待支付",
        "PAID": "✅ 已支付",
        "SHIPPED": "📦 已发货",
        "REFUNDED": "💸 已退款",
    }
    return mapping.get(status, f"❓ 未知状态: {status}")


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


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
