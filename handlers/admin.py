# admin.py
import logging
import bcrypt
from functools import wraps
from typing import cast,Optional, Sequence
from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,InaccessibleMessage
from aiogram.filters import Command
from config.settings import settings
from db.session import get_async_session
from db.models import User, Role,Product,Config 
from sqlalchemy import select, update
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from utils.formatting import _safe_reply
from db.crud import ProductCRUD
from aiogram.fsm.context import FSMContext
from services.user_service import db_get_user
from decimal import Decimal



router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = settings.admin_ids



class AddProductState(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_stock = State()   
    waiting_description = State()
    waiting_image = State()
    
    

@router.message(AddProductState.waiting_name)
async def product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await _safe_reply(message,"请输入商品价格（数字）：")
    await state.set_state(AddProductState.waiting_price)

@router.message(AddProductState.waiting_price)
async def product_price(message: Message, state: FSMContext):
    
    price_str = message.text
    if price_str is None:
        await _safe_reply(message, "❌ 商品价格未填写")
        return
    try:
        price = float(price_str)
    except ValueError:
        await _safe_reply(message,"请输入正确数字")
        return
    await state.update_data(price=price)
    await _safe_reply(message,"请输入库存数量：")
    await state.set_state(AddProductState.waiting_stock)

@router.message(AddProductState.waiting_stock)
async def product_stock(message: Message, state: FSMContext):
    if not message.text:
        await _safe_reply(message,"请输入库存数量（必须是整数）")
        return
    try:
        stock = int(message.text)
        await state.update_data(stock=stock)

        await _safe_reply(message, "请发送商品图片（可选，输入 /skip 跳过）：")
        await state.set_state(AddProductState.waiting_image)

    except ValueError:
        await _safe_reply(message, "❌ 无效输入，请输入库存数量（必须是整数）")

@router.message(AddProductState.waiting_description)
async def product_description(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("❌ 请输入有效文字或发送 /skip 跳过")
        return

    text = message.text.strip()
    if text == "/skip":
        await state.update_data(description=None)
    else:
        await state.update_data(description=text)
    
    await _safe_reply(message, "请发送商品图片（可选，输入 /skip 跳过）：")
    await state.set_state(AddProductState.waiting_image)


@router.message(AddProductState.waiting_image, F.text == "/skip")
async def skip_image(message: Message, state: FSMContext):
    data = await state.get_data()
    async with get_async_session() as session:
        await ProductCRUD.create(
            session=session,
            name=data["name"],
            price=Decimal(data["price"]),
            stock=int(data["stock"]),
            image_file_id=None,
            description=data.get("description")
        )
        await session.commit()
    await _safe_reply(message, "✅ 商品添加成功（无图）")
    await state.clear()

@router.message(AddProductState.waiting_image, F.photo)
async def product_image(message: Message, state: FSMContext):
    data = await state.get_data()
    image_file_id = message.photo[-1].file_id if message.photo else None
    # 保存到数据库
    async with get_async_session() as session:
        product = await ProductCRUD.create(
            session=session,               # ✅ 这里必须传 session
            name=data["name"],
            price=Decimal(data["price"]),  # 如果 Product.price 是 Decimal
            stock=int(data["stock"]),
            image_file_id=image_file_id,
            description=data.get("description")
        )
        await session.commit()

    await _safe_reply(message,"✅ 商品添加成功！")
    await state.clear()

@router.message(AddProductState.waiting_image, F.photo)
async def receive_image(message: Message, state: FSMContext):
    if not message.photo:
        await _safe_reply(message, "❌ 未检测到图片，请重新发送或输入 /skip 跳过。")
        return
    photo = message.photo[-1]  # 取最大尺寸
    await state.update_data(image_file_id=photo.file_id)

    data = await state.get_data()

    async with get_async_session() as session:
        await ProductCRUD.create(
            session=session,
            name=data["name"],
            price=Decimal(data["price"]),
            stock=int(data["stock"]),
            image_file_id=data["image_file_id"],
            description=data.get("description")
        )
        await session.commit() 

    await _safe_reply(message, "✅ 商品添加成功（含图片）")
    await state.clear()    
    
# -----------------------------
# 权限校验
# -----------------------------
def require_role(required_roles):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not message.from_user:
                await _safe_reply(message,"⚠️ 用户信息获取失败")
                return

            async with get_async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == message.from_user.id)
                )
                user = result.scalar_one_or_none()

                if not user or user.role not in required_roles:
                    await _safe_reply(message,
                        f"🚫 权限不足，需角色: {', '.join(r.name if hasattr(r, 'name') else str(r) for r in required_roles)}"
                    )

                    return

            return await handler(message, *args, **kwargs)

        return wrapper

    return decorator

def stock_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(n), callback_data=f"stock:{n}")
        for n in [1, 5, 10, 20, 50]
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])



