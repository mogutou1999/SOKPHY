from redis.asyncio import Redis  # 引入 FastAPI 实例
import json
from fastapi import Request
# 不依赖 main.app，直接操作 Redis 实例
redis = Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True  # 确保 get 返回的是 str 而不是 bytes
)

async def cache_get(request: Request, key: str) -> str | None:
    redis: Redis = request.app.state.redis
    return await redis.get(key)

async def cache_set(request: Request, key: str, value: str, expire: int = 3600):
    redis: Redis = request.app.state.redis
    await redis.set(key, value, ex=expire)
