# handlers/__init__.py

from aiogram import Router

from .auth import setup_auth_handlers


from .profile import setup_profile_handlers
from .carts import setup_cart_handlers
from .carts import setup_cart_handlers
from .orders import setup_orders_handlers
from .admin import setup_admin_handlers
from .commands import setup_command_handlers
from .errors import setup_error_handlers
from .auth import setup_auth_handlers
from .profile import setup_profile_handlers
from aiogram import Router,Dispatcher
from .products import setup_products_handlers
from .buttons import router as buttons_router

def setup_all_handlers(dp: Router):
    dp.include_router(buttons_router)
    setup_auth_handlers(dp)
    setup_admin_handlers(dp)
    setup_orders_handlers(dp)
    setup_profile_handlers(dp)
    setup_command_handlers(dp)
    setup_error_handlers(dp)
    setup_products_handlers(dp)
    setup_cart_handlers(dp)
   


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

    
