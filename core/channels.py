"""Delivery channels: email over SMTP and WhatsApp over the Twilio API."""
import html
import re
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

import markdown as md
import requests

from . import config

DISCLAIMER = "RetailMind AI is a student prototype (CBS International Business School). It is not an official REWE product."


class WhatsAppWindowClosed(RuntimeError):
    """The recipient has not written to the sandbox number within the last 24 hours."""


def linkedin_share_url(text: str) -> str:
    return "https://www.linkedin.com/feed/?shareActive=true&text=" + quote(text)


def _wrap(title: str, inner_html: str, manage_url: str = "") -> str:
    manage = f'<p style="margin:0 0 6px"><a href="{manage_url}" style="color:#666">Manage your automations</a></p>' if manage_url else ""
    return f"""<div style="background:#f4f1ec;padding:24px 0;font-family:Arial,Helvetica,sans-serif">
<div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden">
<div style="background:#1f2a24;color:#ffffff;padding:18px 28px">
<div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#d9b36c">RetailMind AI</div>
<div style="font-size:19px;font-weight:bold;margin-top:4px">{html.escape(title)}</div></div>
<div style="padding:22px 28px;color:#222;font-size:15px;line-height:1.55">{inner_html}</div>
<div style="padding:14px 28px 20px;color:#777;font-size:12px;border-top:1px solid #eee">{manage}{DISCLAIMER}</div>
</div></div>"""


def build_email(title: str, body: str, sources: list, fmt: str) -> tuple:
    """Returns (plain_text, html)."""
    src_html = "".join(
        f'<li style="margin-bottom:6px">{html.escape(s["ref"])}'
        + (f' <a href="{s["url"]}">{html.escape(s["url"])}</a>' if s["url"] else "")
        + "</li>"
        for s in sources
    )
    src_text = "\n".join(f"- {s['ref']} {s['url']}".strip() for s in sources)
    manage_url = config.get("APP_URL")
    if fmt == "linkedin":
        post_html = html.escape(body).replace("\n", "<br>")
        inner = (
            '<p style="margin-top:0">Your LinkedIn post draft is ready. Read it, adjust it to your voice, then publish.</p>'
            f'<div style="border-left:4px solid #d9b36c;background:#faf7f1;padding:14px 18px;margin:14px 0">{post_html}</div>'
            f'<p><a href="{linkedin_share_url(body)}" style="background:#0a66c2;color:#fff;padding:10px 18px;'
            'border-radius:20px;text-decoration:none;font-weight:bold">Open in LinkedIn</a></p>'
            f'<h4 style="margin-bottom:6px">Based on</h4><ul style="padding-left:18px;font-size:13px">{src_html}</ul>'
        )
        plain = f"{body}\n\nBased on:\n{src_text}\n\n{DISCLAIMER}"
    else:
        inner = md.markdown(body) + f'<h4 style="margin-bottom:6px">Sources</h4><ul style="padding-left:18px;font-size:13px">{src_html}</ul>'
        plain = f"{body}\n\nSources:\n{src_text}\n\n{DISCLAIMER}"
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


def normalise_phone(number: str) -> str:
    digits = re.sub(r"[^\d+]", "", number or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+49" + digits[1:]
    elif digits and not digits.startswith("+"):
        digits = "+" + digits
    return digits


def split_message(text: str, limit: int = 1500) -> list:
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


def send_whatsapp(to: str, text: str) -> str:
    sid = config.get("TWILIO_ACCOUNT_SID")
    token = config.get("TWILIO_AUTH_TOKEN")
    sender = config.get("TWILIO_WHATSAPP_FROM", "+14155238886")
    if not sid or not token:
        raise RuntimeError("WhatsApp is not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN).")
    number = normalise_phone(to)
    if len(number) < 8:
        raise RuntimeError("No valid WhatsApp number in your profile.")
    parts = split_message(text)
    for part in parts:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"From": f"whatsapp:{normalise_phone(sender)}", "To": f"whatsapp:{number}", "Body": part},
            timeout=30,
        )
        if r.status_code >= 300:
            try:
                data = r.json()
                reason, code = data.get("message", r.text), data.get("code")
            except Exception:
                reason, code = r.text, None
            if "ContentSid" in reason or code in (63016, 21656):
                raise WhatsAppWindowClosed(
                    "WhatsApp only allows messages within 24 hours after you last wrote to the RetailMind number. "
                    f"Send any WhatsApp message (for example 'Hi') to {normalise_phone(sender)} and try again."
                )
            raise RuntimeError(f"Twilio {r.status_code}: {reason[:250]}")
    return f"WhatsApp accepted by Twilio for {number} ({len(parts)} message{'s' if len(parts) > 1 else ''})"
