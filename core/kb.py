"""Knowledge base: reads the curated, peer reviewed articles from knowledge_base.xlsx."""
import os
import re
from functools import lru_cache

from openpyxl import load_workbook

KB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base.xlsx")

COLUMNS = {
    "id": "ID",
    "topic": "Topic",
    "title": "Title",
    "authors": "Authors",
    "year": "Year",
    "journal": "Journal",
    "doi": "DOI",
    "mechanism": "Mechanism",
    "findings": "Key findings",
    "method": "Method and sample",
    "limitations": "Limitations",
    "relevance": "Relevance for REWE (hypothesis)",
    "checked_by": "Checked by",
}


@lru_cache(maxsize=1)
def _load(mtime: float):
    wb = load_workbook(KB_PATH, read_only=True, data_only=True)
    ws = wb["Articles"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h).strip() if h else "" for h in rows[0]]
    idx = {key: header.index(label) for key, label in COLUMNS.items() if label in header}
    missing = [label for key, label in COLUMNS.items() if key not in idx]
    if missing:
        raise ValueError(f"knowledge_base.xlsx is missing columns: {', '.join(missing)}")
    articles = []
    for row in rows[1:]:
        if not row or not row[idx["id"]] or not row[idx["title"]]:
            continue
        a = {k: ("" if row[i] is None else str(row[i]).strip()) for k, i in idx.items()}
        a["year"] = a["year"].split(".")[0]
        a["doi"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", a["doi"])
        a["checked"] = bool(a["checked_by"]) and "not" not in a["checked_by"].lower()
        articles.append(a)
    wb.close()
    return tuple(articles)


def articles() -> list:
    return list(_load(os.path.getmtime(KB_PATH)))


def topics() -> list:
    seen = []
    for a in articles():
        if a["topic"] and a["topic"] not in seen:
            seen.append(a["topic"])
    return seen


def by_topics(selected) -> list:
    if not selected:
        return articles()
    return [a for a in articles() if a["topic"] in selected]


def short_cite(a: dict) -> str:
    names = [p.strip().split(",")[0].strip() for p in a["authors"].split(";") if p.strip()]
    if not names:
        who = "Unknown"
    elif len(names) == 1:
        who = names[0]
    elif len(names) == 2:
        who = f"{names[0]} & {names[1]}"
    else:
        who = f"{names[0]} et al."
    return f"{who} ({a['year']})"


def doi_url(a: dict) -> str:
    return f"https://doi.org/{a['doi']}" if a["doi"] else ""


def reference(a: dict) -> str:
    ref = f"{a['authors']} ({a['year']}). {a['title']}. {a['journal']}."
    return f"{ref} {doi_url(a)}".strip()


def for_prompt(items) -> str:
    blocks = []
    for a in items:
        blocks.append(
            f"<article id=\"{a['id']}\">\n"
            f"Citation: {short_cite(a)}, {a['journal']}\n"
            f"Title: {a['title']}\n"
            f"Topic: {a['topic']}\n"
            f"Mechanism: {a['mechanism']}\n"
            f"Key findings: {a['findings']}\n"
            f"Method and sample: {a['method']}\n"
            f"Limitations: {a['limitations']}\n"
            f"Relevance for REWE (team hypothesis, not a study result): {a['relevance']}\n"
            f"</article>"
        )
    return "\n\n".join(blocks)
