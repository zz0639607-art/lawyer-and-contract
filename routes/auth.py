"""
routes/auth.py
POST /api/auth/register   — 注册
POST /api/auth/login      — 登录
GET  /api/auth/me         — 获取当前用户信息
PUT  /api/auth/me         — 修改个人资料
POST /api/auth/change-password — 修改密码
GET  /api/auth/usage      — 查看本月使用量
DELETE /api/auth/account  — 注销账号（GDPR 合规）
"""
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from models.database import User, Analysis, UsageLog, get_db
from services.auth    import hash_password, verify_password, create_token, get_current_user
from services.limiter import get_usage_summary

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── 输入校验模型 ───────────────────────────────────────────
class RegisterRequest(BaseModel):
    email:        EmailStr
    password:     str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number.")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(..., max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number.")
        return v


# ── 响应模型（绝不返回密码哈希）──────────────────────────────
class UserResponse(BaseModel):
    id:           int
    email:        str
    display_name: str | None
    plan:         str
    is_verified:  bool
    created_at:   datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserResponse


# ── 注册 ──────────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # 检查邮箱是否已注册
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email         = req.email.lower().strip(),
        password_hash = hash_password(req.password),   # bcrypt 加密
        display_name  = req.display_name.strip() or None,
        plan          = "free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.email)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


# ── 登录 ──────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.email == req.email.lower(),
        User.is_active == True,
    ).first()

    # 故意用相同错误信息，防止枚举攻击
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_token(user.id, user.email)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


# ── 获取个人信息 ───────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


# ── 修改个人资料 ───────────────────────────────────────────
@router.put("/me", response_model=UserResponse)
def update_me(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.display_name = req.display_name.strip() or None
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


# ── 修改密码 ───────────────────────────────────────────────
@router.post("/change-password", status_code=200)
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


# ── 查看本月使用量 ─────────────────────────────────────────
@router.get("/usage")
def get_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "plan":  current_user.plan,
        "usage": get_usage_summary(db, current_user),
    }


# ── 注销账号（GDPR 合规：删除所有个人数据）────────────────────
@router.delete("/account", status_code=200)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 级联删除：analyses 和 usage_logs 会随 user 一起删除
    db.delete(current_user)
    db.commit()
    return {"message": "Account and all associated data have been permanently deleted."}


# ── 历史分析记录 ───────────────────────────────────────────
@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    records = (
        db.query(Analysis)
        .filter(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .limit(min(limit, 50))
        .all()
    )
    return [
        {
            "id":                r.id,
            "contract_type":     r.contract_type,
            "jurisdiction":      r.jurisdiction,
            "risk_level":        r.risk_level,
            "risk_pct":          r.risk_pct,
            "executive_summary": r.executive_summary,
            "created_at":        r.created_at,
        }
        for r in records
    ]