def require_superadmin(handler):
    return require_role([Role.SUPERADMIN])(handler)


def is_admin(user: User | None) -> bool:
    if not user:
        return False
    return user.role in (Role.ADMIN, Role.SUPERADMIN)

def require_admin(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if not message.from_user:
            await _safe_reply(message, "⚠️ 用户信息获取失败")
            return

        user_id = message.from_user.id
        user = await db_get_user(user_id)
        if not is_admin(user):
            await _safe_reply(message, "❌ 你没有权限")
            return await _safe_reply(message, "🚫 无权限")
        return await handler(message, *args, **kwargs)
    return wrapper

async def is_superadmin(user_id: int) -> bool:
    async with get_async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user: Optional[User] = result.scalar_one_or_none()
        return bool(user and user.role == Role.SUPERADMIN)



def require_roles(required_roles):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not message.from_user:
                return await _safe_reply(message, "⚠️ 用户信息获取失败")
            async with get_async_session() as session:
                result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
                user: User | None = result.scalar_one_or_none()
                if not user or user.role not in required_roles:
                    return await _safe_reply(message, f"🚫 权限不足，需角色: {', '.join([r.name for r in required_roles])}")
            return await handler(message, *args, **kwargs)
        return wrapper
    return decorator
# -----------------------------
# 通用异常处理装饰器
# -----------------------------
def handle_errors(handler):
    @wraps(handler)
    async def wrapper(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except Exception as e:
            logger.exception("Handler error")
            event = kwargs.get('message') or args[0]
            await _safe_reply(event, "❌ 出错了，请稍后重试")
    return wrapper
  
# 管理员面板入口
@router.message(Command("admin"))
@handle_errors
async def admin_panel(msg: Message):
    text = "👮 欢迎进入管理员面板\n\n可用命令：\n/ban <用户ID> - 封禁用户\n/unban <用户ID> - 解封用户\n/setadmin <用户ID> <角色> - 设置管理员"
    await _safe_reply(msg, text)  

# 封禁 / 解封用户
# -----------------------------
@router.message(F.text.startswith("/ban"))
@handle_errors
async def ban_user(message: Message):
    if not message.text:
        return await _safe_reply(message,"❌ 请提供参数：/setadmin <用户ID> <角色>")
    
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await _safe_reply(message, "❌ 格式：/ban <用户ID>")

    target_id = int(parts[1])
    async with get_async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user: Optional[User] = result.scalar_one_or_none()
        if not user:
            return await _safe_reply(message, "⚠️ 用户不存在")
        user.is_blocked = True
        await session.commit()
    await _safe_reply(message, f"✅ 用户 {target_id} 已被封禁")  

@router.message(F.text == "/admin")
async def admin_menu(message: types.Message, state: FSMContext):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ 你没有权限访问此菜单。")
        return

    user = await db_get_user(user_id)
    if not is_admin(user):
        await _safe_reply(message, "❌ 你没有权限")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ 新增商品", callback_data="admin_add_product")],
            [InlineKeyboardButton(text="📝 修改商品", callback_data="admin_edit_product")],
            [InlineKeyboardButton(text="❌ 下架商品", callback_data="admin_delete_product")],
        ]
    )
    
    await message.answer("欢迎进入管理员后台菜单：", reply_markup=kb)

# 文本 "admin" 触发时调用核心菜单
@router.message(F.text.lower() == "admin")
async def handle_admin_text(message: Message, state: FSMContext):
    await admin_menu(message, state)

