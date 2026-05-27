"""
services/email.py
发邮件核心逻辑 — 注册验证 + 忘记密码 + 付款通知
"""
import os
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SITE_URL      = os.getenv("SITE_URL", "http://localhost:8000")
FROM_NAME     = os.getenv("FROM_NAME", "LexAI")


def _send(to: str, subject: str, html: str):
    """底层发送函数"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to, msg.as_string())


def _base_template(title: str, content: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#f7f3ec;font-family:'Helvetica Neue',Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:40px 20px;">
          <table width="600" cellpadding="0" cellspacing="0"
                 style="background:#ffffff;border:1px solid #d8ceb8;border-radius:6px;overflow:hidden;">
            <!-- Header -->
            <tr>
              <td style="background:#111008;padding:24px 32px;">
                <span style="font-family:Georgia,serif;font-size:24px;font-weight:700;color:#ffffff;">
                  ⚖️ Lex<span style="color:#b8922a;">AI</span>
                </span>
              </td>
            </tr>
            <!-- Body -->
            <tr>
              <td style="padding:32px;">
                <h2 style="font-family:Georgia,serif;color:#111008;margin:0 0 16px;">{title}</h2>
                {content}
              </td>
            </tr>
            <!-- Footer -->
            <tr>
              <td style="background:#f7f3ec;padding:20px 32px;border-top:1px solid #d8ceb8;">
                <p style="margin:0;font-size:12px;color:#7a6f5a;">
                  ⚖️ LexAI · AI-powered contract analysis<br>
                  <em>This is an automated email. Please do not reply.</em>
                </p>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """


# ── 1. 邮箱验证 ───────────────────────────────────────────
def send_verification_email(to: str, token: str):
    link = f"{SITE_URL}/api/email/verify?token={token}"
    content = f"""
      <p style="color:#444;line-height:1.7;">
        Thanks for signing up! Click the button below to verify your email address.
        This link expires in <strong>24 hours</strong>.
      </p>
      <a href="{link}"
         style="display:inline-block;margin:20px 0;padding:12px 28px;
                background:#111008;color:#ffffff;text-decoration:none;
                border-radius:2px;font-size:15px;">
        Verify Email →
      </a>
      <p style="color:#7a6f5a;font-size:13px;">
        Or copy this link:<br>
        <a href="{link}" style="color:#b8922a;">{link}</a>
      </p>
    """
    _send(to, "Verify your LexAI email", _base_template("Verify Your Email", content))


# ── 2. 忘记密码 ───────────────────────────────────────────
def send_reset_email(to: str, token: str):
    link = f"{SITE_URL}/reset-password?token={token}"
    content = f"""
      <p style="color:#444;line-height:1.7;">
        We received a request to reset your LexAI password.
        Click the button below — this link expires in <strong>1 hour</strong>.
      </p>
      <a href="{link}"
         style="display:inline-block;margin:20px 0;padding:12px 28px;
                background:#a63320;color:#ffffff;text-decoration:none;
                border-radius:2px;font-size:15px;">
        Reset Password →
      </a>
      <p style="color:#7a6f5a;font-size:13px;">
        If you didn't request this, you can safely ignore this email.
      </p>
    """
    _send(to, "Reset your LexAI password", _base_template("Reset Your Password", content))


# ── 3. 欢迎邮件（注册成功）────────────────────────────────
def send_welcome_email(to: str, name: str):
    display = name or "there"
    content = f"""
      <p style="color:#444;line-height:1.7;">Hi {display},</p>
      <p style="color:#444;line-height:1.7;">
        Welcome to LexAI! Your account is ready.
        You have <strong>3 free contract analyses</strong> this month to get started.
      </p>
      <a href="{SITE_URL}"
         style="display:inline-block;margin:20px 0;padding:12px 28px;
                background:#111008;color:#ffffff;text-decoration:none;
                border-radius:2px;font-size:15px;">
        Analyze a Contract →
      </a>
      <p style="color:#7a6f5a;font-size:13px;">
        Need unlimited analyses? Upgrade to Pro for just $9.9/month.
      </p>
    """
    _send(to, "Welcome to LexAI 🎉", _base_template("Welcome to LexAI", content))


# ── 4. 升级成功通知 ───────────────────────────────────────
def send_upgrade_email(to: str, name: str, plan: str):
    display = name or "there"
    content = f"""
      <p style="color:#444;line-height:1.7;">Hi {display},</p>
      <p style="color:#444;line-height:1.7;">
        Your account has been upgraded to <strong>{plan.upper()}</strong>. 🎉<br>
        You now have <strong>unlimited contract analyses</strong> and chats.
      </p>
      <a href="{SITE_URL}"
         style="display:inline-block;margin:20px 0;padding:12px 28px;
                background:#b8922a;color:#111008;text-decoration:none;
                border-radius:2px;font-size:15px;">
        Start Analyzing →
      </a>
    """
    _send(to, f"You're now on LexAI {plan.capitalize()}!", _base_template("Upgrade Successful", content))


# ── 生成安全 Token（存数据库用）──────────────────────────────
def generate_token(length: int = 64) -> str:
    return secrets.token_urlsafe(length)
