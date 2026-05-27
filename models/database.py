"""
models/database.py
数据库连接、表结构定义
"""
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String,
    DateTime, Boolean, Text, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lexai.db")

# SQLite 需要 check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── 用户表 ────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)          # bcrypt，绝不存明文
    display_name  = Column(String(100), nullable=True)
    plan          = Column(String(20), default="free")           # free / pro / business
    is_active     = Column(Boolean, default=True)
    is_verified   = Column(Boolean, default=False)               # 邮箱验证
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login    = Column(DateTime, nullable=True)

    # 关联
    analyses      = relationship("Analysis", back_populates="user", cascade="all, delete-orphan")
    usage         = relationship("UsageLog",  back_populates="user", cascade="all, delete-orphan")


# ── 合同分析记录表 ──────────────────────────────────────────
class Analysis(Base):
    __tablename__ = "analyses"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    contract_type    = Column(String(100))
    jurisdiction     = Column(String(100))
    user_role        = Column(String(100))
    report_lang      = Column(String(50))
    risk_level       = Column(String(10))     # Red / Yellow / Green
    risk_pct         = Column(Integer)
    # 存储 AI 报告摘要（不存原始合同文本，保护用户隐私）
    executive_summary = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="analyses")

    __table_args__ = (
        Index("ix_analyses_user_created", "user_id", "created_at"),
    )


# ── 使用量记录表 ───────────────────────────────────────────
class UsageLog(Base):
    __tablename__ = "usage_logs"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    action     = Column(String(50))    # "analyze" / "chat"
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="usage")

    __table_args__ = (
        Index("ix_usage_user_created", "user_id", "created_at"),
    )


# ── DB Session 依赖注入 ────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── 建表（首次启动自动执行）────────────────────────────────
def init_db():
    Base.metadata.create_all(bind=engine)
