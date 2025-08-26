# db/__init__.py

from .base import Base
from .models import User, Product, CartItem, Order, OrderItem
from .crud import UserCRUD, ProductCRUD, CartCRUD, OrderCRUD
from .session import async_session_maker, get_async_session  

class MessageResponse:
    def __init__(self):
        self.db = async_session_maker()


    def get_data(self):
        return self.db



__all__ = [
    "Base",
    "User",
    "Product",
    "CartItem",
    "Order",
    "OrderItem",
    "UserCRUD",
    "ProductCRUD",
    "CartCRUD",
    "OrderCRUD",
    "async_session_maker",
]
