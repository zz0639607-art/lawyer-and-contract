"""
services/limiter.py
使用量限制 — 免费用户每月分析次数上限
"""
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.database import User, UsageLog

# ── 各套餐每月限额 ──────────────────────────────────────────
PLAN_LIMITS = {
    "free":     {"analyze": 3,   "chat": 30},
    "pro":      {"analyze": 999, "chat": 999},
    "business": {"analyze": 999, "chat": 999},
}


def get_monthly_usage(db: Session, user_id: int, action: str) -> int:
    """查询用户本月某动作的使用次数"""
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(UsageLog)
        .filter(
            UsageLog.user_id == user_id,
            UsageLog.action  == action,
            UsageLog.created_at >= start_of_month,
        )
        .count()
    )


def check_and_log(db: Session, user: User, action: str) -> dict:
    """
    检查用户是否超出限额，未超出则记录一次使用。
    返回当前使用情况字典。
    超出限额时抛出 429 Too Many Requests。
    """
    limit   = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])[action]
    used    = get_monthly_usage(db, user.id, action)
    remaining = max(0, limit - used)

    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error":     "quota_exceeded",
                "message":   f"You have used all {limit} {action} credits for this month.",
                "plan":      user.plan,
                "limit":     limit,
                "used":      used,
                "remaining": 0,
                "upgrade":   "Upgrade to Pro for unlimited access.",
            },
        )

    # 记录使用
    db.add(UsageLog(user_id=user.id, action=action))
    db.commit()

    return {"plan": user.plan, "limit": limit, "used": used + 1, "remaining": remaining - 1}


def get_usage_summary(db: Session, user: User) -> dict:
    """返回用户所有动作的本月使用摘要"""
    summary = {}
    for action in ["analyze", "chat"]:
        limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])[action]
        used  = get_monthly_usage(db, user.id, action)
        summary[action] = {
            "limit":     limit,
            "used":      used,
            "remaining": max(0, limit - used),
        }
    return summary
