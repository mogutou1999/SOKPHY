from db.models import Base
from db.session import engine
import asyncio


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(create_tables())
print("数据库表创建完成")
