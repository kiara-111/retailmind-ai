"""Evaluation and the feedback loop.

The language model itself is not retrained. Instead the system learns in three ways:
1. Highly rated answers become examples the model sees before answering (few-shot learning).
2. Frequent criticism (tags) becomes explicit style rules in the prompt.
3. Questions the knowledge base could not answer are listed as gaps for the team.
All rated question-answer pairs can be exported as a dataset for evaluation or later fine-tuning.
"""
import json
import re
from collections import Counter

from . import kb, store

TAGS = ["Accurate", "Useful for REWE", "Clear", "Too long", "Too short", "Too general",
        "Missing evidence", "Hypothesis not marked", "Factually doubtful"]
NEGATIVE = {"Too long", "Too short", "Too general", "Missing evidence", "Hypothesis not marked", "Factually doubtful"}

NOT_COVERED = re.compile(r"\b(not covered|does not cover|doesn't cover|isn't covered|no article|cannot answer|not in the knowledge base)\b", re.I)

RULES = {
    "Too long": "Readers often found answers too long. Be more concise than you think is necessary.",
    "Too short": "Readers often wanted more depth. Add one more concrete detail per finding.",
    "Too general": "Readers often found answers too general. Name the concrete mechanism, number and context of each study.",
    "Missing evidence": "Readers asked for more evidence. Cite an article for every single claim.",
    "Hypothesis not marked": "Readers noticed unmarked interpretations. Label every implication for REWE explicitly as a hypothesis.",
    "Factually doubtful": "Readers doubted some facts. Stay strictly with what the article summaries say.",
}


def metrics(answer: str, cited: list) -> dict:
    return {
        "answer_words": len(answer.split()),
        "n_citations": len(cited),
        "not_covered": bool(NOT_COVERED.search(answer)),
    }


def topics_of(ids) -> list:
    lookup = kb.by_id()
    return sorted({lookup[i]["topic"] for i in ids if i in lookup})


# ---------------------------------------------------------------- learning from feedback
def learned_guidance(rows=None, max_examples: int = 2) -> dict:
    """What the model currently learns from ratings: example answers and style rules."""
    rows = rows if rows is not None else _safe_rows()
    rated = [r for r in rows if r.get("rating") and r.get("kind") == "chat"]
    examples = [r for r in rated if r["rating"] >= 4 and not set(r.get("tags") or []) & NEGATIVE]
    examples = examples[:max_examples]  # rows are newest first
    counts = Counter(t for r in rated[:50] for t in (r.get("tags") or []))
    rules = [RULES[t] for t, n in counts.items() if t in RULES and n >= 2]
    if counts["Too long"] >= 2 and counts["Too short"] >= 2:
        rules = [r for r in rules if not r.startswith(("Readers often found answers too long", "Readers often wanted more depth"))]
    return {"examples": examples, "rules": rules, "n_rated": len(rated)}


def guidance_prompt(guidance: dict) -> str:
    parts = []
    if guidance["rules"]:
        parts.append("Feedback from readers so far:\n- " + "\n- ".join(guidance["rules"]))
    if guidance["examples"]:
        blocks = []
        for ex in guidance["examples"]:
            blocks.append(f"<example>\nQuestion: {ex['question']}\nHighly rated answer: {ex['answer']}\n</example>")
        parts.append(
            "Answers that readers rated highly. Match their style, structure and depth. "
            "Do not reuse their content unless the knowledge base below supports it:\n" + "\n".join(blocks)
        )
    return "\n\n".join(parts)


def _safe_rows():
    try:
        return store.list_interactions(200)
    except Exception:
        return []


# ---------------------------------------------------------------- automatic evaluation
JUDGE = """You check answers of a research assistant for grounding. You receive the article summaries that were
available and the answer. Score 1 to 5:
5 = every claim is supported by the summaries and implications are marked as hypotheses
4 = supported, minor imprecision
3 = mostly supported, one claim goes beyond the summaries or an implication is not marked
2 = several unsupported claims
1 = largely unsupported or contradicts the summaries
If the answer says the topic is not covered and that is true, score 5.
Reply with JSON only: {"score": <1-5>, "reason": "<one sentence>"}"""


def auto_evaluate(row: dict, ask) -> dict:
    ids = row.get("cited_ids") or []
    lookup = kb.by_id()
    articles = [lookup[i] for i in ids if i in lookup]
    context = kb.for_prompt(articles) if articles else "(no articles were cited)"
    user = f"<articles>\n{context}\n</articles>\n\nQuestion: {row.get('question') or '(scheduled briefing)'}\n\nAnswer:\n{row.get('answer')}"
    raw = ask(JUDGE, [{"role": "user", "content": user}], 300)
    match = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(match.group(0)) if match else {}
    score = max(1, min(5, int(data.get("score", 0) or 0))) if data.get("score") else None
    return {"auto_score": score, "auto_reason": str(data.get("reason", ""))[:300]}


# ---------------------------------------------------------------- export
def export_jsonl(rows) -> str:
    """Rated interactions in the chat-message format used for evaluation sets and fine-tuning."""
    lines = []
    for r in rows:
        if not r.get("rating"):
            continue
        lines.append(json.dumps({
            "messages": [
                {"role": "user", "content": r.get("question") or f"Scheduled {r.get('format')} on {', '.join(r.get('topics') or []) or 'all topics'}"},
                {"role": "assistant", "content": r.get("answer") or ""},
            ],
            "rating": r.get("rating"),
            "tags": r.get("tags") or [],
            "comment": r.get("comment") or "",
            "auto_score": r.get("auto_score"),
            "cited_ids": r.get("cited_ids") or [],
            "kind": r.get("kind"),
            "created_at": r.get("created_at"),
        }, ensure_ascii=False))
    return "\n".join(lines)
