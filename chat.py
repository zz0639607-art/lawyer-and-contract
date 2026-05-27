"""
routes/chat.py
POST /api/chat  —  AI 律师对话（多轮）
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from models.database import User, get_db
from services.gemini  import call_gemini
from services.auth    import get_optional_user
from services.limiter import check_and_log

router = APIRouter()


# ── 请求/响应体 ──────────────────────────────────────────
class Message(BaseModel):
    role:    str
    content: str

class ChatRequest(BaseModel):
    message:  str = Field(..., min_length=1)
    history:  list[Message] = Field(default_factory=list)
    language: str = Field(default="English")

class ChatResponse(BaseModel):
    reply:  str
    usage:  dict | None = None


# ── Prompt ────────────────────────────────────────────────
def build_prompt(message: str, history: list[Message], language: str) -> str:
    system = f"""You are LexAI, a friendly and knowledgeable AI legal assistant.
Help people understand contracts and legal concepts in plain language.
You are NOT a licensed attorney — always remind users to consult a professional for important decisions.
Respond entirely in {language}. Use bullet points for lists. Keep responses concise and actionable.
"""
    history_str = "\n".join(
        f"{'User' if m.role == 'user' else 'LexAI'}: {m.content}"
        for m in history[-10:]
    )
    return f"{system}\n\nConversation:\n{history_str}\nUser: {message}\nLexAI:"


# ── Route ────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat(
    req:          ChatRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db:           Session        = Depends(get_db),
):
    usage_info = None
    if current_user:
        usage_info = check_and_log(db, current_user, "chat")

    try:
        reply = await call_gemini(
            build_prompt(req.message, req.history, req.language),
            max_tokens=1000,
            temperature=0.5,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    return ChatResponse(reply=reply.strip(), usage=usage_info)

