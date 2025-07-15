from typing import Union, Optional
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
)
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton

from services.product import get_all_products, get_product_by_id
from utils.formatter import format_product_detail

import logging

ReplyMarkup = Union[ReplyKeyboardMarkup, InlineKeyboardMarkup]

router = Router()
logger = logging.getLogger(__name__)


async def build_product_detail(product_id: int) -> InlineKeyboardMarkup:
    """
    这是一个占位函数，用于生成某个商品的详情按钮。
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="购买", callback_data=f"buy_{product_id}")]
        ]
    )
    return keyboard


def setup_menu_handlers(router: Router) -> None:
    menu_router = Router()

    @menu_router.message(F.text == "/menu")
    async def handle_menu(message: Message) -> None:
        await message.answer("✅ Menu handler: /menu 命令收到。")

    router.include_router(menu_router)


async def build_product_menu(products: list) -> InlineKeyboardMarkup:
    """
    构建商品菜单的示例函数。

    :param products: 商品列表，每个元素是 dict 或模型。
    :return: InlineKeyboardMarkup
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for product in products:
        button = InlineKeyboardButton(
            text=product.get("name", "未命名商品"),
            callback_data=f"product:{product.get('id', 0)}",
        )
        keyboard.inline_keyboard.append([button])

    return keyboard


@router.message(Command("menu"))
@router.callback_query(F.data == "open_menu")
async def show_product_menu(event: Union[Message, CallbackQuery]):
    try:
        products = await get_all_products()
        if not products:
            await _safe_reply(event, "❌ 暂无商品上架")
            return

            markup = await build_product_menu(products)
            await message.answer("xxx", reply_markup=markup)

    except Exception as e:
        logger.exception(f"加载商品菜单失败: {e}")
        await _safe_reply(event, "❌ 商品加载失败，请稍后重试")


@router.callback_query(F.data.startswith("product_detail:"))
async def show_product_detail(callback: CallbackQuery):
    if callback.data is None:
        await callback.answer("数据异常", show_alert=True)
        return

    try:
        product_id = int(callback.data.split(":")[1])
        product = await get_product_by_id(product_id)

        if not product:
            await callback.answer("❌ 商品不存在", show_alert=True)
            return

        text = format_product_detail(product)
        kb = build_product_detail(product)

        await callback.message.edit_text(text, reply_markup=kb)  # type: ignore

    except Exception as e:
        logger.exception(f"商品详情展示失败: {e}")
        await callback.answer("❌ 加载失败，请稍后重试", show_alert=True)


async def _safe_reply(
    event: Union[Message, CallbackQuery],
    text: str,
    reply_markup: Optional[ReplyMarkup] = None,
    show_alert: bool = False,
) -> None:
    if isinstance(event, Message):
        await event.answer(text, reply_markup=reply_markup)
    elif isinstance(event, CallbackQuery):
        if event.message:
            await event.message.answer(text, reply_markup=reply_markup)  # ✅ 这句
        else:
            await event.answer(text, show_alert=show_alert)
