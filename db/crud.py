# db/crud.py
from typing import Optional, List, Sequence
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from .models import User, Product, CartItem, Order, OrderItem, OrderStatus, Role
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Executable
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)


class BaseCRUD:
    """CRUD 基类，提供公共方法"""

    @classmethod
    async def _execute_commit(
        cls, session: AsyncSession, stmt: Executable, error_msg: str
    ) -> bool:
        """
        安全执行并提交，兼容 rowcount 可能为 None 的情况。
        """
        try:
            result = await session.execute(stmt)
            await session.commit()
            rowcount = getattr(result, "rowcount", None)
            if rowcount is None:
                logger.warning(f"{error_msg}：无法获取 rowcount，已忽略")
                return True  # 默认成功，或者你可以返回 False
            return rowcount > 0
        except SQLAlchemyError as e:
            logger.error(f"{error_msg}: {e}", exc_info=True)
            await session.rollback()
            return False


class UserCRUD(BaseCRUD):
    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession, telegram_id: int
    ) -> Optional[User]:
        result = await session.execute(
            select(User)
            .where(User.telegram_id == telegram_id)
            .options(selectinload(User.cart_items))
        )
        return result.scalars().first()

    @staticmethod
    async def create_user(
        session: AsyncSession, telegram_id: int, username: str, role: Role = Role.USER
    ) -> User:
        try:
            user = User(
                telegram_id=telegram_id,
                username=username,
                role=role,
                last_active=func.now(),
            )
            session.add(user)
            await session.commit()
            await session.flush()  # 保证 INSERT 发出去
            await session.refresh(user)  # 拿到生成的 ID
            return user
        except SQLAlchemyError as e:
            logger.error(f"创建用户失败: {e}", exc_info=True)
            await session.rollback()
            raise

    @staticmethod
    async def update_last_active(session: AsyncSession, user_id: str) -> bool:
        return await UserCRUD._execute_commit(
            session,
            update(User).where(User.id == user_id).values(last_active=func.now()),
            "更新活跃时间失败",
        )


class ProductCRUD(BaseCRUD):
    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        result = await session.execute(
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.order_items))
        )
        return result.scalars().first()

    @staticmethod
    async def list_active(session: AsyncSession) -> Sequence[Product]:
        stmt = select(Product).where(Product.is_active == True)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str,
        price: Decimal,
        stock: int = 0,
        description: str = "",
    ) -> Product:
        product = Product(name=name, price=price, stock=stock, description=description)
        session.add(product)
        await session.flush()
        await session.refresh(product)
        return product


