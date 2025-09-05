# services/cart.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,insert, update, delete
from sqlalchemy.exc import SQLAlchemyError
from db.models import CartItem, Product
from typing import List
from decimal import Decimal
from uuid import UUID
from utils.formatting import _safe_reply
logger = logging.getLogger(__name__)


class CartService:
    @staticmethod
    async def add_product_to_cart(
        db: AsyncSession, user_id: UUID, product_id: UUID, quantity: int
    ) -> dict:
        # 1. 检查商品是否存在
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            return {"success": False, "message": "商品不存在"}

        if product.stock < quantity:
            return {"success": False, "message": "库存不足"}

        # 2. 检查购物车里是否已有该商品
        result = await db.execute(
            select(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.product_id == product_id,
            )
        )
        cart_item = result.scalar_one_or_none()

        if cart_item:
            # 已存在则更新数量
            await db.execute(
                update(CartItem)
                .where(CartItem.id == cart_item.id)
                .values(quantity=cart_item.quantity + quantity)
            )
        else:
            # 不存在则插入新纪录
            await db.execute(
                insert(CartItem).values(
                    user_id=user_id,
                    product_id=product_id,
                    quantity=quantity,
                )
            )

        await db.commit()
        return {"success": True, "message": "商品已加入购物车"}
    @staticmethod
    async def remove_item(db: AsyncSession, user_id: UUID, product_id: UUID) -> bool:
        """删除购物车指定商品"""
        try:
            stmt = delete(CartItem).where(
                CartItem.user_id == user_id, CartItem.product_id == product_id
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(
                f"删除购物车商品失败 user_id={user_id}, product_id={product_id}: {e}"
            )
            return False

    @staticmethod
    async def get_cart_items(db: AsyncSession, user_id: UUID) -> List[CartItem]:
        """获取用户购物车所有商品"""
        result = await db.execute(select(CartItem).where(CartItem.user_id == user_id))
        return list(result.scalars().all())

    @staticmethod
    async def calculate_cart_total(db: AsyncSession, user_id: UUID) -> float:
        """计算购物车总金额"""
        items = await CartService.get_cart_items(db, user_id)
        total: Decimal = sum(
            (Decimal(item.quantity) * Decimal(item.unit_price) for item in items),
            Decimal(0),
        )
        return float(total)

    @staticmethod
    async def update_quantity(
        db: AsyncSession, user_id: UUID, product_id: UUID, quantity: int
    ) -> bool:
        """更新购物车商品数量，<=0 则删除"""
        try:
            if quantity <= 0:
                return await CartService.remove_item(db, user_id, product_id)

            stmt = (
                update(CartItem)
                .where(CartItem.user_id == user_id, CartItem.product_id == product_id)
                .values(quantity=quantity)
                .execution_options(synchronize_session="fetch")
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"更新购物车数量失败: {e}")
            return False

    @staticmethod
    async def clear_cart(db: AsyncSession, user_id: UUID) -> bool:
        """清空购物车"""
        try:
            stmt = delete(CartItem).where(CartItem.user_id == user_id)
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"清空购物车失败: {e}")
            return False
