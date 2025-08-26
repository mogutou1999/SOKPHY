# services/cart.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.exc import SQLAlchemyError
from db.models import CartItem, Product
from typing import List
from decimal import Decimal

logger = logging.getLogger(__name__)


class CartService:
    @staticmethod
    async def add_product_to_cart(
        db: AsyncSession, user_id: int, product_id: int, quantity: int
    ) -> str:
        product = await db.get(Product, product_id)
        if not product or not product.is_active:
            return "❌ 商品不存在或已下架"

        if product.stock < quantity:
            return f"❌ 库存不足，目前仅剩 {product.stock} 件"

        result = await db.execute(
            select(CartItem).where(
                CartItem.user_id == user_id, CartItem.product_id == product_id
            )
        )
        cart_item = result.scalar_one_or_none()

        if cart_item:
            cart_item.quantity += quantity
        else:
            cart_item = CartItem(
                user_id=user_id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=float(product.price),
            )
            db.add(cart_item)

        try:
            await db.commit()
            await db.refresh(cart_item)
            return f"✅ 已加入购物车: {product.name} × {quantity}"
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"添加购物车失败: {e}")
            return "❌ 加入购物车失败"

    @staticmethod
    async def remove_product_from_cart(
        db: AsyncSession, user_id: int, product_id: int
    ) -> bool:
        try:
            stmt = delete(CartItem).where(
                CartItem.user_id == user_id, CartItem.product_id == product_id
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"删除购物车商品失败: {e}")
            return False

    @staticmethod
    async def get_cart_items(db: AsyncSession, user_id: int) -> List[CartItem]:
        result = await db.execute(select(CartItem).where(CartItem.user_id == user_id))
        return list(result.scalars().all())

    @staticmethod
    async def calculate_cart_total(db: AsyncSession, user_id: int) -> float:
        items = await CartService.get_cart_items(db, user_id)
        total: Decimal = sum(
            (Decimal(item.quantity) * Decimal(item.unit_price) for item in items),
            Decimal(0),
        )
        return float(total)

    @staticmethod
    async def update_quantity(
        db: AsyncSession, user_id: int, product_id: int, quantity: int
    ) -> bool:
        """更新购物车数量，<=0 则删除"""
        try:
            if quantity <= 0:
                return await CartService.remove_product_from_cart(
                    db, user_id, product_id
                )

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
    async def clear_cart(db: AsyncSession, user_id: int) -> bool:
        try:
            stmt = delete(CartItem).where(CartItem.user_id == user_id)
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"清空购物车失败: {e}")
            return False

    @staticmethod
    async def remove_item(db: AsyncSession, user_id: int, product_id: int) -> bool:
        """从购物车删除指定商品项"""
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
