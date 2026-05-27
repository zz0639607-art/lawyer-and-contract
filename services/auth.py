"""
services/auth.py
密码加密 + JWT 令牌 — 用户信息安全核心
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from models.database import User, get_db
from dotenv import load_dotenv

load_dotenv()

# ── 配置 ──────────────────────────────────────────────────
JWT_SECRET      = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_MIN  = int(os.getenv("JWT_EXPIRE_MINUTES", 10080))  # 默认 7 天

# bcrypt 加密上下文（自动加盐，不可逆）
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer Token 提取器
bearer_scheme = HTTPBearer(auto_error=False)


# ── 密码工具 ──────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """明文密码 → bcrypt 哈希（存数据库的值）"""
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """验证登录密码是否正确"""
    return pwd_ctx.verify(plain, hashed)


# ── JWT 工具 ──────────────────────────────────────────────
def create_token(user_id: int, email: str) -> str:
    """生成 JWT Access Token"""
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MIN),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 JWT，失败抛出异常"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── 当前用户依赖注入 ───────────────────────────────────────
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    从请求 Header 提取 Bearer Token，验证并返回当前登录用户。
    用法: current_user: User = Depends(get_current_user)
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account disabled.",
        )
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    可选认证：有 Token 则返回用户，没有则返回 None（用于免费试用接口）
    """
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload.get("sub", 0))
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except Exception:
        return None
