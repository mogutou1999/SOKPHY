# utils/messaging.py

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from typing import List, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


async def send_message_safe(
    bot: Bot,
    user_id: int,
    text: str,
    parse_mode: Optional[str] = None,
    disable_notification: bool = False,
) -> bool:
    """
    给单个用户发消息（异常安全）
    """
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
        )
        logger.info(f"[messaging] 发送成功 user_id={user_id}")
        return True
    except TelegramAPIError as e:
        logger.warning(f"[messaging] 发送失败 user_id={user_id} error={e}")
        return False
    except Exception as e:
        logger.exception(f"[messaging] 未知异常 user_id={user_id} error={e}")
        return False


async def broadcast_message(
    bot: Bot,
    user_ids: List[int],
    text: str,
    parse_mode: Optional[str] = None,
    disable_notification: bool = False,
    chunk_size: int = 30,
) -> int:
    """
    并发广播（按块执行，防速率封禁）
    """
    success = 0

    for i in range(0, len(user_ids), chunk_size):
        chunk = user_ids[i:i + chunk_size]
        tasks = [
            send_message_safe(
                bot,
                user_id=uid,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification
            ) for uid in chunk
        ]
        results = await asyncio.gather(*tasks)
        success += sum(results)
        await asyncio.sleep(0.5)  # 稍微限速

    logger.info(f"[messaging] 广播完成: {success}/{len(user_ids)} 成功")
    return success


async def notify_admins(
    bot: Bot,
    admin_ids: List[int],
    text: str,
    parse_mode: Optional[str] = None,
):
    """
    快速群发给所有管理员
    """
    await broadcast_message(bot, admin_ids, text, parse_mode=parse_mode)


def render_template(template: str, **kwargs) -> str:
    """
    格式化文本模板
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"[messaging] 模板 KeyError: {e}")
        return template
