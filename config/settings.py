# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List
from typing import Optional
import json
import logging
import httpx
import os
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class AppSettings(BaseSettings):
    env: str = Field(default="dev", alias="ENV", description="运行环境(dev/test/prod)")
    redis_url: str = Field(default="redis://localhost:6379")
    vault_enabled: bool = Field(default=False)
    vault_addr: str = Field(default="http://localhost:8200")
    vault_token: str = Field(default="")
    vault_secret_path: str = Field(default="secret/data/myapp")
    payment_api_key: str = Field(default="test-key")
    payment_sandbox: bool = Field(default=True, alias="PAYMENT_SANDBOX")
    database_url: str = Field(
        default="postgresql+asyncpg://YOUR_USER:YOUR_PASS@YOUR_HOST:5432/YOUR_DB"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    bot_token: str = Field(..., alias="BOT_TOKEN")
    payment_api_base: Optional[str] = Field(None, alias="PAYMENT_API_BASE")

    BOT_ADMINS: str = Field(default="", alias="BOT_ADMINS")

    @field_validator("log_level", mode="before")
    def validate_log_level(cls, v):
        v = str(v).upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid log level: {v}")
        return v

    @property
    def admin_ids(self) -> List[int]:
        return [int(x) for x in self.BOT_ADMINS.split(",") if x.strip()]

    model_config = SettingsConfigDict(
        env_file=(f".env.{os.getenv('ENV', 'dev')}", ".env"),
        env_file_encoding="utf-8",
        extra="forbid",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    async def load_redis_config(self) -> None:
        """从 Redis 拉配置"""
        try:
            redis = await Redis.from_url(self.redis_url)
            raw = await redis.get(f"config:{self.env}")
            if not raw:
                logger.warning(f"Redis 未找到配置 config:{self.env}")
                return
            data = json.loads(raw)
            await self.update_from_dict(data)
            logger.info("Redis 配置加载成功")
        except RedisError as e:
            logger.error(f"Redis 异常: {e}")
        except Exception as e:
            logger.exception(f"未知错误: {e}")
        finally:
            if redis:
                await redis.close()

    @classmethod
    async def load_from_vault(
        cls, vault_url: str, vault_token: str, secret_path: str, env: str
    ) -> Optional["AppSettings"]:
        """从 Vault 拉配置，新建实例"""
        try:
            url = f"{vault_url}/v1/{secret_path}"
            headers = {"X-Vault-Token": vault_token}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()["data"]["data"]

            instance = cls(**data)
            if instance.env != env:
                raise ValueError(f"环境不一致: {env} ≠ {instance.env}")
            logger.info("Vault 配置加载成功")
            return instance
        except Exception as e:
            logger.error(f"Vault 拉取失败: {e}")
            return None

    async def update_from_dict(self, data: dict) -> None:
        """更新字段"""
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)

    async def refresh(self) -> None:
        await self.load_redis_config()
        if (
            self.vault_enabled
            and self.vault_addr
            and self.vault_token
            and self.vault_secret_path
        ):
            vault_config = await self.load_from_vault(
                vault_url=self.vault_addr,
                vault_token=self.vault_token,
                secret_path=self.vault_secret_path,
                env=self.env,
            )
            if vault_config:
                await self.update_from_dict(vault_config.model_dump())


settings = AppSettings()
print(settings.payment_api_key)  # "abc123"
print(settings.payment_sandbox)  # False
print(settings.payment_api_base)  # "https://example.com/pay"


def get_app_settings() -> AppSettings:
    return settings
