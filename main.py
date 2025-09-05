# main.py
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from config.settings import get_app_settings, AppSettings
from config.loader import periodic_refresh
from db.session import  engine,init_models
from handlers import setup_all_handlers
from handlers.context import RedisService
from api import router as api_router  # API 路由
import uvicorn
from fastapi.staticfiles import StaticFiles


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_app_settings()

COMMANDS_I18N = {
    "en": [
        {"command": "start", "description": "Start the bot"},
        {"command": "menu", "description": "View product list"},
        {"command": "myorders", "description": "View my orders"},
        {"command": "profile", "description": "View profile info"},
    ],
    "zh": [
        {"command": "start", "description": "启动机器人"},
        {"command": "menu", "description": "查看商品列表"},
        {"command": "myorders", "description": "查看我的订单"},
        {"command": "profile", "description": "查看个人信息"},
    ],
}

def get_bot_commands(lang_code: str = "zh") -> list[BotCommand]:
    cmds = COMMANDS_I18N.get(lang_code, COMMANDS_I18N["zh"])
    return [BotCommand(command=c["command"], description=c["description"]) for c in cmds]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 配置
    settings: AppSettings = get_app_settings()
    await settings.refresh()
    app.state.settings = settings
    logger.info(f"🚀 Running ENV: {settings.env}")

    # 2. Redis
    app.state.redis = await RedisService.get_redis()
    logger.info("✅ Redis 初始化完成")
    # 3. 初始化数据库
    await init_models()
    logger.info("✅ 数据库初始化完成")
    # 4. 定时刷新
    if settings.env in ("dev", "test"):
        asyncio.create_task(periodic_refresh(settings, interval=60))

    # 5. 启动 Bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    setup_all_handlers(dp)
    
     # 设置命令
    commands = get_bot_commands(settings.default_lang)
    await bot.set_my_commands(commands)
    logger.info(f"✅ Bot 命令已设置: {settings.default_lang}")

    app.state.bot = bot
    app.state.dp = dp

    polling_task = asyncio.create_task(dp.start_polling(bot))
    logger.info("✅ Telegram Bot 已启动轮询")

    yield  # lifespan 上下文开始，FastAPI 正常运行

    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    await RedisService.close()
    await engine.dispose()
    logger.info("🛑 系统已关闭")

app = FastAPI(
    title="My FastAPI E-commerce Bot",
    description="Bot + API 二合一",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://shop-frontend-5p36.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_router, prefix="/api", tags=["Core"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
