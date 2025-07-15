# services/cart.py
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.exc import SQLAlchemyError
from db.models import CartItem, Product, User
from decimal import Decimal
from typing import Sequence
logger = logging.getLogger(__name__)

class CartService:
    @staticmethod
    async def get_cart_items(db: AsyncSession, user_id: str) -> Sequence[CartItem]:
        """
        获取用户购物车所有商品项
        """
        try:
            result = await db.execute(
                select(CartItem).where(CartItem.user_id == user_id)
            )
            return result.scalars().all()  # 返回 Sequence[CartItem]
        except SQLAlchemyError as e:
            logger.error(f"获取购物车失败 user_id={user_id}: {e}")
            return []
    @staticmethod
    async def add_item(db: AsyncSession, user_id: str, product_id: str, quantity: int = 1) -> bool:
        """
        向购物车添加商品，若已存在则数量累加
        """
        try:
            result = await db.execute(
                select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
            )
            item = result.scalars().first()
            if item:
                item.quantity += quantity
            else:
                # 先查商品，确保存在且活跃
                product_res = await db.execute(
                    select(Product).where(Product.id == product_id, Product.is_active == True)
                )
                product = product_res.scalars().first()
                if not product:
                    logger.warning(f"添加购物车失败，商品不存在或下架 product_id={product_id}")
                    return False
                item = CartItem(
                    user_id=user_id,
                    product_id=product_id,
                    quantity=quantity
                )
                db.add(item)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"添加购物车失败 user_id={user_id}, product_id={product_id}: {e}")
            return False

    @staticmethod
    async def update_quantity(db: AsyncSession, user_id: str, product_id: str, quantity: int) -> bool:
        """
        更新购物车商品数量，quantity <= 0 则删除该项
        """
        try:
            if quantity <= 0:
                return await CartService.remove_item(db, user_id, product_id)
            stmt = (
                update(CartItem)
                .where(CartItem.user_id == user_id, CartItem.product_id == product_id)
                .values(quantity=quantity)
            )
            await db.execute(stmt)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"更新购物车数量失败 user_id={user_id}, product_id={product_id}: {e}")
            return False

    @staticmethod
    async def remove_item(db: AsyncSession, user_id: str, product_id: str) -> bool:
        """
        从购物车删除商品项
        """
        try:
            stmt = delete(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
            await db.execute(stmt)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"删除购物车商品失败 user_id={user_id}, product_id={product_id}: {e}")
            return False

    @staticmethod
    async def clear_cart(db: AsyncSession, user_id: str) -> bool:
        """
        清空用户购物车
        """
        try:
            stmt = delete(CartItem).where(CartItem.user_id == user_id)
            await db.execute(stmt)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"清空购物车失败 user_id={user_id}: {e}")
            return False