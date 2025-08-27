# handlers/commands.py
from aiogram import Router, F, types


def setup_command_handlers(router: Router) -> None:
    @router.message(F.text == "/start")
    async def start_handler(message: types.Message):
        await message.answer("欢迎使用！")

    @router.message(F.text == "/help")
    async def help_handler(message: types.Message):
        await message.answer("帮助信息")
