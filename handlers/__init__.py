# handlers/__init__.py
from aiogram import Router
from .start import router as start_router
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
from .payment import router as payment_router
from .admin_config import router as admin_config_router
from .admin_users import router as admin_users_router


def setup_all_handlers(dp: Router):
    """
    统一注册所有 aiogram handler routers
    """
    dp.include_router(start_router)
    dp.include_router(auth_router)
    dp.include_router(menu_router)
    dp.include_router(products_router)
    dp.include_router(carts_router)
    dp.include_router(orders_router)
    dp.include_router(profile_router)
    dp.include_router(buttons_router)
    dp.include_router(commands_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)
    dp.include_router(admin_products_router)
    dp.include_router(admin_users_router)
    dp.include_router(admin_config_router)
    dp.include_router(errors_router)
