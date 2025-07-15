from fastapi import APIRouter
from services.payment import get_payment_service
from config.settings import settings
from fastapi import APIRouter, HTTPException

router = APIRouter()


ADMIN_IDS = settings.admin_ids


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.post("/pay")
async def pay(user_id: int, amount: float, currency: str = "USD"):
    if not is_admin(user_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    payment_service = await get_payment_service()
    result = await payment_service.create_payment(amount=amount, currency=currency)
    return result


def setup_payment_handlers(router: APIRouter):
    router.include_router(router, prefix="/payment")
