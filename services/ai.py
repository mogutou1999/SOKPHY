# services/ai.py

import httpx
from config.settings import settings

async def call_external_ai(prompt: str) -> str:
    """
    占位函数：
    以后要对接 OpenAI、Claude、Llama 等，把这里写好就行。
    """
    # TODO: 替换为你的外部大模型请求
    # 这里只是示例
    return f"🤖 (AI 回复占位) 你刚才说: {prompt}"