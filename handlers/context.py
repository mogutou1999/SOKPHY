# context.py
from redis.asyncio import Redis
import json
import logging
from typing import cast, List
from config import settings

logger = logging.getLogger(__name__)


class RedisService:
    _redis: Redis | None = None

    @classmethod
    async def get_instance(cls) -> Redis:
        if cls._redis is None:
            cls._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return cls._redis

    @classmethod
    async def get_redis(cls) -> Redis:
        if cls._redis is None:
            cls._redis = Redis(host="localhost", port=6379, db=0)
        return cls._redis
    
    @classmethod
    async def close(cls) -> None:
        if cls._redis:
            await cls._redis.close()
            cls._redis = None

    @classmethod
    async def update_context(
        cls, user_id: int, question: str, answer: str, max_turns: int = 5
    ) -> None:
        """
        更新用户上下文，最多保留 max_turns 条对话
        """
        redis = await cls.get_instance()
        key = f"context:{user_id}"
        value = json.dumps({"question": question, "answer": answer})

        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.rpush(key, value)
                pipe.ltrim(key, -max_turns, -1)
                await pipe.execute()
            logger.debug(f"已更新用户 {user_id} 的上下文，共保留最近 {max_turns} 条")
        except Exception as e:
            logger.error(f"更新用户 {user_id} 上下文失败: {e}")

    @classmethod
    async def get_context(cls, user_id: int) -> List[dict]:
        """
        获取用户上下文列表
        返回格式: [{"question": "...", "answer": "..."}, ...]
        """
        redis = await cls.get_instance()
        key = f"context:{user_id}"

        try:
            items = cast(List[str], await redis.lrange(key, 0, -1)) # type: ignore
            context: list[dict] = [json.loads(item) for item in items] if items else []
            return context
        except Exception as e:
            logger.error(f"获取用户 {user_id} 上下文失败: {e}")
            return []
