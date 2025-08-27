# handlers/errors.py
from aiogram import Router, types


def setup_error_handlers(router: Router) -> None:
    @router.errors()
    async def handle_all_errors(update, exception: Exception):
        # 统一捕获异常并回复
        try:
            if hasattr(update, "message") and update.message:
                await update.message.answer(f"❌ 出现错误: {exception}")
        except Exception:
            pass
