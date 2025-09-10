# handlers/admin_products.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message,InlineKeyboardMarkup, InlineKeyboardButton,CallbackQuery
from typing import cast,Sequence
from db.crud import ProductCRUD
from db.session import get_async_session
from utils.formatting import _safe_reply
import logging
from db.models import Product
from sqlalchemy import select
from config.settings import settings
from decimal import Decimal
from aiogram.filters import Command
from services.products import create_product_db

logger = logging.getLogger(__name__)
router = Router()

class AddProductState(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_stock = State()   
    waiting_description = State()
    waiting_image = State()
    
# --- FSM 定义 ---
class EditProductState(StatesGroup):
    waiting_product_choice = State()
    waiting_field_choice = State()
    waiting_new_value = State()

class DeleteProductState(StatesGroup):
    waiting_product_choice = State()


# 库存查看（回调）
@router.callback_query(F.data == "admin_inventory")
async def handle_inventory_view(call: CallbackQuery):
    if call.message is None:
        await call.answer("⚠️ 消息不存在", show_alert=True)
        return
    async with get_async_session() as session:
        res = await session.execute(select(Product).where(Product.is_active == True))
        products: Sequence[Product] = res.scalars().all()
    if not products:
        await call.answer("📭 当前库存为空")
        return
    lines = [f"📦 <b>{p.name}</b>\n库存: {p.stock} | 价格: ¥{p.price:.2f}\n" for p in products]
    await _safe_reply(call, "\n".join(lines))


# --- 新增：FSM 流程 ---
@router.callback_query(F.data == "admin_add_product")
async def start_add_product(call: CallbackQuery, state: FSMContext):
    await _safe_reply(call, "请输入商品名称：")
    await state.set_state(AddProductState.waiting_name)


@router.message(AddProductState.waiting_name)
async def product_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        return await _safe_reply(message, "❌ 商品名称不能为空")
    await state.update_data(name=name)
    await _safe_reply(message, "请输入商品价格（例如 9.99）：")
    await state.set_state(AddProductState.waiting_price)


@router.message(AddProductState.waiting_price)
async def product_price(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        price = Decimal(text)
    except Exception:
        return await _safe_reply(message, "❌ 价格格式错误，请输入数字（如 9.99）")
    await state.update_data(price=str(price))
    await _safe_reply(message, "请输入库存（整数）：")
    await state.set_state(AddProductState.waiting_stock)


@router.message(AddProductState.waiting_stock)
async def product_stock(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        stock = int(text)
    except Exception:
        return await _safe_reply(message, "❌ 库存必须为整数")
    await state.update_data(stock=stock)
    await _safe_reply(message, "请输入描述（可选，发送 /skip 跳过）：")
    await state.set_state(AddProductState.waiting_description)


@router.message(AddProductState.waiting_description)
async def product_desc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "/skip":
        await state.update_data(description="")
    else:
        await state.update_data(description=text)
    await _safe_reply(message, "请发送商品图片（可选，发送 /skip 跳过）：")
    await state.set_state(AddProductState.waiting_image)


@router.message(AddProductState.waiting_image, F.text == "/skip")
async def skip_image(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name") or "未知商品"
    price = Decimal(data.get("price") or "0")
    stock = int(data.get("stock") or 0)
    description = data.get("description") or ""
    async with get_async_session() as session:
        product = await create_product_db(session=session, name=name, price=price, stock=stock, description=description, image_file_id=None)
    await _safe_reply(message, f"✅ 商品已添加：{product.name} ¥{product.price} 库存:{product.stock}")
    await state.clear()


@router.message(AddProductState.waiting_image, F.photo)
async def receive_image(message: Message, state: FSMContext):
    if not message.photo:
        return await _safe_reply(message, "❌ 未检测到图片，请重试或发送 /skip 跳过")
    photo = message.photo[-1]
    data = await state.get_data()
    name = data.get("name") or "未知商品"
    price = Decimal(data.get("price") or "0")
    stock = int(data.get("stock") or 0)
    description = data.get("description") or ""
    async with get_async_session() as session:
        product = await create_product_db(session=session, name=name, price=price, stock=stock, description=description, image_file_id=photo.file_id)
    await _safe_reply(message, f"✅ 商品已添加（含图片）：{product.name} ¥{product.price} 库存:{product.stock}")
    await state.clear()


# --- 编辑商品（通过 ProductCRUD） ---
@router.callback_query(F.data == "admin_edit_product")
async def list_products_for_edit(call: CallbackQuery, state: FSMContext):
    async with get_async_session() as session:
        products = await ProductCRUD.get_all(session)
    if not products:
        return await _safe_reply(call, "⚠️ 没有商品可以修改")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p.name, callback_data=f"edit_product:{p.id}")] for p in products
    ])
    await _safe_reply(call, "请选择要修改的商品：", reply_markup=kb)
    await state.set_state(EditProductState.waiting_product_choice)


