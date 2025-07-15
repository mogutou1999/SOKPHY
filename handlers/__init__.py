# handlers/__init__.py

from aiogram import Router

from .auth import setup_auth_handlers


from .profile import setup_profile_handlers
from .carts import setup_cart_handlers


def setup_all_handlers() -> Router:
    """
    创建并组合所有路由
    """
    router = Router()
    setup_auth_handlers(router)
    
  
    setup_profile_handlers(router)
    setup_cart_handlers(router)
    return router
    return router

    # Handlers/__init__.py

