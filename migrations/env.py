from logging.config import fileConfig
import asyncio
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import create_async_engine
from config.settings import get_app_settings
from db.models import Base
from alembic import context
from sqlalchemy.engine import Connection

# -----------------------------
# 配置 Alembic logging
# -----------------------------
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -----------------------------
# 读取项目配置
# -----------------------------
settings = get_app_settings()
DATABASE_URL = "postgresql+asyncpg://wuye:@localhost:5432/wuye"
# -----------------------------
# 绑定 MetaData
# -----------------------------
target_metadata = Base.metadata

# -----------------------------
# 异步 Engine
# -----------------------------
def get_async_engine():
    return create_async_engine(DATABASE_URL, poolclass=pool.NullPool, future=True)

# -----------------------------
# 同步运行迁移（offline）
# -----------------------------
def run_migrations_offline():
    url = DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

# -----------------------------
# 异步迁移（online）
# -----------------------------
async def run_migrations_online():
    connectable = create_async_engine(DATABASE_URL, future=True)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def do_run_migrations(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

# -----------------------------
# 入口
# -----------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())