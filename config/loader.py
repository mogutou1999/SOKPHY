# config/loader.py
import asyncio
import logging
from typing import Optional
from .settings import AppSettings

logger = logging.getLogger(__name__)

# 单例
_settings: Optional[AppSettings] = None

async def get_app_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings()
        await _settings.refresh()
    return _settings

async def try_load_vault_settings() -> AppSettings:
    """
    如果 Vault 配置可用，就尝试拉取最新配置，成功则更新单例，否则返回原配置
    """
    global _settings

    current = await get_app_settings()

    vault_ready = all([
        current.vault_enabled,
        current.vault_addr,
        current.vault_token,
        current.vault_secret_path
    ])

    if not vault_ready:
        logger.info("ℹ️ Vault 条件不满足，跳过加载")
        return current

    try:
        new_settings = await AppSettings.load_from_vault(
            vault_url=current.vault_addr,
            vault_token=current.vault_token,
            secret_path=current.vault_secret_path,
            env=current.env
        )
        if new_settings:
            _settings = new_settings
            logger.info("✅ Vault 配置加载成功并已更新全局设置")
            return new_settings
        else:
            logger.warning("⚠️ Vault 返回空配置，使用原配置")
    except Exception as e:
        logger.exception(f"❌ Vault 配置加载异常: {e}")

    return current
async def periodic_refresh(settings: AppSettings, interval: int = 60):
    while True:
        try:
            await settings.refresh()
            logger.info("🔁 配置刷新完成")
        except Exception as e:
            logger.exception(f"刷新配置失败: {e}")
        await asyncio.sleep(interval)