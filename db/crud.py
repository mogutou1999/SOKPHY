# db/crud.py
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from db.models import User, Product, CartItem, Order, OrderItem
from db.roles import Role


class UserCRUD:
    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession, telegram_id: int
    ) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalars().first()

    @staticmethod
    async def create_user(
        session: AsyncSession, telegram_id: int, username: str, role: Role = Role.USER
    ) -> User:
        user = User(telegram_id=telegram_id, username=username, role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def update_username(
        session: AsyncSession, user_id: str, new_username: str
    ) -> bool:
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(username=new_username)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0


class ProductCRUD:
    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: str) -> Optional[Product]:
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalars().first()

    @staticmethod
    async def list_active(session: AsyncSession) -> List[Product]:
        result = await session.execute(select(Product).where(Product.is_active == True))
        return list(result.scalars().all())

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
        await session.commit()
        await session.refresh(product)
        return product


class CartCRUD:
    @staticmethod
    async def get_cart_items(session: AsyncSession, user_id: str) -> List[CartItem]:
        result = await session.execute(
            select(CartItem).where(CartItem.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def clear_cart(session: AsyncSession, user_id: str) -> None:
        await session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        await session.commit()

    @staticmethod
    async def add_item(
        session: AsyncSession,
        user_id: str,
        product_id: str,
        quantity: int,
        name: str,
        price: float,
    ) -> CartItem:
        # 如果已存在对应商品，增加数量
        stmt = select(CartItem).where(
            CartItem.user_id == user_id, CartItem.product_id == product_id
        )
        result = await session.execute(stmt)
        cart_item = result.scalars().first()
        if cart_item:
            cart_item.quantity += quantity
            await session.commit()
            await session.refresh(cart_item)
            return cart_item
        # 否则新增
        new_item = CartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
        )
        session.add(new_item)
        await session.commit()
        await session.refresh(new_item)
        return new_item


class OrderCRUD:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: str,
        total_amount: Decimal,
        status: str = "pending",
    ) -> Order:
        order = Order(user_id=user_id, total_amount=total_amount, status=status)
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

    @staticmethod
    async def add_order_item(
        session: AsyncSession,
        order_id: str,
        product_id: str,
        quantity: int,
        unit_price: Decimal,
    ) -> OrderItem:
        order_item = OrderItem(
            order_id=order_id,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
        )
        session.add(order_item)
        await session.commit()
        await session.refresh(order_item)
        return order_item

    @staticmethod
    async def get_order(session: AsyncSession, order_id: str) -> Optional[Order]:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalars().first()

    @staticmethod
    async def list_user_orders(session: AsyncSession, user_id: str) -> List[Order]:
        result = await session.execute(select(Order).where(Order.user_id == user_id))
        return list(result.scalars().all())

    @staticmethod
    async def update_status(session: AsyncSession, order_id: str, status: str) -> bool:
        result = await session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status=status)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def delete(session: AsyncSession, user_id: str) -> bool:
        result = await session.execute(
            delete(User)
            .where(User.id == user_id)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def list_all(
        session: AsyncSession, limit: int = 100, offset: int = 0
    ) -> List[User]:
        result = await session.execute(select(User).limit(limit).offset(offset))
        return list(result.scalars().all())

    @staticmethod
    async def update_quantity(
        session: AsyncSession, cart_item_id: str, quantity: int
    ) -> bool:
        result = await session.execute(
            update(CartItem)
            .where(CartItem.id == cart_item_id)
            .values(quantity=quantity)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def remove_item(session: AsyncSession, cart_item_id: str) -> bool:
        result = await session.execute(
            delete(CartItem)
            .where(CartItem.id == cart_item_id)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0
