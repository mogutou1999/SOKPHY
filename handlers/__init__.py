# handlers/__init__.py

from aiogram import Router

from .auth import setup_auth_handlers


from .profile import setup_profile_handlers
from .carts import setup_cart_handlers
from .carts import setup_cart_handlers
from .orders import setup_orders_handlers
from .admin import setup_admin_handlers
from .commands import setup_command_handlers# handlers/__init__.py
from aiogram import Router

from .admin_products import router as admin_products_router
from .auth import router as auth_router
from .menu import router as menu_router
from .products import router as products_router
from .orders import router as orders_router
from .carts import router as carts_router
from .admin import router as admin_router
from .profile import router as profile_router
from .buttons import router as buttons_router
from .commands import router as commands_router
from .errors import router as errors_router

def setup_all_handlers(dp: Router):
    """
    统一注册所有 aiogram handler routers
    """
    dp.include_router(buttons_router)
    dp.include_router(auth_router)
    dp.include_router(menu_router)
    dp.include_router(products_router)
    dp.include_router(orders_router)
    dp.include_router(carts_router)
    dp.include_router(admin_router)
    dp.include_router(profile_router)
    dp.include_router(commands_router)
    dp.include_router(errors_router)
    dp.include_router(admin_products_router)
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

    
