import os
import asyncio
import logging
from io import BytesIO
import aiohttp
import qrcode
from qrcode.constants import ERROR_CORRECT_L
from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from dotenv import load_dotenv

from config.settings import get_app_settings, settings
from db.session import get_async_session

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.env != "prod" else logging.INFO)

router = Router()

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ 未设置 BOT_TOKEN，请检查 .env 文件")


# ──────────────────────────────
# ✅ 支付服务类
# ──────────────────────────────


class PaymentService:
    def __init__(self, api_key: str, sandbox: bool = True):
        self.api_key = api_key
        self.sandbox = sandbox

    async def pay(self, amount: float) -> dict:
        logger.info(f"💰 Paying ${amount} using API key: {self.api_key[:4]}...")
        await self.simulate_gateway_call(amount)
        return {"status": "success", "amount": amount}

    async def simulate_gateway_call(self, amount: float):
        await asyncio.sleep(1)
        logger.info(f"✅ 已完成第三方支付: ${amount}")

    async def create_payment(self, amount: float, currency: str = "USD") -> dict:
        logger.info(f"Creating payment: amount={amount}, currency={currency}")
        if self.sandbox:
            logger.info("Sandbox mode: Skipping real API call.")
            return {"status": "success", "sandbox": True, "amount": amount}
        else:
            logger.info("Calling real payment API...")
            return {"status": "success", "sandbox": False, "amount": amount}

    async def verify_payment(self, payment_id: str) -> dict:
        logger.info(f"Verifying payment_id={payment_id}")
        return {"status": "verified", "payment_id": payment_id}


# ──────────────────────────────
# ✅ 工厂函数，生产 PaymentService
# ──────────────────────────────


async def get_payment_service() -> PaymentService:
    # ❗️ 如果 get_app_settings() 是同步的，就别 await
    settings_obj = get_app_settings()
    return PaymentService(api_key=settings_obj.payment_api_key, sandbox=True)


# ──────────────────────────────
# ✅ 生成二维码（同步 + 异步封装）
# ──────────────────────────────


def _generate_qr_sync(payment_url: str) -> BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(payment_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def generate_payment_qr(payment_url: str) -> BytesIO:
    return await asyncio.to_thread(_generate_qr_sync, payment_url)


# ──────────────────────────────
# ✅ 调用后端拿支付链接
# ──────────────────────────────


async def get_payment_link(order_id: int) -> str:
    api_url = f"{settings.payment_api_base}/{order_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"获取支付链接失败: 状态 {resp.status}")
            data = await resp.json()
            return data.get("payment_url", f"https://example.com/payment/{order_id}")


# ──────────────────────────────
# ✅ 流程封装：处理支付请求
# ──────────────────────────────


async def handle_payment_request(order_id: int):
    link = await get_payment_link(order_id)
    if not link:
        raise ValueError("支付链接为空")
    qr_img = await generate_payment_qr(link)
    return link, qr_img


# ──────────────────────────────
# ✅ Aiogram 命令处理
# ──────────────────────────────


@router.message(Command("generate_qr"))
async def handle_generate_payment_qr(message: Message):
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("❌ 用法错误：/generate_qr <支付链接>")
        return

    payment_url = parts[1]
    try:
        qr_image = await generate_payment_qr(payment_url)
        photo = BufferedInputFile(qr_image.getvalue(), filename="qrcode.png")
        await message.answer_photo(photo=photo, caption="✅ 请扫码完成支付")
    except Exception:
        logger.exception("生成二维码失败")
        await message.answer("❌ 无法生成二维码")


# ──────────────────────────────
# ✅ 本地测试入口
# ──────────────────────────────

if __name__ == "__main__":

    async def test():
        oid = 123
        logger.info("开始测试支付流程，订单ID=%s", oid)
        link, qr = await handle_payment_request(oid)
        logger.info("支付链接: %s", link)
        with open("test_qr.png", "wb") as f:
            f.write(qr.read())
        logger.info("二维码已保存到 test_qr.png")

    asyncio.run(test())
