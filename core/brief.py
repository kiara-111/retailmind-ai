"""Turns a structured briefing (headline, lead, sections, bottom line) into email HTML, plain text,
Telegram text and Markdown for the app. The model writes the content, this module owns the layout."""
import html
import math

from . import kb

# Email palette (inline styles; contrast against white checked: text 16.4:1, muted 6.0:1, accent 6.1:1)
INK, MUTED, ACCENT = "#1B1F1C", "#5F6368", "#1F6F4A"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _cite(a_id: str) -> str:
    a = kb.by_id().get(a_id)
    return kb.intext(a) if a else ""


def _source_line(a_id: str) -> str:
    a = kb.by_id().get(a_id)
    return f"{kb.intext(a)} · {a['journal']}" if a else ""


def words(b: dict) -> int:
    parts = [b.get("headline", ""), b.get("lead", ""), b.get("takeaway", ""), b.get("caveat", "")]
    parts += [s.get(k, "") for s in b.get("sections", []) for k in ("what", "why", "rewe")]
    parts += [x.get("text", "") for x in b.get("bullets", [])]
    return len(" ".join(parts).split())


def reading_minutes(b: dict) -> int:
    return max(1, math.ceil(words(b) / 220))


# ---------------------------------------------------------------- Markdown (app, delivery log)
def to_markdown(b: dict) -> str:
    out = [f"## {b['headline']}", "", b["lead"], ""]
    for s in b.get("sections", []):
        out += [f"### {s['mechanism']}", "", f"**What is happening?** {s['what']}", "",
                f"**Why does it work?** {s['why']}", "", f"**For REWE (hypothesis):** {s['rewe']}", "",
                f"*Source: {_source_line(s['id'])}*", ""]
    for x in b.get("bullets", []):
        out.append(f"- {x['text']} ({_cite(x['id'])})")
    if b.get("bullets"):
        out.append("")
    if b.get("takeaway"):
        out += [f"**Bottom line (hypothesis):** {b['takeaway']}", ""]
    if b.get("caveat"):
        out += [f"*Keep in mind: {b['caveat']}*"]
    return "\n".join(out).strip()


# ---------------------------------------------------------------- plain text email part
def to_plain(b: dict) -> str:
    out = [b["headline"].upper(), "", b["lead"], ""]
    for s in b.get("sections", []):
        out += [s["mechanism"].upper(), f"What is happening? {s['what']}", f"Why does it work? {s['why']}",
                f"For REWE (hypothesis): {s['rewe']}", f"Source: {_source_line(s['id'])}", ""]
    for x in b.get("bullets", []):
        out.append(f"- {x['text']} ({_cite(x['id'])})")
    if b.get("takeaway"):
        out += ["", f"BOTTOM LINE (hypothesis): {b['takeaway']}"]
    if b.get("caveat"):
        out += [f"Keep in mind: {b['caveat']}"]
    return "\n".join(out).strip()


# ---------------------------------------------------------------- Telegram
def to_telegram(b: dict) -> str:
    out = [f"*{b['headline']}*", "", b["lead"], ""]
    for s in b.get("sections", []):
        out += [f"*{s['mechanism']}*", f"{s['what']} {s['why']}", f"For REWE (hypothesis): {s['rewe']}",
                f"Source: {_cite(s['id'])}", ""]
    for x in b.get("bullets", []):
        out.append(f"• {x['text']} ({_cite(x['id'])})")
    if b.get("takeaway"):
        out += ["", f"*Bottom line (hypothesis):* {b['takeaway']}"]
    if b.get("caveat"):
        out += [f"Keep in mind: {b['caveat']}"]
    return "\n".join(out).strip()


# ---------------------------------------------------------------- email HTML
def _p(text: str, size: int = 15, color: str = INK, extra: str = "") -> str:
    return (f'<p style="margin:0 0 12px;font-size:{size}px;line-height:1.6;color:{color};{extra}">'
            f"{html.escape(text, quote=False)}</p>")


def _label(text: str) -> str:
    return (f'<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};'
            f'font-weight:600;margin:0 0 4px">{html.escape(text)}</div>')


def to_email_html(b: dict, topics: list, sources: list) -> str:
    """Inner HTML of the email body (the header and footer frame is added by channels._wrap)."""
    n = len(sources)
    meta = (f"{n} peer reviewed stud{'y' if n == 1 else 'ies'} · {html.escape(', '.join(topics) or 'All topics')}"
            f" · about {reading_minutes(b)} min read")
    parts = [
        f'<div style="font-size:12px;color:{MUTED};margin:0 0 14px">{meta}</div>',
        f'<h1 style="margin:0 0 14px;font-size:24px;line-height:1.3;color:{INK};font-weight:700">'
        f"{html.escape(b['headline'], quote=False)}</h1>",
        _p(b["lead"], 16, INK),
    ]
    for i, s in enumerate(b.get("sections", []), 1):
        parts.append(
            f'<div style="margin:22px 0 0;padding:18px 20px;border:1px solid #E3E7E4;border-left:4px solid {ACCENT};'
            f'border-radius:10px;background:#FFFFFF">'
            f'<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{ACCENT};font-weight:700;'
            f'margin:0 0 6px">Finding {i}</div>'
            f'<h2 style="margin:0 0 12px;font-size:18px;line-height:1.35;color:{INK}">{html.escape(s["mechanism"])}</h2>'
            f'{_label("What is happening")}{_p(s["what"], 15)}'
            f'{_label("Why it works")}{_p(s["why"], 15)}'
            f'<div style="margin:6px 0 10px;padding:10px 14px;border:1.5px dashed #C08A14;border-radius:8px;'
            f'background:#FFF8E8">{_label("For REWE · hypothesis")}{_p(s["rewe"], 15, INK, "margin:0")}</div>'
            f'<div style="font-size:12px;color:{MUTED}">Source: {html.escape(_source_line(s["id"]))}</div>'
            f"</div>"
        )
    if b.get("bullets"):
        items = "".join(
            f'<li style="margin:0 0 10px;font-size:15px;line-height:1.6;color:{INK}">{html.escape(x["text"], quote=False)}'
            f' <span style="font-size:12px;color:{MUTED}">({html.escape(_cite(x["id"]))})</span></li>'
            for x in b["bullets"])
        parts.append(f'<ul style="margin:18px 0 0;padding-left:20px">{items}</ul>')
    if b.get("takeaway"):
        parts.append(
            f'<div style="margin:24px 0 0;padding:16px 20px;border-radius:10px;background:#EEF5F0">'
            f'<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{ACCENT};font-weight:700;'
            f'margin:0 0 6px">Bottom line · hypothesis</div>{_p(b["takeaway"], 16, INK, "margin:0;font-weight:600")}</div>')
    if b.get("caveat"):
        parts.append(_p(f"Keep in mind: {b['caveat']}", 13, MUTED, "margin:16px 0 0;font-style:italic"))
    refs = "".join(f'<div style="margin:0 0 6px">{s["apa_html"]}</div>' for s in sources)
    parts.append(
        f'<div style="margin:28px 0 0;padding:14px 0 0;border-top:1px solid #E3E7E4;font-size:11px;line-height:1.5;'
        f'color:{MUTED}"><div style="font-weight:600;margin:0 0 6px">References (APA 7)</div>{refs}</div>')
    return f'<div style="font-family:{FONT}">' + "".join(parts) + "</div>"