@router.callback_query(F.data == "admin_add_product")
async def start_add_product(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("❌ 你没有权限执行此操作。", show_alert=True)
        return
    
    logger.info("✅ 收到 admin_add_product 回调")
    
    await _safe_reply(call.message, "请输入商品名称：") # type: ignore
    await state.set_state(AddProductState.waiting_name)

  
@router.message(F.text == "下一步")
async def handle_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(step_done=True)
  
@router.message(F.text.startswith("/unban"))
@require_admin
async def unban_user(message: Message):
    if not message.text or len(message.text.strip().split()) != 2:
        return await _safe_reply(message,"❌ 格式：/unban <用户ID>")
    
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await _safe_reply(message,"❌ 格式：/unban <用户ID>")
    target_id = int(parts[1])
    async with get_async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return await _safe_reply(message,"⚠️ 用户不存在")
        user.is_blocked = False
        await session.commit()
    await _safe_reply(message,f"✅ 已解封 {target_id}")

@router.message(F.text.startswith("/setadmin"))
@require_admin
async def set_admin(message: Message):
            # 校验参数
    if not message.text:
        return await _safe_reply(message,"❌ 请提供参数：/setadmin <用户ID> <角色>")
    
    parts = message.text.strip().split()
    if len(parts) != 3:
        return await _safe_reply(message,"❌ 格式错误：/setadmin <用户ID> <角色>")
      
    target_id_str, role_str = parts[1], parts[2].upper()
    if not target_id_str.isdigit():
        return await _safe_reply(message,"❌ 用户ID必须为数字")
    if role_str not in ["ADMIN", "SUPERADMIN"]:
        return await _safe_reply(message,"❌ 角色必须是 ADMIN 或 SUPERADMIN")

    target_id = int(target_id_str)
    async with get_async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user: Optional[User] = result.scalar_one_or_none()
        if not user:
            return await _safe_reply(message, "⚠️ 用户不存在")
        user.role = Role[role_str]
        await session.commit()
    await _safe_reply(message, f"✅ 用户 {target_id} 已设为 {role_str}")

@router.message(F.text.startswith("/resetpw"))
@require_admin
async def reset_password(message: Message):
    if not message.text:
        return await _safe_reply(message, "❌ 请提供参数：/resetpw <用户ID> <新密码>")
    
    parts = message.text.strip().split()
    if len(parts) != 3:
        return await _safe_reply(message, "❌ 格式：/resetpw <用户ID> <新密码>")

    if not message.from_user:
        return await _safe_reply(message, "⚠️ 无法获取用户信息")
    
    target_id = int(parts[1])
    new_password = parts[2]
    hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

    async with get_async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user: Optional[User] = result.scalar_one_or_none()
        if not user:
            return await _safe_reply(message, "⚠️ 用户不存在")
        user.password = hashed_password
        await session.commit()
    await _safe_reply(message, f"🔑 用户 {target_id} 密码已重置") 

@router.message(F.text.startswith("/userinfo"))
@require_admin
async def user_info(message: Message):
    if not message.from_user:
        await _safe_reply(message,"⚠️ 用户信息获取失败")
        return

    if not message.text:
        await _safe_reply(message,"⚠️ 指令格式不正确")
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await _safe_reply(message,"❌ 格式应为：/userinfo <用户ID>")
        return

    user_id = int(parts[1])

    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await _safe_reply(message,"⚠️ 用户不存在")
                return

            text = (
                f"👤 <b>用户信息</b>\n"
                f"ID: {user.telegram_id}\n"
                f"用户名: @{user.username or '无'}\n"
                f"姓名: {getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}\n"
                f"语言: {getattr(user, 'language', '未设置')}\n"
                f"手机号: {getattr(user, 'phone', '未绑定')}\n"
                f"邮箱: {getattr(user, 'email', '未绑定')}\n"
                f"注册时间: {user.created_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(user, 'created_at', None) else '未知'}\n"
                f"状态: {'✅ 正常' if not user.is_blocked else '🚫 已封禁'}"
            )

            await _safe_reply(message,text)

    except Exception as e:
        logger.error(f"查询用户信息失败: {e}")
        await _safe_reply(message,"❌ 查询失败，请稍后重试") 

@router.message(Command("setconfig"))
@require_superadmin
@handle_errors
async def set_config(message: Message):
    if not message.text:
        return await _safe_reply(message, "❌ 格式应为：/setconfig <key> <value>")

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) != 3:
        return await _safe_reply(message, "❌ 格式应为：/setconfig <key> <value>")
    key, value = parts[1], parts[2]

    async with get_async_session() as session:
        result = await session.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()
        if config:
            config.value = value
        else:
            config = Config(key=key, value=value)
            session.add(config)
        await session.commit()
        await _safe_reply(message, f"✅ 已设置配置 {key} = {value}")

@router.message(Command("getconfig"))
@require_admin
@handle_errors
async def get_config(message: Message):
    if not message.text:
        return await _safe_reply(message, "❌ 格式应为：/setconfig <key> <value>")

    parts = message.text.strip().split()
    if len(parts) != 2:
        return await _safe_reply(message, "❌ 格式应为：/getconfig <key>")

    key = parts[1]
    async with get_async_session() as session:
        result = await session.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()
        if not config:
            return await _safe_reply(message, f"⚠️ 配置 {key} 不存在")
        await _safe_reply(message, f"📌 {config.key} = {config.value}")

@router.message(Command("listconfig"))
@require_admin
@handle_errors
async def list_config(message: Message):
    async with get_async_session() as session:
        result = await session.execute(select(Config))
        configs = result.scalars().all()
        if not configs:
            return await _safe_reply(message, "📭 当前没有配置")
        text = "\n".join([f"{c.key} = {c.value}" for c in configs])
        await _safe_reply(message, f"📋 配置列表:\n{text}")

