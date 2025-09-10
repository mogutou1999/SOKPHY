# handlers/commands.py
from aiogram import Router, F, types

router = Router()

def setup_command_handlers(router: Router) -> None:
    @router.message(F.text == "/help")
    async def help_handler(message: types.Message):
        await message.answer("帮助信息")
