# handlers/payment.py
import asyncio
import logging
from io import BytesIO
import qrcode
from db.session import get_async_session
from db.models import Order, OrderStatus 
from sqlalchemy import select
from qrcode.constants import ERROR_CORRECT_L
from aiogram import Router,Bot, types
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from config.settings import settings
import stripe


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.env != "prod" else logging.INFO)

router = Router()
bot = Bot(token=settings.bot_token)

# Stripe SDK 全局初始化
stripe.api_key = settings.stripe_api_key


class PaymentService:
    def __init__(self, sandbox: bool = True):
        self.sandbox = sandbox

    async def pay(self, total_amount: float) -> dict:
        logger.info(f"💰 Paying ${total_amount} (sandbox={self.sandbox})")
        await asyncio.sleep(1)
        return {"status": "success", "total_amount": total_amount}

    async def create_stripe_checkout_session(self, amount: int, user_id: int) -> str:
        """生成 Stripe Checkout 链接"""
        if self.sandbox:
            logger.info("Sandbox 模式，返回模拟支付链接")
            return f"https://sandbox.example.com/payment/{user_id}"

        # 调用 Stripe SDK 创建 session
        stripe_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': settings.currency,
                    'product_data': {'name': f"订单 #{user_id}"},
                    'unit_amount': amount,  # 美分
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url="https://你的域名/success",
            cancel_url="https://你的域名/cancel",
        )
        if not stripe_session.url:
            raise ValueError("Stripe session URL 不可为 None")
        assert stripe_session.id is not None, "Stripe session id 不可为 None"
        return stripe_session.url  # ✅ 正确引用

    @staticmethod
    def create_payment(order_id: str, amount: float) -> str:
        return "https://example.com/pay"

    @staticmethod
    def verify_callback(data: dict) -> bool:
        # 这里用支付宝或 Stripe 验签逻辑
        return True
    


    
@router.message(lambda m: m.text == "/pay")
async def pay_command(message: types.Message):
    qr_url = PaymentService.create_payment("test123", 9.99)
    await message.answer(f"请扫码支付：\n{qr_url}")

@router.message(lambda m: m.text.startswith("/callback"))
async def callback_demo(message: types.Message):
    data = {"out_no": "test123", "amount": 9.99, "sign": "abc"}
    out_no = data["out_no"]
    success = PaymentService.verify_callback(data)

    await message.answer("✅ 支付成功" if success else "❌ 支付验证失败")

    # 更新订单状态
    async with get_async_session() as session:
        async with session.begin():
            stmt = select(Order).where(Order.out_no == out_no)
            result = await session.execute(stmt)
            order = result.scalar_one_or_none()
            if order and order.status != "paid":              
                order.status = OrderStatus.PAID 
                # 通知用户
                await bot.send_message(
                    chat_id=order.user.telegram_id,
                    text=f"✅ 您的订单 {out_no} 已支付成功！"
                )

    return "success"

# ──────────────────────────────
# ✅ 工厂函数
# ──────────────────────────────
async def get_payment_service(sandbox: bool = False) -> PaymentService:
    return PaymentService(sandbox=sandbox)

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
    img.save(buf)
    buf.seek(0)
    return buf

async def generate_payment_qr(payment_url: str) -> BytesIO:
    return await asyncio.to_thread(_generate_qr_sync, payment_url)

# ──────────────────────────────
# ✅ 流程封装：处理支付请求
# ──────────────────────────────
async def handle_payment_request(user_id: int, amount: int) -> tuple[str, BytesIO]:
    service = PaymentService(sandbox=False)
    link = await service.create_stripe_checkout_session(amount, user_id)
    qr_img = await generate_payment_qr(link)
    return link, qr_img

# ──────────────────────────────
# ✅ Aiogram 命令处理
# ──────────────────────────────
@router.message(Command("generate_qr"))
async def handle_generate_payment_qr(message: Message):
    if not message.from_user or message.from_user.id is None:
        await message.answer("❌ 无法获取用户信息")
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("❌ 用法错误：/generate_qr <金额（美分）>")
        return

    try:
        amount = int(parts[1])
        link, qr_image = await handle_payment_request(message.from_user.id, amount)
        photo = BufferedInputFile(qr_image.getvalue(), filename="qrcode.png")
        await message.answer_photo(photo=photo, caption=f"✅ 请扫码完成支付\n{link}")
    except Exception:
        logger.exception("生成二维码失败")
        await message.answer("❌ 无法生成二维码")

# ──────────────────────────────
# ✅ 本地测试
# ──────────────────────────────
if __name__ == "__main__":
    async def test():
        user_id = 123
        amount = 100  # 美分
        logger.info("开始测试支付流程，用户ID=%s", user_id)
        link, qr = await handle_payment_request(user_id, amount)
        logger.info("支付链接: %s", link)
        with open("test_qr.png", "wb") as f:
            f.write(qr.read())
        logger.info("二维码已保存到 test_qr.png")

    asyncio.run(test())