@router.callback_query(F.data.startswith("edit_product:"))
async def choose_field(call: CallbackQuery, state: FSMContext):
    parts = (call.data or "").split(":", 1)
    if len(parts) != 2:
        return await _safe_reply(call, "❌ 数据错误")
    product_id = parts[1]
    await state.update_data(product_id=product_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 修改价格", callback_data="edit_field:price")],
        [InlineKeyboardButton(text="📦 修改库存", callback_data="edit_field:stock")]
    ])
    await _safe_reply(call, "请选择要修改的字段：", reply_markup=kb)
    await state.set_state(EditProductState.waiting_field_choice)


@router.callback_query(F.data.startswith("edit_field:"))
async def ask_new_value(call: CallbackQuery, state: FSMContext):
    parts = (call.data or "").split(":", 1)
    if len(parts) != 2:
        return await _safe_reply(call, "❌ 数据错误")
    field = parts[1]
    await state.update_data(field=field)
    await _safe_reply(call, f"请输入新的 {field}：")
    await state.set_state(EditProductState.waiting_new_value)


@router.message(EditProductState.waiting_new_value)
async def save_new_value(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    field = data.get("field")
    if not product_id or not field:
        return await _safe_reply(message, "❌ 状态丢失，请重新开始")
    new_text = (message.text or "").strip()
    async with get_async_session() as session:
        if field == "price":
            try:
                new_price = float(new_text)
            except Exception:
                return await _safe_reply(message, "❌ 价格格式错误")
            await ProductCRUD.update_price(session, product_id, new_price)
        else:  # stock
            try:
                new_stock = int(new_text)
            except Exception:
                return await _safe_reply(message, "❌ 库存必须为整数")
            await ProductCRUD.update_stock(session, product_id, new_stock)
    await _safe_reply(message, "✅ 修改成功")
    await state.clear()


# --- 下架 / 删除 ---
@router.callback_query(F.data == "admin_delete_product")
async def list_products_for_delete(call: CallbackQuery, state: FSMContext):
    async with get_async_session() as session:
        products = await ProductCRUD.get_all(session)
    if not products:
        return await _safe_reply(call, "⚠️ 没有商品可以下架")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {p.name}", callback_data=f"delete_product:{p.id}")] for p in products
    ])
    await _safe_reply(call, "请选择要下架的商品：", reply_markup=kb)
    await state.set_state(DeleteProductState.waiting_product_choice)


@router.callback_query(F.data.startswith("delete_product:"))
async def delete_product(call: CallbackQuery, state: FSMContext):
    parts = (call.data or "").split(":", 1)
    if len(parts) != 2:
        return await _safe_reply(call, "❌ 数据错误")
    product_id = int(parts[1])
    async with get_async_session() as session:
        await ProductCRUD.delete(session, product_id)
    await _safe_reply(call, "✅ 商品已下架")
    await state.clear()
