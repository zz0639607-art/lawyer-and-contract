"""
services/gemini.py
Gemini API 封装 — 所有 AI 调用都走这里
"""
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/gemini-1.5-flash:generateContent"
)


async def call_gemini(prompt: str, max_tokens: int = 2500, temperature: float = 0.3) -> str:
    """
    向 Gemini API 发送请求，返回纯文本响应。
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in environment variables.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"Gemini API error: {data['error']['message']}")

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError("Unexpected Gemini response format.")


async def call_gemini_json(prompt: str, max_tokens: int = 2500) -> dict:
    """
    调用 Gemini 并解析 JSON 响应。
    自动去除 markdown 代码块包裹。
    """
    raw = await call_gemini(prompt, max_tokens=max_tokens, temperature=0.2)
    cleaned = raw.strip()
    # 去除 ```json ... ``` 包裹
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[-1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned.strip())
