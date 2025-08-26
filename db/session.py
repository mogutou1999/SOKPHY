# db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from typing import AsyncGenerator
from sqlalchemy import text
from contextlib import asynccontextmanager
from config.settings import AppSettings, settings
import logging
from db.base import Base

DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(DATABASE_URL, echo=True)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

logger = logging.getLogger(__name__)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 提供异步数据库会话（依赖注入、事务管理推荐用法）


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """提供 async with 的安全会话"""
    async with async_session_maker() as session:  # 正确调用实例
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


# 关闭连接池（建议在 shutdown 时调用）
async def close_connections():
    await engine.dispose()
    logger.info("🔌 数据库连接池已关闭")
