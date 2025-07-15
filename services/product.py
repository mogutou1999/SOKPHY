import logging
from typing import List, Optional, Dict, Any
from aiogram.filters import Command
from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
import traceback
from typing import Optional
from db.models import Product
from config.settings import settings
from aiogram.types import Message
from aiogram import Router

logger = logging.getLogger(__name__)
logger.error(f"创建商品失败: {traceback.format_exc()}")
ADMIN_IDS = settings.admin_ids or []


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


router = Router()


@router.message(Command("create_product"))
async def handle_create_product(message: Message):
    if not message.from_user:
        await message.answer("⚠️ 用户信息获取失败")
        return
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("🚫 无权限")
        return


async def get_all_products(session: AsyncSession) -> List[Product]:
    try:
        result = await session.execute(select(Product))
        products = list(result.scalars().all())
        return products
    except SQLAlchemyError as e:
        logger.error(f"获取商品列表失败: {e}")
        return []


async def get_product_by_id(
    product_id: int, session: AsyncSession
) -> Optional[Product]:
    try:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        return product
    except SQLAlchemyError as e:
        logger.error(f"查询商品(id={product_id})失败: {e}")
        return None


async def create_product(
    name: str,
    description: Optional[str],
    price: float,
    stock: int,
    session: AsyncSession,
) -> Optional[Product]:
    new_product = Product(
        name=name, description=description, price=price, stock=stock, is_active=True
    )
    try:
        session.add(new_product)
        await session.commit()
        await session.refresh(new_product)
        return new_product
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"创建商品失败: {e}")
        return None


async def update_product(
    product_id: int, update_fields: Dict[str, Any], session: AsyncSession
) -> bool:
    try:
        stmt = (
            update(Product)
            .where(Product.id == product_id)
            .values(**update_fields)
            .returning(Product.id)
        )
        result = await session.execute(stmt)
        updated = result.scalar()
        if not updated:
            return False

        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception(f"更新商品(id={product_id})失败: {e}")
        return False


async def set_product_status(
    product_id: int, is_active: bool, session: AsyncSession
) -> bool:
    return await update_product(product_id, {"is_active": is_active}, session)
