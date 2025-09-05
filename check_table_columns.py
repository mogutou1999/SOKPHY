import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import inspect

DATABASE_URL = "postgresql+asyncpg://wuye:mypassword@localhost:5432/wuye"

engine = create_async_engine(DATABASE_URL, echo=True)

async def check_columns():
    async with engine.connect() as conn:
        # run_sync 包裹整个 inspect + get_columns
        columns = await conn.run_sync(lambda sync_conn: [
            {
                "name": col["name"],
                "type": col["type"],
                "default": col.get("default"),
                "nullable": col.get("nullable", True)
            }
            for col in inspect(sync_conn).get_columns("products")
        ])
        
        print("Products 表列：")
        for col in columns:
            print(f'{col["name"]} ({col["type"]}), default={col["default"]}, nullable={col["nullable"]}')

asyncio.run(check_columns())
