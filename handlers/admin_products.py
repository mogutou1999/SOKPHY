# handlers/admin_products.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message,InlineKeyboardMarkup, InlineKeyboardButton

from db.crud import ProductCRUD
from db.session import get_async_session
from utils.formatting import _safe_reply

router = Router()

# --- FSM 定义 ---
class EditProductState(StatesGroup):
    waiting_product_choice = State()
    waiting_field_choice = State()
    waiting_new_value = State()

class DeleteProductState(StatesGroup):
    waiting_product_choice = State()


# --- 修改商品 ---
@router.callback_query(F.data == "admin_edit_product")
async def choose_product_to_edit(call: types.CallbackQuery, state: FSMContext):
    async with get_async_session() as session:
        products = await ProductCRUD.get_all(session)

    if not products:
        return await _safe_reply(call,"⚠️ 没有商品可以修改")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p.name, callback_data=f"edit_product_{p.id}")]
            for p in products
        ]
    )
    await  _safe_reply(call,"请选择要修改的商品：", reply_markup=kb)
    await state.set_state(EditProductState.waiting_product_choice)


@router.callback_query(F.data.startswith("edit_product_"))
async def choose_field(call: types.CallbackQuery, state: FSMContext):
    if not call.data:
        await _safe_reply(call, "发生错误：回调数据为空。")
        return

    try:
        product_id = int(call.data.split("_")[-1])
    except (IndexError, ValueError):
        await _safe_reply(call, "无法解析产品ID。")
        return

    await state.update_data(product_id=product_id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 修改价格", callback_data="edit_field_price")],
            [InlineKeyboardButton(text="📦 修改库存", callback_data="edit_field_stock")],
        ]
    )
    await _safe_reply(call, "请选择要修改的字段：", reply_markup=kb)
    await state.set_state(EditProductState.waiting_field_choice)


@router.callback_query(F.data.startswith("edit_field_"))
async def ask_new_value(call: types.CallbackQuery, state: FSMContext):
    if not call.data:
        await _safe_reply(call, "发生错误：回调数据为空。")
        return
    field = call.data.split("_")[-1]  # price / stock
    await state.update_data(field=field)

    # 安全发送消息给用户
    if call.message:  # ✅ 确保 message 不为 None
        await _safe_reply(call, f"请输入新的 {field}：")
    else:
        await _safe_reply(call,"⚠️ 无法获取消息上下文", show_alert=True)

    # 设置 FSM 状态
    await state.set_state(EditProductState.waiting_new_value)


@router.message(EditProductState.waiting_new_value)
async def save_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product_id = data["product_id"]
    field = data["field"]
    
    new_value = (message.text or "").strip()

    async with get_async_session() as session:
        if field == "price":
            try:
                price = float(new_value)  # ✅ 转换为 float
            except ValueError:
                await _safe_reply(message,"❌ 请输入有效的价格（数字）")
                return
            await ProductCRUD.update_price(session, product_id, price)

        elif field == "stock":
            try:
                stock = int(new_value)
            except ValueError:
                await _safe_reply(message,"❌ 请输入有效的库存数量（整数）")
                return
            await ProductCRUD.update_stock(session, product_id, stock)

    await _safe_reply(message,"✅ 商品修改成功！")
    await state.clear()


# --- 删除商品 ---
@router.callback_query(F.data == "admin_delete_product")
async def choose_product_to_delete(call: types.CallbackQuery, state: FSMContext):
    async with get_async_session() as session:
        products = await ProductCRUD.get_all(session)

    if not products:
        return await _safe_reply(call, "⚠️ 没有商品可以下架")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"❌ {p.name}", callback_data=f"delete_product_{p.id}")]
            for p in products
        ]
    )
    await _safe_reply(call, "请选择要下架的商品：", reply_markup=kb)
    await state.set_state(DeleteProductState.waiting_product_choice)


@router.callback_query(F.data.startswith("delete_product_"))
async def delete_product(call: types.CallbackQuery, state: FSMContext):
    if not call.data:
        await _safe_reply(call, "❌ 无法识别回调数据")
        return

    product_id = int(call.data.split("_")[-1])

    async with get_async_session() as session:
        await ProductCRUD.delete(session, product_id)  # ✅ 确保这个方法存在

    await _safe_reply(call, "✅ 商品已下架")
    await state.clear()
