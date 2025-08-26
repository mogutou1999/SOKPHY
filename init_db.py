import asyncio
from db.session import engine
from db.models import Base


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库表已创建")


if __name__ == "__main__":
    asyncio.run(init_models())
