# handlers/errors.py
import logging
from aiogram import Router, types
logger = logging.getLogger(__name__)
router = Router()

def setup_error_handlers(router: Router) -> None:
    @router.errors()
    async def handle_all_errors(update: types.Update, exception: Exception):
        # 统一捕获异常并回复
        try:
            if hasattr(update, "message") and update.message:
                await update.message.answer(f"❌ 出现错误: {exception}")
        except Exception as e:
            logger.exception(f"错误处理器发送失败: {e}")
