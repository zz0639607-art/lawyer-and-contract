"""
main.py — LexAI Backend 主程序
启动: uvicorn main:app --reload
文档: http://localhost:8000/docs
"""
import os, time, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from models.database import init_db
from routes.analyze  import router as analyze_router
from routes.chat     import router as chat_router
from routes.auth     import router as auth_router
from routes.email    import router as email_router

load_dotenv()
ENV = os.getenv("ENV", "development")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lexai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database…")
    init_db()
    logger.info(f"LexAI API started — ENV={ENV}")
    yield
    logger.info("LexAI API shutting down.")


app = FastAPI(
    title="LexAI API",
    description="AI-powered international contract analysis and legal assistant.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────
ALLOWED_ORIGINS = (
    ["*"] if ENV == "development"
    else os.getenv("ALLOWED_ORIGINS", "").split(",")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ── 安全响应头 ─────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["X-XSS-Protection"]       = "1; mode=block"
    response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    if ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# ── 请求日志 ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start    = time.perf_counter()
    response = await call_next(request)
    elapsed  = (time.perf_counter() - start) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.1f}ms)")
    return response

# ── 全局异常处理 ───────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please try again later."},
    )

# ── Routers ───────────────────────────────────────────────
app.include_router(auth_router,    prefix="/api", tags=["Auth"])
app.include_router(email_router,   prefix="/api", tags=["Email"])
app.include_router(analyze_router, prefix="/api", tags=["Contract Analysis"])
app.include_router(chat_router,    prefix="/api", tags=["AI Lawyer Chat"])

# ── Health ────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "LexAI API",
        "version": "1.0.0",
        "status":  "ok",
        "env":     ENV,
        "endpoints": {
            "register":       "POST /api/auth/register",
            "login":          "POST /api/auth/login",
            "me":             "GET  /api/auth/me",
            "usage":          "GET  /api/auth/usage",
            "history":        "GET  /api/auth/history",
            "verify-send":    "POST /api/email/verify-send",
            "verify":         "GET  /api/email/verify?token=",
            "forgot-password":"POST /api/email/forgot-password",
            "reset-password": "POST /api/email/reset-password",
            "analyze":        "POST /api/analyze",
            "chat":           "POST /api/chat",
            "docs":           "GET  /docs",
        },
    }

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
