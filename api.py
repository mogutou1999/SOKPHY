from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
import uvicorn

from db.session import get_async_session
from db.crud import UserCRUD, ProductCRUD, OrderCRUD

# === 创建 FastAPI 实例 ===
app = FastAPI(
    title="My Online Shop API",
    description="一个示例 API，支持用户、商品、订单管理",
    version="1.0.0",
)

# === CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 正式上线请替换
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === 健康检查 ===
@app.get("/health", response_model=dict)
async def health_check():
    return {"status": "ok"}


# === 获取用户 ===
@app.get("/users/{telegram_id}", response_model=dict)
async def get_user(
    telegram_id: int, session: AsyncSession = Depends(get_async_session)
):
    user = await UserCRUD.get_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
    }


# === 创建商品 ===
@app.post("/products", response_model=dict)
async def create_product(
    name: str,
    price: Decimal,
    stock: int = 0,
    description: str = "",
    session: AsyncSession = Depends(get_async_session),
):
    product = await ProductCRUD.create(
        session, name=name, price=price, stock=stock, description=description
    )
    return {
        "id": product.id,
        "name": product.name,
        "price": str(product.price),
        "stock": product.stock,
        "description": product.description,
    }


# === 列出所有商品 ===
@app.get("/products", response_model=list)
async def list_products(session: AsyncSession = Depends(get_async_session)):
    products = await ProductCRUD.list_active(session)
    return [
        {
            "id": p.id,
            "name": p.name,
            "price": str(p.price),
            "stock": p.stock,
        }
        for p in products
    ]


# === 创建订单 ===
@app.post("/orders", response_model=dict)
async def create_order(
    user_id: int,
    total_amount: Decimal,
    session: AsyncSession = Depends(get_async_session),
):
    order = await OrderCRUD.create_order(
        session, user_id=user_id, total_amount=total_amount
    )
    return {
        "id": order.id,
        "user_id": order.user_id,
        "amount": str(order.total_amount),
        "status": order.status,
    }


# === 列出用户订单 ===
@app.get("/orders/{user_id}", response_model=list)
async def list_orders(user_id: int, session: AsyncSession = Depends(get_async_session)):
    orders = await OrderCRUD.list_user_orders(session, user_id=user_id)
    return [
        {"id": o.id, "status": o.status, "amount": str(o.total_amount)} for o in orders
    ]


# === 启动入口 ===
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
