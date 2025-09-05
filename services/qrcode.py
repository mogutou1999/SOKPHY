# services/qr.py
import io
import logging
from typing import Optional, Union, Tuple
import qrcode
from aiogram.types import BufferedInputFile
from aiogram import Bot
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.pil import PilImage
from qrcode.image.styles.colormasks import SolidFillColorMask

logger = logging.getLogger(__name__)

# 类型别名
ColorType = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]

# ====== Pydantic 响应体 ======
class QRCodeResponse(BaseModel):
    qr_id: Optional[int] = None
    image_bytes: Optional[bytes] = None
    status: str

# ====== QRCodeService ======
class QRCodeService:
    def __init__(self, db: AsyncSession, bot: Bot):
        self.db = db
        self.bot = bot

    async def generate_qr(
        self,
        data: str,
        size: int = 300,
        fill_color: str = "black",
        back_color: str = "white",
        style: str = "rounded",
    ) -> QRCodeResponse:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=ERROR_CORRECT_H,
                box_size=10,
                border=4,
                image_factory=PilImage,  # ✅ 强制使用 PIL 工厂，避免 PyPNGImage
            )
            qr.add_data(data)
            qr.make(fit=True)

            # 样式控制
            img_factory = {
                "rounded": StyledPilImage,
                "square": PilImage,
                "gradient": StyledPilImage,
            }.get(style, PilImage)

            drawer = RoundedModuleDrawer() if style == "rounded" else None

            if style == "gradient":
                color_mask = SolidFillColorMask(
                    front_color=(0, 0, 0),
                    back_color=(255, 255, 255),
                )
                img = qr.make_image(
                    image_factory=img_factory,
                    module_drawer=drawer,
                    color_mask=color_mask,
                )
            else:
                img = qr.make_image(
                    image_factory=img_factory,
                    module_drawer=drawer,
                    fill_color=fill_color,
                    back_color=back_color,
                )

            # ✅ 确保拿到 PIL.Image
            pil_img = img.get_image() if hasattr(img, "get_image") else img

            # ✅ 这里 resize 就不会再报错
            pil_img = pil_img.resize((size, size))

            output = io.BytesIO()
            pil_img.save(output, format="PNG")
            output.seek(0)

            return QRCodeResponse(
                qr_id=None,
                image_bytes=output.getvalue(),
                status="success",
            )

        except ValueError as e:
            logger.error(f"生成QR失败: {e}", exc_info=True)
            return QRCodeResponse(status=f"error: {str(e)}")
        
    async def send_telegram_qr(
        self, chat_id: Union[int, str], qr_data: str, caption: Optional[str] = None
    ) -> QRCodeResponse:
        """发送QR到Telegram (类型安全版本)"""
        qr_result = await self.generate_qr(qr_data)
        if qr_result.status != "success" or not qr_result.image_bytes:
            return QRCodeResponse(status="生成二维码失败")

        try:
            await self.bot.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(file=qr_result.image_bytes, filename="qr.png"),
                caption=caption or "您的二维码",
            )
            return qr_result
        except ValueError as e:
            logger.error(f"发送QR失败: {e}", exc_info=True)
            return QRCodeResponse(status=f"send_error: {str(e)}")

