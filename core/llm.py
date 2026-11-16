"""All calls to the language model. The model only ever sees articles from the knowledge base."""
import json
import re

from . import config, kb

FORMATS = {
    "report": "Research report",
    "insights": "Key insights briefing",
    "linkedin": "LinkedIn post draft",
}
CHANNELS = {"email": "Email", "whatsapp": "WhatsApp"}

GROUNDING = """You are RetailMind AI, a research assistant for senior marketing leaders at REWE Group, a German grocery retailer.
Your audience is experienced and short on time. Write in clear, precise business English.

Strict rules:
1. Use ONLY the articles inside <knowledge_base>. Never use other studies, numbers or facts from memory.
2. Never invent sources, effect sizes, sample sizes or revenue effects. If the knowledge base does not cover something, say so plainly.
3. Keep evidence and interpretation apart. What a study found is evidence. What it could mean for REWE is always a hypothesis and must be worded as one.
4. Mention relevant limitations instead of hiding them.
5. Do not use em dashes."""


def _client():
    import anthropic

    key = config.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=key)


def ask(system: str, messages: list, max_tokens: int = 1200) -> str:
    response = _client().messages.create(
        model=config.get("ANTHROPIC_MODEL", config.DEFAULT_MODEL),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()


def clean(text: str) -> str:
    return text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").strip()


def cited_ids(text: str, allowed) -> list:
    found = re.findall(r"\[([A-Za-z]+\d+)\]", text)
    allowed = set(allowed)
    return [i for i in dict.fromkeys(found) if i in allowed]


# ---------- chat ----------
def answer_question(question: str, articles: list, history: list) -> str:
    system = (
        f"{GROUNDING}\n\n"
        "Answer the question. Cite every claim with the article id in square brackets, for example [R03]. "
        "If the knowledge base cannot answer the question, say that it is not covered and name the closest "
        "topic that is covered. Keep it under 220 words unless asked for more. "
        "End with one line starting with 'For REWE (hypothesis):'.\n\n"
        f"<knowledge_base>\n{kb.for_prompt(articles)}\n</knowledge_base>"
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
    messages.append({"role": "user", "content": question})
    return clean(ask(system, messages, max_tokens=900))


# ---------- scheduled content ----------
_TASKS = {
    ("report", "email"): (
        "Write a research report in Markdown, 350 to 450 words. Start with a one sentence headline as a level 2 heading. "
        "Then for each article one section with a level 3 heading naming the mechanism, answering in three short labelled "
        "paragraphs: **What is happening?** **Why does it work?** **What does it mean for REWE? (hypothesis)**. "
        "Cite with article ids in square brackets. Close with a section 'Limitations to keep in mind'."
    ),
    ("report", "whatsapp"): (
        "Write a research report for WhatsApp, at most 1100 characters, plain text. Use *single asterisks* for bold, no "
        "Markdown headings, no tables. One short block per article covering what is happening, why it works and what it "
        "could mean for REWE (marked as hypothesis). Refer to studies as Author (Year), not with ids."
    ),
    ("insights", "email"): (
        "Write a key insights briefing in Markdown, 150 to 200 words: a one line headline as a level 2 heading, then "
        "3 to 4 bullet points, each one finding with its article id in square brackets, then one line "
        "'**For REWE (hypothesis):**' and one line '**Caveat:**'."
    ),
    ("insights", "whatsapp"): (
        "Write a key insights briefing for WhatsApp, at most 700 characters, plain text, *single asterisks* for bold. "
        "3 bullet points starting with a dot character, then one line 'For REWE (hypothesis):' and one line 'Caveat:'. "
        "Refer to studies as Author (Year)."
    ),
    ("linkedin", "any"): (
        "Write a LinkedIn post a senior marketing leader could publish under their own name, 120 to 170 words, first "
        "person, plain text without Markdown and without ids. Open with a concrete observation, explain the finding "
        "and the mechanism, refer to the study as Author (Year), share one considered takeaway for grocery retail "
        "worded as a personal view, and end with a genuine question to the network. No hashtags inside the text, "
        "add 3 fitting hashtags on the last line. No emojis. Do not present REWE internal plans."
    ),
}


def generate(fmt: str, channel: str, topics: list, focus: list, user_name: str = "") -> str:
    task = _TASKS[("linkedin", "any")] if fmt == "linkedin" else _TASKS[(fmt, channel)]
    system = f"{GROUNDING}\n\n<knowledge_base>\n{kb.for_prompt(focus)}\n</knowledge_base>"
    user = (
        f"Reader: {user_name or 'a senior marketing leader'} at REWE.\n"
        f"Selected topics: {', '.join(topics) if topics else 'all topics'}.\n\n"
        f"{task}\n\nDo not add a list of sources at the end, it is attached automatically. Output only the text itself."
    )
    return clean(ask(system, [{"role": "user", "content": user}], max_tokens=1400))


# ---------- natural language automation setup ----------
def parse_automation(text: str, available_topics: list) -> dict:
    system = (
        "You turn a request for a recurring delivery into JSON. Output ONLY a JSON object with these keys:\n"
        f'"topics": list, chosen only from {json.dumps(available_topics)} (empty list means all topics),\n'
        '"format": one of "report", "insights", "linkedin",\n'
        '"channel": one of "email", "whatsapp" (LinkedIn post drafts default to "email"),\n'
        '"freq_type": one of "daily", "every_n_days", "weekly",\n'
        '"interval_days": integer, only for every_n_days,\n'
        '"weekday": integer 0 to 6 where 0 is Monday, only for weekly,\n'
        '"hour": integer 0 to 23 in local time, default 8,\n'
        '"understood": false if the request is not about a recurring delivery, otherwise true.\n'
        "The request may be in English or German."
    )
    raw = ask(system, [{"role": "user", "content": text}], max_tokens=300)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("The request could not be interpreted.")
    return normalise(json.loads(match.group(0)), available_topics)


def normalise(d: dict, available_topics: list) -> dict:
    if d.get("understood") is False:
        raise ValueError("This does not look like a request for a recurring delivery.")
    fmt = d.get("format") if d.get("format") in FORMATS else "insights"
    channel = d.get("channel") if d.get("channel") in CHANNELS else "email"
    freq = d.get("freq_type") if d.get("freq_type") in ("daily", "every_n_days", "weekly") else "weekly"

    def _int(value, default, low, high):
        try:
            return min(high, max(low, int(value)))
        except (TypeError, ValueError):
            return default

    return {
        "topics": [t for t in (d.get("topics") or []) if t in available_topics],
        "format": fmt,
        "channel": channel,
        "freq_type": freq,
        "interval_days": _int(d.get("interval_days"), 3, 1, 60) if freq == "every_n_days" else None,
        "weekday": _int(d.get("weekday"), 0, 0, 6) if freq == "weekly" else None,
        "hour": _int(d.get("hour"), 8, 0, 23),
    }
