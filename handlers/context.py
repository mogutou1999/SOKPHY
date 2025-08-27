from redis.asyncio import Redis
from typing import List
import logging

from config import settings

REDIS_URL = "redis://localhost:6379"
MAX_CONTEXT_TURNS = 5

logger = logging.getLogger(__name__)


class RedisService:
    _redis = None

    @classmethod
    async def get_instance(cls) -> Redis:
        if cls._redis is None:
            cls._redis = await Redis.from_url(settings.redis_url, decode_responses=True)
        return cls._redis

    @classmethod
    async def close(cls):
        if cls._redis:
            await cls._redis.close()
            cls._redis = None

    @classmethod
    async def update_context(cls, user_id: int, question: str, answer: str, max_turns: int = 5):
        """更新对话上下文"""
        redis = await cls.get_instance()
        key = f"context:{user_id}"
        value = f"User: {question}\nAI: {answer}"
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.rpush(key, value)      # 添加新记录
                pipe.ltrim(key, -max_turns, -1)  # 保留最后 max_turns 条
                await pipe.execute()
            logger.debug(f"已更新用户 {user_id} 的上下文")
        except Exception as e:
            logger.error(f"更新用户 {user_id} 上下文失败: {e}")

    @classmethod
    async def get_context(cls, user_id: int) -> str:
        """获取对话上下文"""
        redis = await cls.get_instance()
        key = f"context:{user_id}"
        try:
            items = await redis.lrange(key, 0, -1)   # type: ignore
            return "\n".join(items) if items else ""
        except Exception as e:
            logger.error(f"获取用户 {user_id} 上下文失败: {e}")
            return ""
