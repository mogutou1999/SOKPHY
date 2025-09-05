# api.py
from fastapi import  Depends, HTTPException, APIRouter,FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from handlers import products
from enum import Enum
from typing import List, Optional, Sequence
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from db.session import get_async_session
from db.crud import UserCRUD, ProductCRUD, OrderCRUD, CartCRUD
from config.settings import get_app_settings, settings
from services.orders import get_orders_by_user
from handlers.payment import get_payment_service
from uuid import UUID
from db.models import OrderStatus
from datetime import datetime
from services import orders as order_service
from utils.cache import cache_get, cache_set



router = APIRouter()
app = FastAPI()

# === Pydantic Models ===
class ProductCreate(BaseModel):
    name: str
    price: Decimal
    stock: int = 0
    description: str = "" 


class UserOut(BaseModel):
    id: UUID
    telegram_id: int
    username: Optional[str] = None
    is_admin: bool = False

    model_config = {"from_attributes": True}

class ProductOut(BaseModel):
    id: UUID
    name: str
    price: Decimal
    stock: int
    description: Optional[str] = ""

    model_config = {"from_attributes": True}
    
class CartItemOut(BaseModel):
    id: UUID
    user_id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price: Decimal

    model_config = {"from_attributes": True}    

class OrderItemOut(BaseModel):
    product_id: UUID
    quantity: int
    unit_price: Decimal

    model_config = {"from_attributes": True}

class OrderOut(BaseModel):
    id: UUID
    user_id: UUID
    items: List[OrderItemOut]
    total_amount: Decimal
    status: OrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}

@app.get("/some")
async def some_handler(request: Request):
    redis = request.app.state.redis  # 拿到共享的 Redis 客户端
    value = await redis.get("some_key")
    return {"value": value}
    
    
@router.get("/")
async def root():
    return {
        "message": "Hello World",
        "products": ["Product 1", "Product 2"]
    }

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/features")
async def get_features():
    return JSONResponse(content={
        "status": 200,
        "features_count": 516,
        "features": [
            {"id": 1, "name": "商品管理", "description": "管理员可添加/删除/修改商品"},
            {"id": 2, "name": "订单管理", "description": "用户下单、支付、查看订单"},
            {"id": 3, "name": "用户管理", "description": "管理员可管理用户信息"},
            {"id": 4, "name": "支付系统", "description": "支持支付宝、微信等支付方式"}
        ]
    })

@router.get("/users/{telegram_id}", response_model=UserOut)
async def get_user_cached(
    telegram_id: int,
    request: Request,  # ✅ 加上这个
    session: AsyncSession = Depends(get_async_session)
):
    cached = await cache_get(request, f"user:{telegram_id}")  # ✅ 正确传参
    if cached:
        return {"user": cached, "source": "cache"}

    user = await UserCRUD.get_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await cache_set(request, f"user:{telegram_id}", user.username)

    return UserOut.model_validate(user)

@router.post("/products", response_model=List[ProductOut])
async def create_product(
    product_data: ProductCreate,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        product = await ProductCRUD.create(
            session=session,
            name=product_data.name,
            price=product_data.price,
            stock=product_data.stock,
            description=product_data.description or "",  # 确保 description 不为 None
        )
        if not product:
            raise HTTPException(status_code=400, detail="创建商品失败")
        await session.commit()
        return ProductOut.model_validate(product)
    except SQLAlchemyError as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"数据库错误: {str(e)}")

@router.get("/products", response_model=List[ProductOut])
async def list_products(
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
):
    products = await ProductCRUD.search_products(session, search=search)
    return [ProductOut.model_validate(p) for p in products]

@router.post("/cart/add")
async def add_to_cart(
    user_id: UUID,
    product_id: UUID,
    quantity: int,
    product_name: str,
    unit_price: Decimal,
    session: AsyncSession = Depends(get_async_session),
):
    cart_item = await CartCRUD.add_item(
        session=session,
        user_id=user_id,
        product_id=product_id,
        quantity=quantity,
        product_name=product_name,
        unit_price=unit_price,
    )
    return {
        "message": "已加入购物车",
        "cart_item_id": cart_item.id,
        "product_name": cart_item.product_name,
        "quantity": cart_item.quantity,
        "unit_price": str(cart_item.unit_price),
    }

@router.get("/orders/{user_id}", response_model=List[OrderOut])
async def list_orders(user_id: UUID, session: AsyncSession = Depends(get_async_session)):
    orders = await order_service.get_orders_by_user(user_id, session)

    result = []
    for o in orders:
        items_out = [
            OrderItemOut(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price  # 必须提供
            )
            for item in getattr(o, "items", [])
        ]
        result.append(
            OrderOut(
                id=o.id,
                user_id=o.user_id,
                items=items_out,
                total_amount=o.total_amount,
                status=OrderStatus(o.status.value),
                created_at=o.created_at
            )
        )

    return result

@router.post("/pay")
async def pay(total_amount: Decimal):
    payment_service = await get_payment_service()
    result = await payment_service.pay(float(total_amount)) 
    return result
