"""Runs one automation: pick articles, let the model write, deliver, log."""
from . import channels, kb, llm, schedule, store

FOCUS_COUNT = {"report": 3, "insights": 2, "linkedin": 1}


def pick_focus(sub: dict) -> tuple:
    """Rotates through the fixed knowledge base so every issue covers different articles."""
    pool = kb.by_topics(sub.get("topics") or [])
    if not pool:
        raise RuntimeError("No articles in the knowledge base for the selected topics.")
    n = min(FOCUS_COUNT.get(sub["format"], 2), len(pool))
    covered = [i for i in (sub.get("covered_ids") or []) if i in {a["id"] for a in pool}]
    fresh = [a for a in pool if a["id"] not in covered]
    if len(fresh) < n:  # end of a cycle: finish the remaining articles, then start again from the top
        refill = [a for a in pool if a not in fresh][: n - len(fresh)]
        focus = fresh + refill
        return focus, [a["id"] for a in refill]
    focus = fresh[:n]
    return focus, covered + [a["id"] for a in focus]


def title_for(sub: dict) -> str:
    topics = sub.get("topics") or []
    scope = ", ".join(topics) if topics else "Consumer psychology"
    return f"{llm.FORMATS[sub['format']]}: {scope}"


def compose(sub: dict) -> dict:
    focus, covered = pick_focus(sub)
    body = llm.generate(sub["format"], sub["channel"], sub.get("topics") or [], focus, sub.get("user_name", ""))
    sources = [{"id": a["id"], "ref": kb.reference(a).replace(kb.doi_url(a), "").strip(), "url": kb.doi_url(a),
                "short": f"{kb.short_cite(a)}, {a['journal']}"} for a in focus]
    return {"body": body, "sources": sources, "covered": covered, "title": title_for(sub)}


def deliver(sub: dict, piece: dict) -> str:
    if sub["channel"] in ("telegram", "whatsapp"):  # "whatsapp" only for automations created before the switch
        label = "Based on" if sub["format"] == "linkedin" else "Sources"
        lines = "\n".join(f"{s['short']} {s['url']}".strip() for s in piece["sources"])
        head = "*RetailMind AI*\n" + ("Your LinkedIn post draft\n\n" if sub["format"] == "linkedin" else "\n")
        try:
            # the database column is still called "whatsapp"; it now holds the Telegram chat id
            return channels.send_telegram(sub.get("whatsapp", ""), f"{head}{piece['body']}\n\n*{label}*\n{lines}")
        except channels.TelegramNotConnected as exc:
            note = (
                "This was meant for Telegram, but your Telegram is not connected. "
                "Connect it in the RetailMind app under Your profile to receive the next issue there.\n\n"
            )
            plain, html_body = channels.build_email(piece["title"], note + piece["body"], piece["sources"], sub["format"])
            channels.send_email(sub["email"], f"RetailMind AI | {piece['title']}", plain, html_body)
            return f"Telegram not connected, delivered by email instead. ({exc})"
    plain, html_body = channels.build_email(piece["title"], piece["body"], piece["sources"], sub["format"])
    return channels.send_email(sub["email"], f"RetailMind AI | {piece['title']}", plain, html_body)


def run(sub: dict, trigger: str = "schedule") -> dict:
    """trigger is 'schedule' (moves the schedule forward) or 'manual' (Send now button)."""
    piece, status, detail = None, "sent", ""
    try:
        piece = compose(sub)
        detail = deliver(sub, piece)
    except Exception as exc:  # one failing automation must not stop the others
        status, detail = "failed", str(exc)[:400]

    changes = {}
    if status == "sent":
        changes["covered_ids"] = piece["covered"]
        changes["last_run_at"] = schedule.iso(schedule.now_utc())
    if trigger == "schedule":
        changes["next_run_at"] = schedule.iso(schedule.next_run(sub))
    if changes and sub.get("id"):
        store.update_subscription(sub["id"], changes)
    try:
        store.log_delivery({
            "subscription_id": sub.get("id"), "email": sub["email"], "channel": sub["channel"],
            "format": sub["format"], "topics": sub.get("topics") or [], "trigger": trigger,
            "status": status, "detail": detail, "content": piece["body"] if piece else "",
        })
    except Exception as exc:
        detail += f" (log failed: {exc})"
    return {"status": status, "detail": detail, "piece": piece}
