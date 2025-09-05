# db/session.py

from sqlalchemy.exc import SQLAlchemyError
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from config.settings import AppSettings, settings,get_app_settings
import logging
import asyncio
from db.base import Base

logger = logging.getLogger(__name__)
settings = get_app_settings()

DATABASE_URL = "postgresql+asyncpg://wuye:mypassword@localhost:5432/sokphy"

engine = create_async_engine(DATABASE_URL, echo=True)

# 创建 sessionmaker
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ 数据库表已创建/检查完成")

# 异步上下文管理器
@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


# 健康检查（可用于 /ping 或启动检测）
async def health_check() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ 数据库连接正常")
        return True
    except SQLAlchemyError as e:
        logger.critical(f"❌ 数据库健康检查失败: {e}")
        return False



async def close_connections():
    await engine.dispose()
    logger.info("🔌 数据库连接池已关闭")

    

if __name__ == "__main__":
    asyncio.run(health_check())