# ----------------------------
# 商品管理
# ----------------------------
@router.message(Command("create_product"))
@require_admin
@handle_errors
async def create_product(message: Message):
    if not message.text:
        return await _safe_reply(message, "❌ 格式应为：/getconfig <key>")

    args = message.text.strip().split()[1:]
    if len(args) < 3:
        return await _safe_reply(message, "❌ 格式错误: /create_product 名称 价格 库存")

    name = args[0]
    try:
        price = float(args[1])
        stock = int(args[2])
    except ValueError:
        return await _safe_reply(message, "⚠️ 价格必须是数字，库存必须是整数")

    description = "默认描述"
    async with get_async_session() as session:
        product = Product(name=name, price=price, stock=stock, description=description)
        session.add(product)
        await session.commit()
        await _safe_reply(message, f"✅ 商品已创建: {name} - {price} 元 - 库存 {stock}")

@router.message(F.text.startswith("/shutdown"))
@require_admin
@handle_errors
async def shutdown_system(message: Message):
    if not message.from_user:
        await _safe_reply(message,"⚠️ 用户信息获取失败")
        return

    async with get_async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        
        if not user or not await is_superadmin(user.telegram_id):
            await _safe_reply(message, "🚫 只有超级管理员可以执行此操作")
            return

        await _safe_reply(message,"💥 系统关机指令已执行（示例）")



# -----------------------------
# 查看商品列表（管理员）
# -----------------------------
@router.message(Command("admin_products"))
@require_admin
@handle_errors
async def admin_show_products(message: Message):
    async with get_async_session() as session:
        result = await session.execute(select(Product).where(Product.is_active == True))
        products: Sequence[Product] = result.scalars().all()

    if not products:
        return await _safe_reply(message, "📭 当前没有上架商品")

    for p in products:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛒 加入购物车", callback_data=f"addcart:{p.id}")],
                [InlineKeyboardButton(text=f"💳 立即购买 {p.price} 元", callback_data=f"buy:{p.id}")],
                [InlineKeyboardButton(text="✏️ 修改", callback_data=f"edit_product:{p.id}"),
                 InlineKeyboardButton(text="❌ 下架", callback_data=f"delete_product:{p.id}")]
            ]
        )

        caption = (
            f"📦 {p.name}\n"
            f"💰 {p.price} 元\n"
            f"库存: {p.stock}\n"
            f"{p.description or ''}"
        )

        if getattr(p, "image_url", None):
            await _safe_reply(message, caption, reply_markup=kb)
        else:
            await _safe_reply(message, caption, reply_markup=kb)

@router.callback_query(F.data.startswith("delete_product:"))
@require_admin
async def handle_delete_product(call: CallbackQuery):
    # 确保消息存在并可访问
    if not call.message or isinstance(call.message, InaccessibleMessage):
        await _safe_reply(call,"⚠️ 无法访问消息", show_alert=True)
        return

    assert call.data is not None  # 告诉 Pylance 这个不会是 None
    product_id = int(call.data.split(":")[1])

    async with get_async_session() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product: Optional[Product] = result.scalar_one_or_none()
        if not product:
            await _safe_reply(call,"❌ 商品不存在", show_alert=True)
            return
        product.is_active = False
        await session.commit()

    await call.message.edit_text(f"✅ 商品《{product.name}》已下架")
        
# -----------------------------
# 查看用户信息或列表
# -----------------------------
@router.message(F.text.startswith("/user"))
@require_admin
async def list_or_show_user(message: Message):
    if not message.text:
        return await _safe_reply(message, "❌ 格式应为：/getconfig <key>")

    parts = message.text.strip().split()
    per_page = getattr(settings, "items_per_page", 5)
    async with get_async_session() as session:
        if len(parts) == 2 and parts[1].isdigit():
            # 查询单用户
            user_id = int(parts[1])
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user: Optional[User] = result.scalar_one_or_none()
            if not user:
                return await _safe_reply(message, "⚠️ 用户不存在")
            text = (
                f"👤 用户信息\n"
                f"ID: {user.telegram_id}\n"
                f"用户名: @{user.username or '无'}\n"
                f"状态: {'✅ 正常' if not user.is_blocked else '🚫 封禁'}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="设置为管理员", callback_data=f"setadmin:{user_id}")]
            ])
            await _safe_reply(message, text, reply_markup=keyboard)
            return

        # 分页查询列表
        page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
        total_users = await session.scalar(select(func.count()).select_from(User)) or 0
        max_page = (total_users + per_page - 1) // per_page
        if page > max_page: page = max_page
        offset = (page - 1) * per_page
        result = await session.execute(select(User).offset(offset).limit(per_page))
        users: Sequence[User] = result.scalars().all()
        if not users:
            return await _safe_reply(message, f"📭 没有用户 (第 {page} 页)")
        text = "\n".join([f"ID:{u.telegram_id} 用户名:@{u.username or '无'} 状态:{'🚫封禁' if u.is_blocked else '✅正常'}" for u in users])
        await _safe_reply(message, f"👥 用户列表 (第 {page} 页):\n{text}")
         
