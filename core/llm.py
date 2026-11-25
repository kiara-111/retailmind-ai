"""All calls to the language model. The model only ever sees articles from the knowledge base."""
import json
import re
import threading
import time

from . import config, kb

FORMATS = {
    "report": "Research report",
    "insights": "Key insights briefing",
    "linkedin": "LinkedIn post draft",
}
CHANNELS = {"email": "Email", "telegram": "Telegram"}

GROUNDING = """You are RetailMind AI, a research assistant for senior marketing leaders at REWE Group, a German grocery retailer.
Your audience is experienced and short on time. Write in clear, precise business English.

Strict rules:
1. Use ONLY the articles inside <knowledge_base>. Never use other studies, numbers or facts from memory.
2. Never invent sources, effect sizes, sample sizes or revenue effects. If the knowledge base does not cover something, say so plainly.
3. Keep evidence and interpretation apart. What a study found is evidence. What it could mean for REWE is always a hypothesis and must be worded as one.
4. Mention relevant limitations instead of hiding them.
5. Do not use em dashes.
6. Refer to studies only through their article id in square brackets, e.g. [R03]. Never write author names or years yourself; they are inserted automatically in APA 7 format."""


def _client():
    import anthropic

    key = config.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=key)


_LOCAL = threading.local()


def last_usage() -> dict:
    """Tokens, model and duration of the most recent model call in this thread."""
    return dict(getattr(_LOCAL, "usage", {}))


