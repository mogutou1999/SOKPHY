# handlers/buttons.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram import Router, types, F
from utils.formatting import _safe_reply
router = Router()

@router.message(Command("show_buttons"))
async def show_buttons(msg: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="加入购物车", callback_data="add_to_cart:1"),
            InlineKeyboardButton(text="立即购买", callback_data="buy_now:1")
        ],
        [
            InlineKeyboardButton(text="查看详情", callback_data="view_details:1")
        ]
    ])
    await _safe_reply(msg, "商品操作按钮示例：", reply_markup=keyboard)
    
@router.callback_query(F.data.startswith("add_to_cart:"))
async def add_to_cart_handler(callback: types.CallbackQuery):
    if not callback.data:
        return
    product_id = callback.data.split(":")[1]
    await _safe_reply(callback, f"✅ 商品 {product_id} 已加入购物车", show_alert=True)

@router.callback_query(F.data.startswith("buy_now:"))
async def handle_buy_now(callback: types.CallbackQuery):
    if not callback.data:
        return
    product_id = int(callback.data.split(":")[1])
    await _safe_reply(callback, f"💳 正在购买商品 {product_id}", show_alert=True)

@router.callback_query(F.data.startswith("view_details:"))
async def handle_view_details(callback: types.CallbackQuery):
    if not callback.data:
        return
    product_id = int(callback.data.split(":")[1])
    await _safe_reply(callback, f"📦 商品 {product_id} 详情如下：\n...\n（这里显示商品描述）")
    
    await callback.answer() 
