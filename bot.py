import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

# 设置日志
logging.basicConfig(level=logging.INFO)

API_TOKEN ="7893903290:AAEbZ0tFJBpXF-sOv8uPDhiORgTnZEg3pwo" 

# 初始化 Bot 和 Dispatcher
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher()


# /start 命令处理器
@dp.message(Command("start"))
async def cmd_start(message: Message):
    print(f"message.text: {message.text}")
    print(f"message.text 类型: {type(message.text)}")

    await message.answer("✅ Hello! Your bot is working!")


# 回声处理器（非命令消息）
@dp.message()
async def echo(message: Message):
    await message.answer(message.text)


# 主函数（用于启动 polling）
async def main():
    logging.info("🚀 Bot 正在启动...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())