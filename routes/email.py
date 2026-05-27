"""
routes/email.py
邮件相关接口
POST /api/email/verify-send     — 发送验证邮件
GET  /api/email/verify          — 验证邮箱（点链接）
POST /api/email/forgot-password — 发送重置密码邮件
POST /api/email/reset-password  — 重置密码
"""
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Session

from models.database import Base, get_db, User
from services.auth   import hash_password, get_current_user
from services.email  import (
    send_verification_email,
    send_reset_email,
    generate_token,
)

router = APIRouter(prefix="/email", tags=["Email"])

TOKEN_EXPIRE_HOURS = 24   # 验证邮件有效期
RESET_EXPIRE_HOURS = 1    # 重置密码有效期


# ── Token 表（存数据库）───────────────────────────────────
class EmailToken(Base):
    __tablename__ = "email_tokens"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token      = Column(String(128), unique=True, index=True, nullable=False)
    purpose    = Column(String(30))          # "verify" | "reset"
    expires_at = Column(DateTime, nullable=False)
    used       = Column(String(1), default="0")   # "0"=未用 "1"=已用


# ── 请求体 ────────────────────────────────────────────────
class EmailRequest(BaseModel):
    email: EmailStr

class ResetRequest(BaseModel):
    token:        str
    new_password: str


# ── 1. 发送验证邮件 ───────────────────────────────────────
@router.post("/verify-send", status_code=200)
def send_verify(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    if current_user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified.")

    token = generate_token()
    db.add(EmailToken(
        user_id    = current_user.id,
        token      = token,
        purpose    = "verify",
        expires_at = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    ))
    db.commit()
    send_verification_email(current_user.email, token)
    return {"message": "Verification email sent."}


# ── 2. 验证邮箱（点链接后调用）────────────────────────────
@router.get("/verify", status_code=200)
def verify_email(token: str, db: Session = Depends(get_db)):
    record = db.query(EmailToken).filter(
        EmailToken.token   == token,
        EmailToken.purpose == "verify",
        EmailToken.used    == "0",
    ).first()

    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link.")

    # 标记已验证
    user = db.query(User).filter(User.id == record.user_id).first()
    user.is_verified = True
    record.used = "1"
    db.commit()
    return {"message": "Email verified successfully. You can now log in."}


# ── 3. 发送重置密码邮件 ───────────────────────────────────
@router.post("/forgot-password", status_code=200)
def forgot_password(req: EmailRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    # 不论用户是否存在都返回相同响应，防止枚举攻击
    if user:
        token = generate_token()
        db.add(EmailToken(
            user_id    = user.id,
            token      = token,
            purpose    = "reset",
            expires_at = datetime.utcnow() + timedelta(hours=RESET_EXPIRE_HOURS),
        ))
        db.commit()
        send_reset_email(user.email, token)
    return {"message": "If this email exists, a reset link has been sent."}


# ── 4. 重置密码 ───────────────────────────────────────────
@router.post("/reset-password", status_code=200)
def reset_password(req: ResetRequest, db: Session = Depends(get_db)):
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    record = db.query(EmailToken).filter(
        EmailToken.token   == req.token,
        EmailToken.purpose == "reset",
        EmailToken.used    == "0",
    ).first()

    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    user = db.query(User).filter(User.id == record.user_id).first()
    user.password_hash = hash_password(req.new_password)
    record.used = "1"
    db.commit()
    return {"message": "Password reset successfully. You can now log in."}
