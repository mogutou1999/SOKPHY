# app.py
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import get_app_settings, AppSettings
from config.loader import periodic_refresh
from db.session import init_db, get_async_session,engine
from db.crud import UserCRUD, ProductCRUD, OrderCRUD, CartCRUD
from services.payment import get_payment_service
from handlers import setup_all_handlers
from handlers.context import RedisService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# -----------------------------
# Vault / Settings
# -----------------------------

# -----------------------------
# FastAPI Lifespan
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 加载配置
    settings: AppSettings = get_app_settings()
    await settings.refresh()
    app.state.settings = settings
    print(f"🚀 Running ENV: {settings.env}")

    # 2. Redis
    redis = await RedisService.get_redis()
    app.state.redis = redis

    # 3. 初始化数据库
    await init_db()

    # 4. 定时刷新（仅 dev/test）
    if settings.env in ("dev", "test"):
        asyncio.create_task(periodic_refresh(settings, interval=60))

    # 5. Bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # 注册 handlers
    setup_all_handlers(dp) 

    app.state.bot = bot
    app.state.dp = dp

    bot_task = asyncio.create_task(dp.start_polling(bot))

    yield

    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    await RedisService.close()
    await engine.dispose()
    logger.info("应用已安全关闭 ✅")

# -----------------------------
# FastAPI 应用
# -----------------------------
app = FastAPI(
    title="Shop Bot API",
    description="Bot + API 二合一",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置（生产建议改成域名白名单）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# API 路由
# -----------------------------
@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/cart/add")
async def add_to_cart(
    user_id: str,
    product_id: int,
    quantity: int,
    product_name: str,
    unit_price: float,
    session: AsyncSession = Depends(get_async_session),
):
    cart_item = await CartCRUD.add_item(
        session=session,
        user_id=user_id,
        product_id=product_id,
        quantity=quantity,
        product_name=product_name,
        unit_price=unit_price,
    )
    return {
        "message": "已加入购物车",
        "cart_item_id": cart_item.id,
        "product_name": cart_item.product_name,
        "quantity": cart_item.quantity,
        "unit_price": cart_item.unit_price,
    }


@app.get("/users/{telegram_id}")
async def get_user(
    telegram_id: int, session: AsyncSession = Depends(get_async_session)
):
    user = await UserCRUD.get_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.username,
    }


@app.post("/products")
async def create_product(
    name: str,
    price: Decimal,
    stock: int = 0,
    description: str = "",
    session: AsyncSession = Depends(get_async_session),
):
    product = await ProductCRUD.create(
        session, name=name, price=price, stock=stock, description=description
    )
    return {
        "id": product.id,
        "name": product.name,
        "price": str(product.price),
        "stock": product.stock,
        "description": product.description,
    }


@app.get("/products")
async def list_products(session: AsyncSession = Depends(get_async_session)):
    products = await ProductCRUD.list_active(session)
    return [
        {"id": p.id, "name": p.name, "price": str(p.price), "stock": p.stock}
        for p in products
    ]

@app.get("/orders/{user_id}")
async def list_orders(user_id: int, session: AsyncSession = Depends(get_async_session)):
    orders = await OrderCRUD.list_by_user(session, user_id=user_id)
    return [
        {"id": o.id, "status": o.status, "total_amount": str(o.total_amount)}
        for o in orders
    ]


@app.get("/pay")
async def pay(total_amount: float = 100.0):
    payment_service = await get_payment_service()
    result = await payment_service.pay(total_amount)
    return result


# -----------------------------
# 启动入口
# -----------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
