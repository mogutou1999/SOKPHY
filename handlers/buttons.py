# handlers/buttons.py
from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

router = Router()

@router.message(Command("show_buttons"))
async def show_buttons(msg: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="加入购物车", callback_data="add_to_cart:1"),
                InlineKeyboardButton(text="立即购买", callback_data="buy_now:1")
            ],
            [
                InlineKeyboardButton(text="查看详情", callback_data="view_details:1")
            ]
        ]
    )
    await msg.answer("商品操作按钮示例：", reply_markup=keyboard)
