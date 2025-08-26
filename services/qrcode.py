import io
import logging
from typing import Optional, Union
import qrcode
from aiogram.types import BufferedInputFile
from aiogram import Bot
from aiogram.types import InputFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradientColorMask
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.pil import PilImage
print(PilImage)
logger = logging.getLogger(__name__)


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
        style: str = "rounded"
    ) -> QRCodeResponse:
        """
        生成高级 QR 码
        """
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)

            # 样式
            img_factory = {
                "rounded": StyledPilImage,
                "square": None,
                "gradient": StyledPilImage
            }.get(style)

            color_mask = RadialGradientColorMask() if style == "gradient" else None
            drawer = RoundedModuleDrawer() if style == "rounded" else None

            img = qr.make_image(
                fill_color=fill_color,
                back_color=back_color,
                image_factory=img_factory,
                module_drawer=drawer,
                color_mask=color_mask
            )

            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            # 这里假设有 QRCodeLog 模型
            # log = QRCodeLog(
            #     data=data[:500],
            #     size=size,
            #     style=style
            # )
            # self.db.add(log)
            # await self.db.commit()

            return QRCodeResponse(
                qr_id=None,  # 如果你有 DB 主键，写 log.id
                image_bytes=img_bytes.getvalue(),
                status="success"
            )

        except Exception as e:
            # await self.db.rollback()
            logger.error(f"生成 QR 失败: {e}")
            return QRCodeResponse(status=f"error: {str(e)}")

    async def send_telegram_qr(
        self,
        chat_id: Union[int, str],
        qr_data: str,
        caption: Optional[str] = None
    ) -> QRCodeResponse:
        """
        生成并发送 QR
        """
        qr_result = await self.generate_qr(qr_data)
        if qr_result.status != "success":
            return qr_result

        buf = io.BytesIO(qr_result.image_bytes or b"")
        photo = BufferedInputFile(buf.getvalue(), filename="qr.png")

        await self.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption or "Here is your QR code"
        )

        return qr_result