class CartCRUD(BaseCRUD):
    @staticmethod
    async def merge_cart_items(
        session: AsyncSession, user_id: str, items: List[dict]
    ) -> bool:
        try:
            async with session.begin():
                await session.execute(
                    delete(CartItem).where(CartItem.user_id == user_id)
                )
                if items:
                    session.add_all(
                        [
                            CartItem(
                                user_id=user_id,
                                product_id=item["product_id"],
                                quantity=item["quantity"],
                                unit_price=Decimal(str(item["unit_price"])),
                                product_name=item["product_name"],
                            )
                            for item in items
                        ]
                    )
            return True
        except SQLAlchemyError as e:
            logger.error(f"合并购物车失败: {e}", exc_info=True)
            return False

    @staticmethod
    async def clear_cart(
        session: AsyncSession,
        user_id: str,
    ) -> bool:
        """
        清空购物车
        """
        try:
            stmt = delete(CartItem).where(CartItem.user_id == user_id)
            await session.execute(stmt)
            await session.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"清空购物车失败: {e}")
            await session.rollback()
            return False

    @staticmethod
    async def add_item(
        session: AsyncSession,
        user_id: str,
        product_id: int,
        quantity: int,
        product_name: str,
        unit_price: float,
    ) -> CartItem:
        """
        加入购物车：如果有相同商品，数量叠加；否则新增，并保存 name 和 price。
        """
        try:
            stmt = select(CartItem).where(
                CartItem.user_id == user_id, CartItem.product_id == product_id
            )
            result = await session.execute(stmt)
            cart_item = result.scalars().first()
            if cart_item:
                cart_item.quantity += quantity
            else:
                cart_item = CartItem(
                    user_id=user_id,
                    product_id=product_id,
                    quantity=quantity,
                    product_name=product_name,
                    unit_price=unit_price,
                )
                session.add(cart_item)

            await session.commit()
            await session.refresh(cart_item)
            return cart_item

        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"加入购物车失败: {e}")
            raise RuntimeError(f"添加购物车失败: {e}") from e

    @staticmethod
    async def update_quantity(
        session: AsyncSession, cart_item_id: str, quantity: int
    ) -> bool:
        """
        更新某个购物车项的商品数量。
        常用于前端点击“+”或“-”按钮直接设置数量。
        """
        try:
            result = await session.execute(
                update(CartItem)
                .where(CartItem.id == cart_item_id)
                .values(quantity=quantity)
                .execution_options(synchronize_session="fetch")
            )
            await session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"更新购物车数量失败: {e}", exc_info=True)
            return False

    @staticmethod
    async def remove_item(
        session: AsyncSession,
        user_id: str,
        product_id: str,
    ) -> bool:
        """
        删除用户购物车中某个指定商品。
        通常用于前端提供“删除该商品”按钮。
        """
        try:
            stmt = delete(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.product_id == product_id,
            )
            await session.execute(stmt)
            await session.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除购物车商品失败: {e}", exc_info=True)
            await session.rollback()
            return False


class OrderCRUD(BaseCRUD):
    @staticmethod
    async def create_with_items(
        session: AsyncSession,
        user_id: str,
        items: List[dict],
        status: OrderStatus = OrderStatus.PENDING,
        **kwargs,
    ) -> Optional[Order]:
        try:
            async with session.begin():
                total = sum(
                    Decimal(str(item["unit_price"])) * item["quantity"]
                    for item in items
                )
                order = Order(
                    user_id=user_id, total_amount=total, status=status, **kwargs
                )
                session.add(order)
                await session.flush()
                session.add_all(
                    [
                        OrderItem(
                            order_id=order.id,
                            product_id=item["product_id"],
                            quantity=item["quantity"],
                            unit_price=Decimal(str(item["unit_price"])),
                        )
                        for item in items
                    ]
                )
                return order
        except SQLAlchemyError as e:
            logger.error(f"创建订单失败: {e}", exc_info=True)
            await session.rollback()
            return None

    @staticmethod
    async def mark_paid(session: AsyncSession, order_id: int) -> bool:
        return await OrderCRUD._execute_commit(
            session,
            update(Order)
            .where(Order.id == order_id)
            .values(status=OrderStatus.PAID.value, is_paid=True),
            "订单标记支付失败",
        )

    @staticmethod
    async def get_with_items(session: AsyncSession, order_id: str) -> Optional[Order]:
        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.user))
        )
        return result.scalars().first()

    @staticmethod
    async def get_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(session: AsyncSession, user_id: int) -> List[Order]:
        result = await session.execute(select(Order).where(Order.user_id == user_id))
        return list(result.scalars().all())

    @staticmethod
    async def update_status(
        session: AsyncSession, order_id: int, status: OrderStatus
    ) -> bool:
        result = await session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status=status.value)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_by_user_id(session: AsyncSession, user_id: int) -> List[Order]:
        stmt = select(Order).where(Order.user_id == user_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete(session: AsyncSession, order_id: str) -> bool:
        result = await session.execute(
            delete(Order)
            .where(Order.id == order_id)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def list_by_status(
        session: AsyncSession, status: OrderStatus, limit: int = 100
    ) -> List[Order]:
        """按状态筛选订单"""
        result = await session.execute(
            select(Order)
            .where(Order.status == status)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .options(selectinload(Order.user))
        )
        return list(result.scalars().all())
