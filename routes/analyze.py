"""
routes/analyze.py
POST /api/analyze  —  合同分析，返回 4 模块结构化报告
- 登录用户：检查使用量限额，保存历史记录
- 未登录用户：每个 IP 每天最多 1 次（试用）
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from models.database import User, Analysis, get_db
from services.gemini  import call_gemini_json
from services.auth    import get_optional_user
from services.limiter import check_and_log

router = APIRouter()


# ── 请求体 ──────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    contract_text: str = Field(..., min_length=50, description="合同原文")
    contract_type: str = Field(default="General Contract")
    jurisdiction:  str = Field(default="International")
    user_role:     str = Field(default="General / Unknown")
    report_lang:   str = Field(default="English")


# ── 响应体 ──────────────────────────────────────────────
class ClauseRow(BaseModel):
    clause:      str
    risk:        str
    implication: str

class RedlineItem(BaseModel):
    clause_name: str
    original:    str
    revised:     str
    talk_track:  str

class AnalyzeResponse(BaseModel):
    risk_level:          str
    risk_pct:            int
    contract_match:      str
    executive_summary:   str
    module2_rows:        list[ClauseRow]
    module3_items:       list[RedlineItem]
    module4_date_flag:   str
    module4_crossborder: str
    usage:               dict | None = None   # 返回剩余次数给前端显示


# ── System Prompt ────────────────────────────────────────
SYSTEM_PROMPT = """You are LexAI, an elite international legal AI and contract analysis specialist.
Your target users are global freelancers, remote workers, and SMBs.
Your tone is professional, legally precise, clear, and actionable.

CONTRACT DETAILS:
- Jurisdiction:    {jurisdiction}
- Contract_Type:   {contract_type}
- User_Role:       {user_role}
- Report Language: {report_lang}

CORE DIRECTIVES:
1. Legal Alignment: Adapt analysis to {jurisdiction} legal system (Common Law vs Civil Law).
   Cite specific regional laws (GDPR/CCPA for privacy, local labour laws for employment) where risks occur.
2. Risk Identification: Scan for: Non-compete, Governing Law, Arbitration, Data Privacy,
   Force Majeure, Indemnity, Intellectual Property.
3. PII Safety: Do NOT echo any SSN, IBAN, passport numbers, or other sensitive PII.

RESPOND WITH ONLY A VALID JSON OBJECT — no markdown fences, no explanation outside the JSON.
Use this exact structure:
{{
  "risk_level": "Red|Yellow|Green",
  "risk_pct": <integer 0-100>,
  "contract_match": "<one sentence confirming or flagging contract_type + jurisdiction compatibility>",
  "executive_summary": "<2-3 sentence overall assessment>",
  "module2_rows": [
    {{ "clause": "<name>", "risk": "🔴|🟡|🟢", "implication": "<legal implication for {user_role}>" }}
  ],
  "module3_items": [
    {{
      "clause_name": "<name of risky clause>",
      "original":    "<excerpt max 60 words>",
      "revised":     "<exact legally-sound replacement text>",
      "talk_track":  "<one polite professional sentence to send to counterparty>"
    }}
  ],
  "module4_date_flag":   "<date/currency format ambiguity, or 'None detected'>",
  "module4_crossborder": "<tax withholding or trade compliance warning, or 'None applicable'>"
}}

Rules:
- Respond entirely in {report_lang}.
- Only include 🔴 and 🟡 items in module3_items.
- Cite real laws only. No hallucinations.

CONTRACT TEXT:
---
{contract_text}
---"""


# ── Route ────────────────────────────────────────────────
@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_contract(
    req:          AnalyzeRequest,
    request:      Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db:           Session        = Depends(get_db),
):
    usage_info = None

    if current_user:
        # 登录用户：检查月度配额
        usage_info = check_and_log(db, current_user, "analyze")
    else:
        # 未登录：用 IP 做简单限流（每 IP 每天 1 次试用）
        client_ip = request.client.host
        from datetime import date
        from models.database import UsageLog
        today_start_str = str(date.today())
        from sqlalchemy import func, cast, Date
        guest_count = (
            db.query(UsageLog)
            .filter(
                UsageLog.user_id == 0,           # 0 代表访客
                UsageLog.action  == f"guest:{client_ip}",
                func.date(UsageLog.created_at)   == today_start_str,
            )
            .count()
        )
        if guest_count >= 1:
            raise HTTPException(
                status_code=429,
                detail={
                    "error":   "guest_limit",
                    "message": "Free trial: 1 analysis per day for guests. Sign up for more.",
                    "signup":  "/api/auth/register",
                },
            )
        # 记录访客使用
        from models.database import UsageLog as UL
        db.add(UL(user_id=0, action=f"guest:{client_ip}"))
        db.commit()

    # ── 调用 AI ──
    prompt = SYSTEM_PROMPT.format(
        jurisdiction  = req.jurisdiction,
        contract_type = req.contract_type,
        user_role     = req.user_role,
        report_lang   = req.report_lang,
        contract_text = req.contract_text[:4500],
    )

    try:
        data = await call_gemini_json(prompt, max_tokens=2500)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    # ── 保存历史（仅登录用户，不存原始合同文本）──
    if current_user:
        db.add(Analysis(
            user_id           = current_user.id,
            contract_type     = req.contract_type,
            jurisdiction      = req.jurisdiction,
            user_role         = req.user_role,
            report_lang       = req.report_lang,
            risk_level        = data.get("risk_level", ""),
            risk_pct          = int(data.get("risk_pct", 0)),
            executive_summary = data.get("executive_summary", "")[:500],
        ))
        db.commit()

    # ── 构建响应 ──
    try:
        return AnalyzeResponse(
            risk_level          = data.get("risk_level", "Yellow"),
            risk_pct            = int(data.get("risk_pct", 50)),
            contract_match      = data.get("contract_match", ""),
            executive_summary   = data.get("executive_summary", ""),
            module2_rows        = [ClauseRow(**r)    for r in data.get("module2_rows",  [])],
            module3_items       = [RedlineItem(**i)  for i in data.get("module3_items", [])],
            module4_date_flag   = data.get("module4_date_flag",   "None detected"),
            module4_crossborder = data.get("module4_crossborder", "None applicable"),
            usage               = usage_info,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Response parsing error: {str(e)}")
