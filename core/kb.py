"""Knowledge base: reads the curated, peer reviewed articles from knowledge_base.xlsx.

All references are formatted in APA 7 with a DOI link.
"""
import html
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
OPTIONAL = {"volume": "Volume", "issue": "Issue", "pages": "Pages", "url": "Source link"}

ID_RE = r"R\d{2,3}"


@lru_cache(maxsize=1)
def _load(mtime: float):
    wb = load_workbook(KB_PATH, read_only=True, data_only=True)
    ws = wb["Articles"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h).strip() if h else "" for h in rows[0]]
    idx = {key: header.index(label) for key, label in {**COLUMNS, **OPTIONAL}.items() if label in header}
    missing = [label for key, label in COLUMNS.items() if key not in idx]
    if missing:
        raise ValueError(f"knowledge_base.xlsx is missing columns: {', '.join(missing)}")
    articles = []
    for row in rows[1:]:
        if not row or not row[idx["id"]] or not row[idx["title"]]:
            continue
        a = {k: ("" if row[i] is None else str(row[i]).strip()) for k, i in idx.items()}
        for key in OPTIONAL:
            a.setdefault(key, "")
        for key in ("year", "volume", "issue"):
            a[key] = a[key][:-2] if a[key].endswith(".0") else a[key]
        a["doi"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", a["doi"])
        a["checked"] = bool(a["checked_by"]) and "not yet" not in a["checked_by"].lower()
        articles.append(a)
    wb.close()
    return tuple(articles)


def articles() -> list:
    return list(_load(os.path.getmtime(KB_PATH)))


def by_id() -> dict:
    return {a["id"]: a for a in articles()}


def ordered() -> list:
    """Articles in reference-list order. IDs are assigned alphabetically, so ID order equals APA order."""
    return sorted(articles(), key=lambda a: a["id"])


def numbers() -> dict:
    """Running number of each article in the alphabetical reference list (1, 2, 3 ...)."""
    return {a["id"]: n for n, a in enumerate(ordered(), 1)}


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


# ---------------------------------------------------------------- APA 7
def _authors(a: dict) -> list:
    return [p.strip() for p in a["authors"].split(";") if p.strip()]


def _surname(author: str) -> str:
    return author.split(",")[0].strip()


def intext(a: dict) -> str:
    """APA 7 parenthetical citation without brackets, e.g. 'Fasolo et al., 2009'."""
    names = [_surname(x) for x in _authors(a)]
    if not names:
        who = "Unknown"
    elif len(names) == 1:
        who = names[0]
    elif len(names) == 2:
        who = f"{names[0]} & {names[1]}"
    else:
        who = f"{names[0]} et al."
    return f"{who}, {a['year']}"


def short_cite(a: dict) -> str:
    """Parenthetical APA 7 citation, e.g. '(Fasolo et al., 2009)'."""
    return f"({intext(a)})"


def doi_url(a: dict) -> str:
    return f"https://doi.org/{a['doi']}" if a["doi"] else ""


def _author_list(a: dict) -> str:
    names = _authors(a)
    if len(names) > 20:  # APA 7: first 19, ellipsis, last author
        names = names[:19] + ["…", names[-1]]
        return ", ".join(names[:-2]) + ", … " + names[-1]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def reference(a: dict, style: str = "plain") -> str:
    """APA 7 reference. style: 'plain', 'md' (Markdown italics) or 'html'."""
    def it(text):
        if style == "md":
            return f"*{text}*"
        if style == "html":
            return f"<i>{html.escape(text, quote=False)}</i>"
        return text

    esc = (lambda t: html.escape(t, quote=False)) if style == "html" else (lambda t: t)
    authors = _author_list(a)
    if not authors.endswith("."):
        authors += "."
    title = a["title"].rstrip(".")
    title_end = "" if title.endswith(("?", "!")) else "."
    source = it(a["journal"])
    if a["volume"]:
        source += ", " + it(a["volume"])
        if a["issue"]:
            source += f"({esc(a['issue'])})"
    if a["pages"]:
        source += ", " + esc(a["pages"])
    ref = f"{esc(authors)} ({a['year']}). {esc(title)}{title_end} {source}."
    url = doi_url(a)
    if url:
        ref += f' <a href="{url}">{url}</a>' if style == "html" else f" {url}"
    return ref


def apply_citations(text: str, allowed=None) -> tuple:
    """Replaces id citations like [R03] or [R03, R07] with APA 7 in-text citations.

    Returns (new_text, cited_ids). Unknown ids are removed rather than shown."""
    lookup = by_id()
    allowed = set(allowed) if allowed is not None else set(lookup)
    cited = []
    # merge neighbouring brackets: [R01][R02] or [R01] [R02] -> [R01, R02]
    text = re.sub(rf"({ID_RE})\]\s*\[(?={ID_RE})", r"\1, ", text)

    def repl(match):
        ids = [i for i in re.findall(ID_RE, match.group(1)) if i in lookup and i in allowed]
        if not ids:
            return ""
        for i in ids:
            if i not in cited:
                cited.append(i)
        unique = sorted(dict.fromkeys(ids), key=lambda i: (intext(lookup[i]).lower()))  # APA 7: alphabetical
        return "(" + "; ".join(intext(lookup[i]) for i in unique) + ")"

    text = re.sub(rf"\[({ID_RE}(?:\s*[,;]\s*{ID_RE})*)\]", repl, text)
    text = re.sub(r"\(([^()]*)\)\s*\((?=[A-Z][^()]*, \d{4}\))", r"(\1; ", text)  # (A, 2009) (B, 2011) -> (A, 2009; B, 2011)
    text = re.sub(r" +([.,;:])", r"\1", text)
    return text, cited


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
