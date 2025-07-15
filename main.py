# main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from handlers.auth import setup_auth_handlers
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties  # ✅ 必须引入这个！
from aiogram.enums import ParseMode  # ✅ 注意这里！
from aiogram.fsm.storage.memory import MemoryStorage
from redis.asyncio import Redis

from config.settings import get_app_settings, settings
from config.loader import periodic_refresh
from services import start, order
from handlers import menu, auth, admin, profile, carts
from services.payment import get_payment_service
from db.session import init_db, async_session_maker
from db.models import User, CartItem
from services.start import router as start_router
from services.order import router as orders_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def try_load_vault_settings(current_settings): ...


@asynccontextmanager
async def lifespan(app: FastAPI):
    # === 1️⃣ 加载本地 env 配置 ===
    settings = get_app_settings()
    print(f"🚀 Running ENV: {settings.env}")

    # === 2️⃣ 尝试从 Vault 补充配置 ===
    await try_load_vault_settings(settings)
    app.state.settings = settings

    # === 3️⃣ Redis 连接 ===
    redis = await Redis.from_url(settings.redis_url)
    app.state.redis = redis

    # === 4️⃣ 定时刷新 ===
    if settings.env in ("dev", "test"):
        asyncio.create_task(periodic_refresh(settings, interval=60))

    # === 5️⃣ 启动 Bot ===
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),  # ✅ 正确的新版写法
    )
    dp = Dispatcher(storage=MemoryStorage())

    # 注册路由
    dp.include_router(profile.router)
    dp.include_router(menu.router)
    dp.include_router(auth.router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(carts.router)
    dp.include_router(order.router)

    app.state.bot = bot
    app.state.dp = dp

    bot_task = asyncio.create_task(dp.start_polling(bot))

    yield  # 👈 必须有

    print("👋 shutdown")
    bot_task.cancel()
    await bot.session.close()
    await redis.close()


# === FastAPI ===
app = FastAPI(lifespan=lifespan)


async def main():
    await init_db()

    async with async_session_maker() as session:
        user = User(username="jinwuye", age=18)
        session.add(user)
        await session.commit()

        item = CartItem(name="My First Item", user_id=user.id)
        session.add(item)
        await session.commit()

        print(f"✅ Added user {user.username} with item {item.product.name}")


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/pay")
async def pay(amount: float = 100.0):
    payment_service = await get_payment_service()
    result = await payment_service.pay(amount)
    return result


if __name__ == "__main__":
    asyncio.run(main())
