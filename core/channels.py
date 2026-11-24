"""Delivery channels: email over SMTP and Telegram over the Bot API."""
import hashlib
import html
import re
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

import markdown as md
import requests

from . import config

AI_NOTE = "Written by AI (Claude) from the peer reviewed articles listed above. Check them before you act on it."
DISCLAIMER = "RetailMind AI is a student prototype (CBS International Business School). It is not an official REWE product."


class TelegramNotConnected(RuntimeError):
    """The person has not connected their Telegram chat to the bot yet."""


def linkedin_share_url(text: str) -> str:
    return "https://www.linkedin.com/feed/?shareActive=true&text=" + quote(text)


def _wrap(title: str, inner_html: str, manage_url: str = "") -> str:
    manage = f'<p style="margin:0 0 6px"><a href="{manage_url}" style="color:#5F6368">Manage your automations</a></p>' if manage_url else ""
    return f"""<div style="background:#f4f1ec;padding:24px 0;font-family:Arial,Helvetica,sans-serif">
<div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden">
<div style="background:#1f2a24;color:#ffffff;padding:18px 28px">
<div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#d9b36c">RetailMind AI</div>
<div style="font-size:19px;font-weight:bold;margin-top:4px">{html.escape(title)}</div></div>
<div style="padding:22px 28px;color:#222;font-size:15px;line-height:1.55">{inner_html}</div>
<div style="padding:14px 28px 20px;color:#5F6368;font-size:12px;border-top:1px solid #eee"><p style="margin:0 0 6px">{AI_NOTE}</p>{manage}{DISCLAIMER}</div>
</div></div>"""


def build_email(title: str, body: str, sources: list, fmt: str) -> tuple:
    """Returns (plain_text, html)."""
    src_html = "".join(
        f'<li style="margin-bottom:8px">{s["apa_html"]}</li>'
        for s in sources
    )
    src_text = "\n\n".join(s["apa"] for s in sources)
    manage_url = config.get("APP_URL")
    if fmt == "linkedin":
        post_html = html.escape(body).replace("\n", "<br>")
        inner = (
            '<p style="margin-top:0">Your LinkedIn post draft is ready. Read it, adjust it to your voice, then publish.</p>'
            f'<div style="border-left:4px solid #d9b36c;background:#faf7f1;padding:14px 18px;margin:14px 0">{post_html}</div>'
            f'<p><a href="{linkedin_share_url(body)}" style="background:#0a66c2;color:#fff;padding:10px 18px;'
            'border-radius:20px;text-decoration:none;font-weight:bold">Open in LinkedIn</a></p>'
            f'<h4 style="margin-bottom:6px">Based on (APA 7)</h4><ul style="padding-left:18px;font-size:13px;list-style:none">{src_html}</ul>'
        )
        plain = f"{body}\n\nBased on:\n{src_text}\n\n{AI_NOTE}\n{DISCLAIMER}"
    else:
        inner = md.markdown(body) + f'<h4 style="margin-bottom:6px">References (APA 7)</h4><ul style="padding-left:18px;font-size:13px;list-style:none">{src_html}</ul>'
        plain = f"{body}\n\nReferences (APA 7):\n{src_text}\n\n{AI_NOTE}\n{DISCLAIMER}"
    return plain, _wrap(title, inner, manage_url)


def send_email(to: str, subject: str, plain: str, html_body: str = "") -> str:
    host = config.get("SMTP_HOST", "smtp.gmail.com")
    port = int(config.get("SMTP_PORT", "465"))
    user = config.get("SMTP_USER")
    password = config.get("SMTP_PASSWORD").replace(" ", "")
    if not user or not password:
        raise RuntimeError("Email is not configured (SMTP_USER / SMTP_PASSWORD).")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"RetailMind AI <{user}>"
    msg["To"] = to
    msg.set_content(plain)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
    return f"Email sent to {to}"


def split_message(text: str, limit: int = 3500) -> list:
    parts, current = [], ""
    for para in text.split("\n"):
        while len(para) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(para[:limit])
            para = para[limit:]
        if len(current) + len(para) + 1 > limit:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current.strip():
        parts.append(current)
    return [p.strip("\n") for p in parts if p.strip()]


# ---------------- Telegram ----------------
def _tg(method: str, **params):
    token = config.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Telegram is not configured (TELEGRAM_BOT_TOKEN missing).")
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=30)
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"Telegram answered with status {r.status_code}.")
    if not data.get("ok"):
        raise RuntimeError(f"Telegram: {data.get('description', 'unknown error')}")
    return data["result"]


_BOT_NAME = {}


def bot_username() -> str:
    token = config.get("TELEGRAM_BOT_TOKEN")
    if token not in _BOT_NAME:
        _BOT_NAME[token] = _tg("getMe")["username"]
    return _BOT_NAME[token]


def connect_code(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]


def connect_link(email: str) -> str:
    return f"https://t.me/{bot_username()}?start={connect_code(email)}"


def find_chat_id(email: str) -> str:
    """Looks for the /start message this person sent to the bot after clicking their personal link."""
    code = connect_code(email)
    updates = _tg("getUpdates", limit=100, allowed_updates=["message"])
    for update in reversed(updates):
        message = update.get("message") or {}
        if (message.get("text") or "").strip() == f"/start {code}":
            return str(message["chat"]["id"])
    return ""


def _to_html(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return re.sub(r"\*(\S[^*\n]*?)\*", r"<b>\1</b>", escaped)


def send_telegram(chat_id: str, text: str) -> str:
    if not chat_id or not str(chat_id).lstrip("-").isdigit():
        raise TelegramNotConnected("Telegram is not connected yet. Connect it in the sidebar under Your profile.")
    parts = split_message(text)
    for part in parts:
        try:
            _tg("sendMessage", chat_id=chat_id, text=_to_html(part), parse_mode="HTML", disable_web_page_preview=True)
        except RuntimeError as exc:
            if "chat not found" in str(exc) or "blocked" in str(exc):
                raise TelegramNotConnected(
                    "Telegram could not reach this chat. Open the bot again, press Start and reconnect in the sidebar."
                )
            raise
    return f"Telegram message sent ({len(parts)} part{'s' if len(parts) > 1 else ''})"
