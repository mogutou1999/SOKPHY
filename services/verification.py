# services/verification.py

import random
import string
import redis.asyncio as aioredis
from config.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User
from sqlalchemy import select, update

# Redis 客户端
redis = aioredis.from_url(settings.redis_url)

DEFAULT_EXPIRE = 300  # 有效期 5 分钟
# 生成随机验证码
async def generate_verification_code(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))
# 保存验证码
async def save_code(target: str, code: str, expire: int = 300):
    await redis.setex(f"verify:{target}", expire, code)
# 验证用户输入
async def verify_code(target: str, input_code: str) -> bool:
    key = f"verify:{target}"
    real_code = await redis.get(key)
    if real_code and real_code.decode() == input_code:
        await redis.delete(key)
        return True
    return False

# 发送验证码（占位函数）
async def send_sms(phone: str, code: str):
    # TODO: 调用短信供应商 API
    print(f"给手机号 {phone} 发送验证码 {code}")
async def send_email(email: str, code: str):
    # TODO: 调用邮件发送服务
    print(f"给邮箱 {email} 发送验证码 {code}")
# 注册流程：发送验证码
async def request_verification(target: str, is_email: bool = False):
    code = await generate_verification_code()
    await save_code(target, code)
    if is_email:
        await send_email(target, code)
    else:
        await send_sms(target, code)
    return code


# 验证流程：检查并更新用户状态
async def confirm_verification(
    session: AsyncSession,
    target: str,
    input_code: str,
    is_email: bool = False,
):
    ok = await verify_code(target, input_code)
    if not ok:
        return False

    stmt = select(User).where(User.email == target) if is_email else select(User).where(User.phone == target)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.is_verified = True
        await session.commit()
    return True