def ask(system: str, messages: list, max_tokens: int = 1200) -> str:
    started = time.time()
    response = _client().messages.create(
        model=config.get("ANTHROPIC_MODEL", config.DEFAULT_MODEL),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    if getattr(response, "stop_reason", None) == "max_tokens":
        # The answer was cut off at the length limit: ask again once with a much larger budget.
        response = _client().messages.create(
            model=config.get("ANTHROPIC_MODEL", config.DEFAULT_MODEL),
            max_tokens=max(max_tokens * 4, 8000),
            system=system,
            messages=messages,
        )
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise RuntimeError("The answer was cut off at the length limit twice. Please try again.")
    usage = getattr(response, "usage", None)
    _LOCAL.usage = {
        "model": getattr(response, "model", None) or model_name(),
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "latency_ms": int((time.time() - started) * 1000),
    }
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
    if not text:
        kinds = ", ".join(getattr(b, "type", "?") for b in response.content) or "none"
        raise RuntimeError(f"The model returned no text (stop reason: {response.stop_reason}, content: {kinds}).")
    return text


def model_name() -> str:
    return config.get("ANTHROPIC_MODEL", config.DEFAULT_MODEL)


def clean(text: str) -> str:
    return text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").strip()


def cited_ids(text: str, allowed) -> list:
    found = re.findall(r"\[([A-Za-z]+\d+)\]", text)
    allowed = set(allowed)
    return [i for i in dict.fromkeys(found) if i in allowed]


# ---------- chat ----------
def answer_question(question: str, articles: list, history: list, guidance: str = "") -> str:
    system = (
        f"{GROUNDING}\n\n"
        + (f"{guidance}\n\n" if guidance else "")
        +
        "Answer the question. Cite every claim with the article id in square brackets, for example [R03]. "
        "If the knowledge base cannot answer the question, say that it is not covered and name the closest "
        "topic that is covered. Keep it under 220 words unless asked for more. "
        "End with one line starting with 'For REWE (hypothesis):'.\n\n"
        f"<knowledge_base>\n{kb.for_prompt(articles)}\n</knowledge_base>"
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
    messages.append({"role": "user", "content": question})
    return clean(ask(system, messages, max_tokens=900))


def answer_with_citations(question: str, articles: list, history: list, guidance: str = "", trace: dict = None) -> tuple:
    """Returns (answer with APA 7 in-text citations, cited article ids). Fills trace if given."""
    _LOCAL.usage = {}
    raw = answer_question(question, articles, history, guidance)
    stats = {}
    text, ids = kb.apply_citations(raw, [a["id"] for a in articles], stats)
    if trace is not None:
        trace.update(last_usage(), **stats, pool=len(articles), sources=ids)
    return text, ids


# ---------- scheduled content ----------
_TASKS = {
    ("report", "email"): (
        "Write a research report in Markdown, 350 to 450 words. Start with a one sentence headline as a level 2 heading. "
        "Then for each article one section with a level 3 heading naming the mechanism, answering in three short labelled "
        "paragraphs: **What is happening?** **Why does it work?** **What does it mean for REWE? (hypothesis)**. "
        "Cite with article ids in square brackets. Close with a section 'Limitations to keep in mind'."
    ),
    ("report", "telegram"): (
        "Write a research report for a Telegram message, at most 1800 characters, plain text. Use *single asterisks* for bold, no "
        "Markdown headings, no tables. One short block per article covering what is happening, why it works and what it "
        "could mean for REWE (marked as hypothesis). Cite every study with its article id in square brackets, for example [R03]."
    ),
    ("insights", "email"): (
        "Write a key insights briefing in Markdown, 150 to 200 words: a one line headline as a level 2 heading, then "
        "3 to 4 bullet points, each one finding with its article id in square brackets, then one line "
        "'**For REWE (hypothesis):**' and one line '**Caveat:**'."
    ),
    ("insights", "telegram"): (
        "Write a key insights briefing for a Telegram message, at most 900 characters, plain text, *single asterisks* for bold. "
        "3 bullet points starting with a dot character, then one line 'For REWE (hypothesis):' and one line 'Caveat:'. "
        "Cite every finding with its article id in square brackets, for example [R03]."
    ),
    ("linkedin", "any"): (
        "Write a LinkedIn post a senior marketing leader could publish under their own name, 120 to 170 words, first "
        "person, plain text without Markdown. Open with a concrete observation, explain the finding "
        "and the mechanism, cite the study once with its article id in square brackets, e.g. [R03], share one considered takeaway for grocery retail "
        "worded as a personal view, and end with a genuine question to the network. No hashtags inside the text, "
        "add 3 fitting hashtags on the last line. No emojis. Do not present REWE internal plans."
    ),
}


def generate(fmt: str, channel: str, topics: list, focus: list, user_name: str = "", trace: dict = None) -> str:
    task = _TASKS[("linkedin", "any")] if fmt == "linkedin" else _TASKS[(fmt, channel)]
    system = f"{GROUNDING}\n\n<knowledge_base>\n{kb.for_prompt(focus)}\n</knowledge_base>"
    user = (
        f"Reader: {user_name or 'a senior marketing leader'} at REWE.\n"
        f"Selected topics: {', '.join(topics) if topics else 'all topics'}.\n\n"
        f"{task}\n\nDo not add a list of sources at the end, it is attached automatically. Output only the text itself."
    )
    _LOCAL.usage = {}
    text = clean(ask(system, [{"role": "user", "content": user}], max_tokens=1400))
    stats = {}
    text = kb.apply_citations(text, [a["id"] for a in focus], stats)[0]
    if trace is not None:
        trace.update(last_usage(), **stats)
    return text


# ---------- natural language automation setup ----------
def parse_automation(text: str, available_topics: list) -> dict:
    system = (
        "You turn a request for a recurring delivery into JSON. Output ONLY a JSON object with these keys:\n"
        f'"topics": list, chosen only from {json.dumps(available_topics)} (empty list means all topics),\n'
        '"format": one of "report", "insights", "linkedin",\n'
        '"channel": one of "email", "telegram" (requests for Telegram, WhatsApp, messenger, chat or phone mean "telegram"; LinkedIn post drafts default to "email"),\n'
        '"freq_type": one of "daily", "every_n_days", "weekly",\n'
        '"interval_days": integer, only for every_n_days,\n'
        '"weekday": integer 0 to 6 where 0 is Monday, only for weekly,\n'
        '"hour": integer 0 to 23 in local time, default 8,\n'
        '"understood": false if the request is not about a recurring delivery, otherwise true.\n'
        "The request may be in English or German."
    )
    raw = ask(system, [{"role": "user", "content": text}], max_tokens=800)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("The request could not be interpreted.")
    return normalise(json.loads(match.group(0)), available_topics)


def normalise(d: dict, available_topics: list) -> dict:
    if d.get("understood") is False:
        raise ValueError("This does not look like a request for a recurring delivery.")
    fmt = d.get("format") if d.get("format") in FORMATS else "insights"
    channel = "telegram" if d.get("channel") == "whatsapp" else d.get("channel")
    channel = channel if channel in CHANNELS else "email"
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


# ---------- claim check
VERDICTS = {
    "supported": "Supported",
    "contradicted": "Contradicted",
    "mixed": "Mixed evidence",
    "no_evidence": "No evidence in dataset",
}

CLAIM_TASK = """A marketing leader states an assumption. Check it ONLY against the articles in <knowledge_base>.

Decide one verdict:
- "supported": at least one article directly supports the assumption and none clearly contradicts it
- "contradicted": the articles directly speak against it
- "mixed": some findings support it, others contradict it or show it only holds under conditions
- "no_evidence": no article addresses the assumption directly. Do not stretch loosely related findings.

Reply with JSON only, no other text:
{"verdict": "...",
 "summary": "two sentences on what the evidence says, citing article ids like [R05]",
 "evidence": [{"id": "R05", "finding": "one sentence on what this study found that supports the assumption"}],
 "counter_evidence": [{"id": "R12", "finding": "one sentence on what speaks against it or limits it"}],
 "for_rewe": "one sentence on what this could mean for REWE, worded as a hypothesis (empty if no_evidence)"}
Use at most 3 items per list. Use only ids that exist in the knowledge base."""


def check_claim(claim: str, articles: list, trace: dict = None) -> dict:
    """Checks a marketing assumption against the knowledge base. Never invents evidence."""
    _LOCAL.usage = {}
    system = f"{GROUNDING}\n\n<knowledge_base>\n{kb.for_prompt(articles)}\n</knowledge_base>"
    raw = ask(system, [{"role": "user", "content": f"{CLAIM_TASK}\n\nAssumption: {claim}"}], max_tokens=1200)
    match = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(match.group(0)) if match else {}
    allowed = {a["id"] for a in articles}

    def items(key):
        out = []
        for it in (data.get(key) or [])[:3]:
            if isinstance(it, dict) and it.get("id") in allowed and it.get("finding"):
                out.append({"id": it["id"], "finding": clean(kb.apply_citations(str(it["finding"]), allowed)[0])})
        return out

    evidence, counter = items("evidence"), items("counter_evidence")
    verdict = data.get("verdict") if data.get("verdict") in VERDICTS else "no_evidence"
    removed = 0
    if verdict != "no_evidence" and not (evidence or counter):
        verdict = "no_evidence"  # a verdict without a valid source is not accepted
    stats = {}
    summary = clean(kb.apply_citations(str(data.get("summary") or ""), allowed, stats)[0])
    removed += stats.get("citations_removed", 0)
    if verdict == "no_evidence":
        evidence, counter = [], []
        summary = summary or "None of the articles in the knowledge base addresses this assumption directly."
    ids = list(dict.fromkeys([e["id"] for e in evidence] + [c["id"] for c in counter]))
    result = {
        "verdict": verdict, "summary": summary, "evidence": evidence, "counter_evidence": counter,
        "for_rewe": clean(str(data.get("for_rewe") or "")) if verdict != "no_evidence" else "", "ids": ids,
    }
    if trace is not None:
        trace.update(last_usage(), pool=len(articles), sources=ids, citations_kept=len(ids), citations_removed=removed)
    return result


# ---------- structured briefings (layout is built in core/brief.py)
BRIEF_TASKS = {
    "report": """Write a research report for a senior marketing leader. Reply with JSON only:
{"headline": "the key message across all articles in one sentence, max 20 words",
 "lead": "3 to 4 sentences that back up the headline: what the studies together show and why it matters for grocery retail; cite with ids like [R05]",
 "sections": [{"id": "R05", "mechanism": "the psychological mechanism, 2 to 6 words",
               "what": "2 to 3 sentences: what the study found, with method or numbers if given",
               "why": "2 sentences: why it works psychologically",
               "rewe": "1 to 2 sentences: what it could mean for REWE, worded as a hypothesis"}],
 "takeaway": "2 sentences: the overall implication for REWE, worded as a hypothesis",
 "caveat": "1 to 2 sentences on the most important limitations",
 "options": [{"title": "short name of a concrete measure, 3 to 6 words",
              "action": "1 to 2 sentences: what exactly the team would do in stores, online or in communication",
              "effort": "low, medium or high",
              "owner": "the team that would typically own it, e.g. Category management, Pricing, CRM, Store operations, Brand marketing",
              "measure": "the one KPI that shows whether it works, e.g. unit sales, basket size, redemption rate",
              "based_on": ["R05"]}],
 "start_with": "1 to 2 sentences: which option to try first and why (effort versus strength of evidence)",
 "decide_by": "1 to 2 sentences: a simple pilot design and the rule for scaling or stopping, e.g. test stores versus control stores for 4 to 6 weeks"}
Write exactly one section per article, in the order given, and 3 options. Each option must follow from at least one
article and name it in based_on. Options are ideas to test, never proven results. About 650 to 850 words in total.""",
    "insights": """Write a key insights briefing for a senior marketing leader. Reply with JSON only:
{"headline": "the key message in one sentence, max 18 words",
 "lead": "2 to 3 sentences that back up the headline; cite with ids like [R05]",
 "bullets": [{"id": "R05", "text": "one finding in 1 to 2 sentences, concrete, with a number if the summary gives one"}],
 "takeaway": "1 to 2 sentences for REWE, worded as a hypothesis",
 "caveat": "1 sentence on the main limitation",
 "options": [{"title": "short name of a concrete measure, 3 to 6 words",
              "action": "1 to 2 sentences: what exactly the team would do in stores, online or in communication",
              "effort": "low, medium or high",
              "owner": "the team that would typically own it, e.g. Category management, Pricing, CRM, Store operations, Brand marketing",
              "measure": "the one KPI that shows whether it works, e.g. unit sales, basket size, redemption rate",
              "based_on": ["R05"]}],
 "start_with": "1 to 2 sentences: which option to try first and why (effort versus strength of evidence)",
 "decide_by": "1 to 2 sentences: a simple pilot design and the rule for scaling or stopping, e.g. test stores versus control stores for 4 to 6 weeks"}
3 to 4 bullets, each based on one of the articles, and 2 options that follow from them. About 300 to 380 words in total.""",
}


def generate_brief(fmt: str, topics: list, focus: list, user_name: str = "", trace: dict = None) -> dict:
    """Structured report or insights briefing. Every id is checked against the selected articles."""
    allowed = [a["id"] for a in focus]
    system = f"{GROUNDING}\n\n<knowledge_base>\n{kb.for_prompt(focus)}\n</knowledge_base>"
    user = (f"Reader: {user_name or 'a senior marketing leader'} at REWE.\n"
            f"Selected topics: {', '.join(topics) if topics else 'all topics'}.\n"
            f"Articles in order: {', '.join(allowed)}.\n\n{BRIEF_TASKS[fmt]}")
    _LOCAL.usage = {}
    raw = ask(system, [{"role": "user", "content": user}], max_tokens=4000)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise RuntimeError("The briefing could not be read (no JSON).")
    data = json.loads(match.group(0))
    stats = {"citations_kept": 0, "citations_removed": 0}

    def txt(value, own=None):
        s = {}
        raw_text = str(value or "")
        if own:  # the block already names its own source in small print, so drop the inline repeat
            raw_text = re.sub(rf"\s*\[{own}\]", "", raw_text)
        out = clean(kb.apply_citations(clean(raw_text), allowed, s)[0])
        stats["citations_removed"] += s.get("citations_removed", 0)
        return out

    brief = {"kind": fmt, "headline": txt(data.get("headline")), "lead": txt(data.get("lead")),
             "takeaway": txt(data.get("takeaway")), "caveat": txt(data.get("caveat")), "sections": [], "bullets": []}
    for s in data.get("sections") or []:
        if isinstance(s, dict) and s.get("id") in allowed:
            brief["sections"].append({"id": s["id"], "mechanism": txt(s.get("mechanism"), s["id"]),
                                      "what": txt(s.get("what"), s["id"]), "why": txt(s.get("why"), s["id"]),
                                      "rewe": txt(s.get("rewe"), s["id"])})
        elif isinstance(s, dict):
            stats["citations_removed"] += 1
    for x in data.get("bullets") or []:
        if isinstance(x, dict) and x.get("id") in allowed:
            brief["bullets"].append({"id": x["id"], "text": txt(x.get("text"), x["id"])})
        elif isinstance(x, dict):
            stats["citations_removed"] += 1
    brief["options"] = []
    for o in data.get("options") or []:
        if not isinstance(o, dict):
            continue
        based = [i for i in (o.get("based_on") or []) if i in allowed]
        if not based:  # an option without a valid source is dropped, like any other unsupported claim
            stats["citations_removed"] += 1
            continue
        effort = str(o.get("effort", "")).strip().lower()
        brief["options"].append({"title": txt(o.get("title")), "action": txt(o.get("action")),
                                 "effort": effort if effort in ("low", "medium", "high") else "medium",
                                 "owner": txt(o.get("owner")), "measure": txt(o.get("measure")), "based_on": based})
    brief["start_with"] = txt(data.get("start_with")) if brief["options"] else ""
    brief["decide_by"] = txt(data.get("decide_by")) if brief["options"] else ""
    if not brief["headline"] or not (brief["sections"] or brief["bullets"]):
        raise RuntimeError("The briefing was incomplete.")
    used = {s["id"] for s in brief["sections"]} | {x["id"] for x in brief["bullets"]}
    stats["citations_kept"] = len(used)
    if trace is not None:
        trace.update(last_usage(), **stats)
    return brief
