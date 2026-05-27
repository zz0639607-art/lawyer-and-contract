# LexAI Backend

AI-powered contract analysis API built with FastAPI + Google Gemini.

## 项目结构

```
lexai-backend/
├── main.py                 # FastAPI 入口
├── routes/
│   ├── analyze.py          # POST /api/analyze
│   └── chat.py             # POST /api/chat
├── services/
│   └── gemini.py           # Gemini API 封装
├── requirements.txt
├── .env.example            # 环境变量模板
└── .gitignore
```

## 本地启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 Gemini API Key

# 3. 启动服务
uvicorn main:app --reload

# 服务地址: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

## API 接口

### POST /api/analyze — 合同分析

**请求体：**
```json
{
  "contract_text": "合同全文...",
  "contract_type": "Employment Contract",
  "jurisdiction":  "China",
  "user_role":     "Employee / Worker",
  "report_lang":   "中文（简体）"
}
```

**响应：**
```json
{
  "risk_level": "Red",
  "risk_pct": 75,
  "contract_match": "Employment contract under Chinese labor law — compatible.",
  "executive_summary": "...",
  "module2_rows": [
    { "clause": "Non-compete", "risk": "🔴", "implication": "..." }
  ],
  "module3_items": [
    {
      "clause_name": "Non-compete",
      "original": "...",
      "revised": "...",
      "talk_track": "..."
    }
  ],
  "module4_date_flag": "None detected",
  "module4_crossborder": "None applicable"
}
```

### POST /api/chat — AI 律师对话

**请求体：**
```json
{
  "message": "什么是竞业禁止条款？",
  "history": [
    { "role": "user",      "content": "你好" },
    { "role": "assistant", "content": "你好！有什么可以帮助你的？" }
  ],
  "language": "中文（简体）"
}
```

**响应：**
```json
{
  "reply": "竞业禁止条款是指..."
}
```

## 免费部署（Railway）

1. 注册 [railway.app](https://railway.app)（免费）
2. 新建项目 → Deploy from GitHub
3. 上传代码到 GitHub，连接仓库
4. 在 Railway 环境变量里添加 `GEMINI_API_KEY`
5. 自动部署完成，获得公网 URL

## 连接前端

前端 HTML 里把 API 调用从 Gemini 直接请求改为：
```javascript
// 改前（直接调 Gemini）
fetch(`https://generativelanguage.googleapis.com/...`)

// 改后（走你的后端）
fetch(`https://your-backend.railway.app/api/analyze`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ contract_text, contract_type, jurisdiction, user_role, report_lang })
})
```

## 注意事项

- `.env` 文件绝对不要上传 GitHub
- 上线后把 CORS `allow_origins` 改为你的真实域名
- Gemini 免费额度：每天 1500 次请求，完全够用
