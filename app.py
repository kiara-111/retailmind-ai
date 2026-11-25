"""RetailMind AI: research on demand for marketing leaders. Student prototype (CBS)."""
import html
import json
import re
import time

import pandas as pd
import streamlit as st

from core import channels, config, engine, feedback, kb, llm, schedule, store

st.set_page_config(page_title="RetailMind AI", page_icon="🧠", layout="wide")

st.markdown(
    """<style>
    .block-container {padding-top: 2rem; max-width: 1100px;}
    /* Secondary text inherits the theme colour; 72% keeps 6.2:1 (light) and 8.0:1 (dark). */
    .rm-note {opacity: .72; font-size: .9rem;}
    /* Signature: implications for REWE are hypotheses, set apart from the evidence by a dashed frame. */
    .rm-hypothesis {border: 1.5px dashed rgba(190, 135, 20, .85); background: rgba(214, 160, 40, .10);
                    border-radius: .6rem; padding: .65rem .9rem; margin: .4rem 0 .2rem;}
    .rm-hypothesis b {letter-spacing: .01em;}
    </style>""",
    unsafe_allow_html=True,
)

DISCLAIMER = "Student prototype, CBS International Business School. Not an official REWE product."
PRESETS = [
    ("Weekly research report on Telegram", {"format": "report", "channel": "telegram", "freq_type": "weekly", "weekday": 4, "hour": 8}),
    ("LinkedIn post draft every Monday", {"format": "linkedin", "channel": "email", "freq_type": "weekly", "weekday": 0, "hour": 8}),
    ("Key insights by email every 3 days", {"format": "insights", "channel": "email", "freq_type": "every_n_days", "interval_days": 3, "hour": 7}),
]


# ------------------------------------------------------------------ access and profile
def gate():
    code = config.get("APP_ACCESS_CODE")
    if not code or st.session_state.get("authed"):
        return
    st.title("RetailMind AI")
    st.markdown("Research on demand for marketing leaders.")
    st.write("Enter the access code from the pitch deck to continue.")
    with st.form("gate_form"):
        entered = st.text_input("Access code", type="password")
        if st.form_submit_button("Enter", type="primary"):
            if entered.strip() == code:
                st.session_state.authed = True
                st.rerun()
            st.error("This access code doesn't match. Check the code on the pitch deck and try again.")
    st.caption(DISCLAIMER)
    st.stop()


def profile_sidebar():
    p = st.session_state.setdefault("profile", {"name": "", "email": "", "telegram": ""})
    with st.sidebar:
        st.markdown("**Profile**")
        with st.form("profile_form"):
            name = st.text_input("Name", p["name"])
            email = st.text_input("Email", p["email"], help="Your automations are stored under this address.")
            if st.form_submit_button("Save profile"):
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
                    st.error("Please enter a valid email address.")
                else:
                    p.update(name=name.strip(), email=email.strip().lower())
                    try:
                        p["telegram"] = store.telegram_chat_id(p["email"])
                    except Exception:
                        p["telegram"] = ""
                    st.rerun()
        if p["email"]:
            st.caption(f"Signed in as {p['email']}")
            telegram_box(p)
        st.divider()
        appearance_toggle()
        st.caption(f"**RetailMind AI**  \n{DISCLAIMER}")


PAGE_PATHS = ["", "ask", "knowledge-base", "automations", "delivery-log", "analytics", "system-check"]

# Streamlit keeps each visitor's theme choice ("Light", "Dark" or "System") in that browser's
# localStorage and reads it when the page loads. Writing it there and reloading switches the theme
# for this visitor only. The key carries an internal version number, so a few versions are written.
THEME_SCRIPT = """<script>
(function () {
  const choice = %s;
  const pages = %s;
  const path = window.location.pathname.replace(/\\/+$/, "");
  let base = path;
  for (const p of pages) {
    if (p && path.endsWith("/" + p)) { base = path.slice(0, -(p.length + 1)); break; }
  }
  for (const p of pages) {
    const full = (base + "/" + p).replace(/\\/+$/, "") || "/";
    for (const variant of new Set([full, full + "/"])) {
      for (let v = 2; v <= 5; v++) {
        window.localStorage.setItem("stActiveTheme-" + variant + "-v" + v, JSON.stringify(choice));
      }
    }
  }
  window.location.reload();
})();
</script>"""


def appearance_toggle():
    """Light/dark switch for demos. Without it the app follows the system setting."""
    current = (getattr(st.context.theme, "type", None) or "light").lower()
    dark = st.toggle(
        ":material/dark_mode: Dark mode",
        value=current == "dark",
        help="Switches between light and dark for this browser. The page reloads, so the current chat and profile are cleared.",
    )
    if dark != (current == "dark"):
        st.html(THEME_SCRIPT % (json.dumps("Dark" if dark else "Light"), json.dumps(PAGE_PATHS)),
                unsafe_allow_javascript=True)


@st.cache_data(show_spinner=False)
def qr_png(text: str) -> bytes:
    import io

    import qrcode

    buf = io.BytesIO()
    qrcode.make(text, border=2).save(buf, format="PNG")
    return buf.getvalue()


def telegram_box(p: dict):
    st.markdown("**Telegram**")
    if p.get("telegram"):
        st.markdown(":green-badge[:material/check: Connected]")
        return
    if not config.has("TELEGRAM_BOT_TOKEN"):
        st.caption("Telegram is not set up yet (see System check).")
        return
    try:
        link = channels.connect_link(p["email"])
    except Exception as exc:
        st.caption(f"Telegram bot not reachable: {exc}")
        return
    st.caption("1. Scan the code with your phone camera (or use the button) and press **Start** in Telegram.  \n"
               "2. Come back and click **Check connection**.")
    st.image(qr_png(link), width=170)
    st.link_button("Open RetailMind in Telegram", link, width="stretch")
    st.caption(f"No QR scanner? In Telegram open @{channels.bot_username()} and send:")
    st.code(f"/start {channels.connect_code(p['email'])}", language=None)
    if st.button("Check connection", width="stretch"):
        try:
            chat_id = channels.find_chat_id(p["email"])
        except Exception as exc:
            st.error(str(exc))
            return
        if not chat_id:
            st.warning("No Start message found yet. Open the bot with the button above and press Start.")
            return
        p["telegram"] = chat_id
        try:
            store.set_telegram_chat_id(p["email"], chat_id)
            channels.send_telegram(chat_id, f"*RetailMind AI*\nHi {p['name'] or 'there'}, your Telegram is connected. Briefings you set up for Telegram will arrive here.")
        except Exception:
            pass
        st.rerun()


def need_profile() -> dict:
    p = st.session_state.profile
    if not p["email"]:
        st.info("Add your name and email under **Your profile** in the sidebar first. That is where your deliveries go.")
        st.stop()
    return p


def header(title: str, lead: str):
    st.title(title)
    st.markdown(f'<p class="rm-note">{lead}</p>', unsafe_allow_html=True)


def source_list(ids):
    lookup = {a["id"]: a for a in kb.articles()}
    for i in ids:
        a = lookup[i]
        flag = "" if a["checked"] else "  ·  not yet verified"
        st.markdown(f"{kb.reference(a, 'md')}{flag}")


# ------------------------------------------------------------------ answers
HYPOTHESIS = re.compile(r"^\**\s*For REWE \(hypothesis\):?\s*\**\s*", re.I)


def render_answer(text: str, ids: list):
    """Evidence as normal text with APA citations; the REWE implication in a dashed hypothesis frame."""
    body, hypotheses = [], []
    for line in text.splitlines():
        (hypotheses if HYPOTHESIS.match(line.strip()) else body).append(line)
    st.markdown("\n".join(body).strip())
    for h in hypotheses:
        claim = html.escape(HYPOTHESIS.sub("", h.strip()))
        st.markdown(f'<div class="rm-hypothesis"><b>For REWE · hypothesis</b><br>{claim}</div>', unsafe_allow_html=True)
    if ids:
        with st.expander(f":material/menu_book: Evidence · {len(ids)} peer reviewed source{'s' if len(ids) > 1 else ''} (APA 7)"):
            source_list(ids)
    st.caption(":material/auto_awesome: Written by AI from the sources above. Check them before you act on it.")


# ------------------------------------------------------------------ pipeline panel
def pipeline_panel(trace: dict, label: str = "How this answer was built"):
    """Shows the real steps of one run: topic → sources → Claude → evidence check → channel."""
    if not trace:
        return
    lookup = kb.by_id()
    with st.expander(f":material/account_tree: {label}"):
        steps = st.columns(5)
        topics = ", ".join(trace.get("topics") or []) or "All topics"
        with steps[0]:
            st.markdown("**1 · Topic**")
            st.caption(f"{topics}  \n{trace.get('pool', '?')} peer reviewed articles in scope")
        with steps[1]:
            st.markdown("**2 · Sources**")
            ids = trace.get("sources") or []
            if ids:
                st.caption("  \n".join(
                    f"[{kb.intext(lookup[i])}]({kb.doi_url(lookup[i])})" if i in lookup and lookup[i]["doi"] else i for i in ids))
            else:
                st.caption("No source cited")
        with steps[2]:
            st.markdown("**3 · Claude**")
            tokens_in, tokens_out = trace.get("input_tokens") or 0, trace.get("output_tokens") or 0
            lines = [str(trace.get("model") or llm.model_name())]
            if trace.get("latency_ms"):
                lines.append(f"{trace['latency_ms'] / 1000:.1f} s")
            if tokens_in or tokens_out:
                lines.append(f"{tokens_in:,} in · {tokens_out:,} out tokens")
                lines.append(f"≈ {config.cost_usd(tokens_in, tokens_out) * 100:.2f} US cents")
            st.caption("  \n".join(lines))
        with steps[3]:
            st.markdown("**4 · Evidence check**")
            kept, removed = trace.get("citations_kept", len(ids)), trace.get("citations_removed", 0)
            check = [f"{kept} citation{'s' if kept != 1 else ''} verified against the dataset"]
            check.append(f"{removed} unsupported citation{'s' if removed != 1 else ''} removed" if removed else "no unsupported citation")
            if trace.get("auto_score"):
                check.append(f"groundedness check: {trace['auto_score']} / 5")
            st.caption("  \n".join(check))
        with steps[4]:
            st.markdown("**5 · Channel**")
            channel = trace.get("channel") or "In the app"
            detail = trace.get("delivery") or ""
            st.caption(f"{channel}" + (f"  \n{detail}" if detail else ""))
        st.caption("Costs use the list price of Claude Sonnet 5.5 (2 USD per million input and 10 USD per million output tokens).")


def trace_from_record(r: dict) -> dict:
    """Rebuilds a pipeline view for stored briefings (older runs have fewer details)."""
    return {
        "topics": r.get("topics") or [], "pool": len(kb.by_topics(r.get("topics") or [])),
        "sources": r.get("cited_ids") or [], "model": r.get("model"), "latency_ms": r.get("latency_ms"),
        "citations_kept": r.get("n_citations") if r.get("n_citations") is not None else len(r.get("cited_ids") or []),
        "auto_score": r.get("auto_score"), "channel": llm.CHANNELS.get(r.get("channel"), r.get("channel")),
    }


# ------------------------------------------------------------------ page: chat
def page_chat():
    header("Ask the research", "Answers come only from the curated set of peer reviewed articles. Every claim carries its source.")
    selected = st.multiselect("Limit to topics (optional)", kb.topics(), placeholder="All topics")
    chat = st.session_state.setdefault("chat", [])
    if not chat:
        st.markdown("**Try one of these**")
        cols = st.columns(3)
        examples = [
            "Does offering fewer product variants really increase sales?",
            "What makes loyalty card campaigns more effective?",
            "How far should we personalise app offers?",
        ]
        for col, ex in zip(cols, examples):
            if col.button(ex, width="stretch"):
                st.session_state.pending_question = ex
                st.rerun()
    for n, m in enumerate(chat):
        with st.chat_message(m["role"]):
            if m["role"] == "assistant":
                render_answer(m["content"], m.get("sources") or [])
                pipeline_panel(m.get("trace"))
            else:
                st.markdown(m["content"])
            if m["role"] == "assistant" and m.get("interaction_id"):
                rating_widget(m, f"chat_{n}")
    question = st.chat_input("Ask a question about consumer psychology in retail") or st.session_state.pop("pending_question", None)
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        pool = kb.by_topics(selected)
        with st.chat_message("assistant"):
            try:
                with st.spinner(f"Reading {len(pool)} peer reviewed articles"):
                    guidance = feedback.guidance_prompt(feedback.learned_guidance())
                    started = time.time()
                    trace = {"topics": selected or ["All topics"], "channel": "In the app (chat)"}
                    answer, ids = llm.answer_with_citations(question, pool, chat, guidance, trace)
                    latency = int((time.time() - started) * 1000)
            except Exception as exc:
                st.error(f"The language model could not be reached: {exc}")
                return
            render_answer(answer, ids)
        interaction_id = None
        try:
            interaction_id = store.log_interaction({
                "email": st.session_state.profile.get("email"), "kind": "chat", "question": question, "answer": answer,
                "cited_ids": ids, "topics": selected or feedback.topics_of(ids), "model": llm.model_name(),
                "latency_ms": latency, **feedback.metrics(answer, ids),
            })
        except Exception:
            pass  # analytics must never block an answer
        chat.append({"role": "user", "content": question})
        chat.append({"role": "assistant", "content": answer, "sources": ids, "interaction_id": interaction_id, "trace": trace})
        st.rerun()
    if chat and st.button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()


# ------------------------------------------------------------------ page: automations
def describe_sub(s: dict) -> str:
    topics = ", ".join(s.get("topics") or []) or "All topics"
    return f"**{llm.FORMATS[s['format']]}** via **{llm.CHANNELS[s['channel']]}**  ·  {schedule.describe(s)}  ·  {topics}"


def save_sub(p: dict, spec: dict):
    if spec["channel"] == "telegram" and not p.get("telegram"):
        st.error("Connect Telegram in the sidebar first (under Your profile).")
        return
    # the column is still called "whatsapp" in the database; it holds the Telegram chat id
    sub = {"user_name": p["name"], "email": p["email"], "whatsapp": p.get("telegram", ""), **spec}
    sub["topics"] = spec.get("topics") or []
    try:
        store.add_subscription(sub)
    except Exception as exc:
        st.error(f"Could not save: {exc}")
        return
    st.session_state.pop("proposal", None)
    st.session_state.flash = "Automation saved."
    st.rerun()


def page_automations():
    p = need_profile()
    header("Automations", "Choose what you want to receive, where and how often. Times are Central European Time.")
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))
    all_topics = kb.topics()

    tab_say, tab_quick, tab_form = st.tabs(["Say it in your own words", "Quick start", "Set it up step by step"])

    with tab_say:
        with st.form("nl_form"):
            text = st.text_input(
                "What would you like to receive?",
                placeholder="Send me a Telegram report on loyalty programmes every Friday at 8",
            )
            go = st.form_submit_button("Interpret", type="primary")
        if go and text.strip():
            try:
                with st.spinner("Interpreting your request"):
                    st.session_state.proposal = llm.parse_automation(text.strip(), all_topics)
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get("proposal"):
            prop = st.session_state.proposal
            st.markdown("**This is what I understood**")
            st.markdown(describe_sub(prop))
            c1, c2, _ = st.columns([1, 1, 4])
            if c1.button("Save automation", type="primary"):
                save_sub(p, prop)
            if c2.button("Discard"):
                st.session_state.pop("proposal")
                st.rerun()

    with tab_quick:
        topics_q = st.multiselect("Topics", all_topics, placeholder="All topics", key="quick_topics")
        for label, spec in PRESETS:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{label}**  \n<span class='rm-note'>{schedule.describe(spec)}</span>", unsafe_allow_html=True)
            if c2.button("Add", key=f"preset_{label}", width="stretch"):
                save_sub(p, {**spec, "topics": topics_q})

    with tab_form:
        with st.form("manual_form"):
            topics_m = st.multiselect("Topic", all_topics, placeholder="All topics")
            c1, c2 = st.columns(2)
            fmt = c1.selectbox("Format", list(llm.FORMATS), format_func=llm.FORMATS.get)
            channel = c2.selectbox("Channel", list(llm.CHANNELS), format_func=llm.CHANNELS.get)
            c3, c4, c5 = st.columns(3)
            freq = c3.selectbox(
                "Timing", ["weekly", "every_n_days", "daily"],
                format_func={"weekly": "Weekly", "every_n_days": "Every N days", "daily": "Daily"}.get,
            )
            weekday = c4.selectbox("Weekday (weekly)", range(7), format_func=lambda i: schedule.WEEKDAYS[i])
            interval = c4.number_input("N (every N days)", 1, 60, 3)
            hour = c5.selectbox("Time", range(24), index=8, format_func=lambda h: f"{h:02d}:00")
            if st.form_submit_button("Save automation", type="primary"):
                save_sub(p, {
                    "topics": topics_m, "format": fmt, "channel": channel, "freq_type": freq,
                    "weekday": int(weekday) if freq == "weekly" else None,
                    "interval_days": int(interval) if freq == "every_n_days" else None,
                    "hour": int(hour),
                })

    st.divider()
    st.subheader("Your automations")
    try:
        subs = store.list_subscriptions(p["email"])
    except Exception as exc:
        st.error(f"Storage is not reachable: {exc}")
        return
    if not subs:
        st.write("Nothing set up yet. Add your first automation above.")
        return
    for s in subs:
        with st.container(border=True):
            st.markdown(describe_sub(s))
            state = ":green-badge[:material/schedule: Active]" if s.get("active") else ":orange-badge[:material/pause: Paused]"
            nxt = schedule.local_str(s["next_run_at"]) if s.get("active") else "paused"
            st.markdown(f"{state} <span class='rm-note'>Next: {nxt}  ·  Last sent: {schedule.local_str(s.get('last_run_at'))}</span>",
                        unsafe_allow_html=True)
            c1, c2, c3, _ = st.columns([1, 1, 1, 3])
            if c1.button("Send now", key=f"now_{s['id']}", type="primary", width="stretch"):
                with st.spinner("Writing and sending"):
                    st.session_state[f"result_{s['id']}"] = engine.run(s, trigger="manual")
            if c2.button("Resume" if not s.get("active") else "Pause", key=f"tog_{s['id']}", width="stretch"):
                changes = {"active": not s.get("active")}
                if changes["active"]:
                    changes["next_run_at"] = schedule.iso(schedule.next_run({**s, "next_run_at": None}))
                store.update_subscription(s["id"], changes)
                st.rerun()
            if c3.button("Delete", key=f"del_{s['id']}", width="stretch"):
                store.delete_subscription(s["id"])
                st.rerun()
            result = st.session_state.get(f"result_{s['id']}")
            if result:
                if result["status"] == "sent":
                    st.success(result["detail"])
                else:
                    st.error(f"Not delivered: {result['detail']}")
                if result.get("piece"):
                    with st.expander("What was written", expanded=result["status"] != "sent"):
                        show_piece(s, result["piece"])
    st.markdown(
        "<p class='rm-note'>Scheduled deliveries are checked twice per hour, so they can arrive up to about "
        "30 minutes after the chosen time. If Telegram is not connected, Telegram briefings arrive by email instead.</p>",
        unsafe_allow_html=True,
    )


def show_piece(sub: dict, piece: dict):
    if sub["format"] == "linkedin":
        st.code(piece["body"], language=None, wrap_lines=True)
        st.link_button("Open in LinkedIn", channels.linkedin_share_url(piece["body"]))
    else:
        st.markdown(piece["body"])
    st.markdown("**References (APA 7)**")
    for s in piece["sources"]:
        st.markdown(s["apa_md"])
    pipeline_panel(piece.get("trace"), "How this briefing was built")


# ------------------------------------------------------------------ page: claim check
VERDICT_BADGE = {
    "supported": ":green-badge[:material/check_circle: Supported]",
    "contradicted": ":red-badge[:material/cancel: Contradicted]",
    "mixed": ":orange-badge[:material/balance: Mixed evidence]",
    "no_evidence": ":gray-badge[:material/search_off: No evidence in dataset]",
}
CLAIM_EXAMPLES = [
    "Offering fewer product variants increases sales.",
    "Shoppers notice when package sizes shrink.",
    "Nudges in the store reliably make baskets healthier.",
    "Influencer reach matters more than credibility.",
]


def page_claim():
    header("Claim check", "Test a marketing assumption against the peer reviewed dataset. "
                          "RetailMind shows the evidence and the counter-evidence, or says plainly that the dataset has none.")
    selected = st.multiselect("Limit to topics (optional)", kb.topics(), placeholder="All topics", key="claim_topics")
    cols = st.columns(len(CLAIM_EXAMPLES))
    for col, ex in zip(cols, CLAIM_EXAMPLES):
        if col.button(ex, width="stretch", key=f"claim_ex_{ex}"):
            st.session_state.claim_text = ex
    with st.form("claim_form"):
        claim = st.text_area("Your assumption", key="claim_text", height=90,
                             placeholder="e.g. Loyalty points mainly work because of the discount.")
        go = st.form_submit_button("Check against the evidence", type="primary")
    if go and claim.strip():
        pool = kb.by_topics(selected)
        trace = {"topics": selected or ["All topics"], "channel": "In the app (claim check)"}
        try:
            with st.spinner(f"Checking against {len(pool)} peer reviewed articles"):
                result = llm.check_claim(claim.strip(), pool, trace)
        except Exception as exc:
            st.error(f"The check could not be completed: {exc}")
            return
        record = {"claim": claim.strip(), "result": result, "trace": trace}
        try:
            text = f"Verdict: {llm.VERDICTS[result['verdict']]}. {result['summary']}"
            record["interaction_id"] = store.log_interaction({
                "email": st.session_state.profile.get("email"), "kind": "claim", "question": claim.strip(),
                "answer": text, "cited_ids": result["ids"], "topics": selected or feedback.topics_of(result["ids"]),
                "model": trace.get("model") or llm.model_name(), "latency_ms": trace.get("latency_ms"),
                "answer_words": len(text.split()), "n_citations": len(result["ids"]),
                "not_covered": result["verdict"] == "no_evidence",
            })
        except Exception:
            pass
        st.session_state.claim_result = record
    record = st.session_state.get("claim_result")
    if not record:
        return
    r = record["result"]
    lookup = kb.by_id()
    st.divider()
    st.markdown(f"#### “{record['claim']}”")
    st.markdown(VERDICT_BADGE[r["verdict"]])
    st.markdown(r["summary"])
    if r["verdict"] != "no_evidence":
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**:material/thumb_up: Evidence for**")
            for e in r["evidence"] or []:
                st.markdown(f"- {e['finding']} ({kb.intext(lookup[e['id']])})")
            if not r["evidence"]:
                st.caption("No supporting study in the dataset.")
        with c2:
            st.markdown("**:material/thumb_down: Evidence against or limits**")
            for e in r["counter_evidence"] or []:
                st.markdown(f"- {e['finding']} ({kb.intext(lookup[e['id']])})")
            if not r["counter_evidence"]:
                st.caption("No contradicting study in the dataset.")
        if r["for_rewe"]:
            st.markdown(f'<div class="rm-hypothesis"><b>For REWE · hypothesis</b><br>{html.escape(r["for_rewe"])}</div>',
                        unsafe_allow_html=True)
        with st.expander(f":material/menu_book: Evidence · {len(r['ids'])} peer reviewed source{'s' if len(r['ids']) != 1 else ''} (APA 7)"):
            source_list(r["ids"])
    else:
        st.caption("RetailMind does not fill gaps with general knowledge. The question is listed as a knowledge gap under Analytics.")
    st.caption(":material/auto_awesome: Written by AI from the sources above. Check them before you act on it.")
    pipeline_panel(record["trace"], "How this check was built")
    if record.get("interaction_id"):
        rating_widget(record, "claim")


# ------------------------------------------------------------------ rating
STARS = {5: "★★★★★", 4: "★★★★☆", 3: "★★★☆☆", 2: "★★☆☆☆", 1: "★☆☆☆☆"}


def rating_widget(item: dict, key: str):
    """item needs 'interaction_id'; stores the rating in the item after submitting."""
    if item.get("rated"):
        st.caption(f"Your rating: {STARS[item['rated']]}  ·  thank you, it helps improve RetailMind.")
        return
    with st.expander("Rate this answer"):
        with st.form(f"rate_{key}"):
            stars = st.radio("Overall", [5, 4, 3, 2, 1], index=None, format_func=STARS.get, horizontal=True)
            tags = st.multiselect("What stands out?", feedback.TAGS)
            comment = st.text_input("Comment (optional)")
            if st.form_submit_button("Submit rating"):
                if not stars:
                    st.error("Please choose a star rating.")
                    return
                try:
                    store.update_interaction(item["interaction_id"], {"rating": stars, "tags": tags, "comment": comment.strip()})
                    item["rated"] = stars
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save the rating: {exc}")


# ------------------------------------------------------------------ page: analytics
def bar(df: pd.DataFrame, x: str, y: str, horizontal: bool = False):
    st.bar_chart(df, x=x, y=y, horizontal=horizontal, height=260)


def page_analytics():
    header("Analytics", "How good are the answers, what do readers want, and what does the system learn from it. "
                        "Covers chat answers and scheduled briefings of all users.")
    try:
        rows = store.list_interactions(1000)
    except Exception as exc:
        st.error(f"Analytics data is not available: {exc}")
        st.info("If the message mentions 'interactions', run supabase_analytics.sql once in the Supabase SQL Editor.")
        return
    if not rows:
        st.info("No answers yet. Ask a question under **Ask the research** or send a briefing, then rate it.")
        return
    df = pd.DataFrame(rows)
    for col in ["kind", "question", "answer", "comment", "format", "channel", "rating", "auto_score", "n_citations",
                "answer_words", "latency_ms", "not_covered", "tags", "cited_ids", "topics", "auto_reason"]:
        if col not in df.columns:
            df[col] = None  # older or unrated rows may lack a field
    for col in ["rating", "auto_score", "n_citations", "answer_words", "latency_ms"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["created"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert(schedule.TZ)
    for col in ["tags", "cited_ids", "topics"]:
        df[col] = df[col].apply(lambda v: v if isinstance(v, list) else [])
    df["not_covered"] = df["not_covered"].fillna(False).astype(bool)
    rated = df[df["rating"].notna()]

    k = st.columns(6)
    k[0].metric("Answers and claim checks", int(df["kind"].isin(["chat", "claim"]).sum()))
    k[1].metric("Briefings sent", int((df["kind"] == "delivery").sum()))
    k[2].metric("Rated", f"{len(rated) / len(df):.0%}")
    k[3].metric("Reader rating", f"{rated['rating'].mean():.1f} / 5" if len(rated) else "n/a")
    k[4].metric("Groundedness (auto)", f"{df['auto_score'].mean():.1f} / 5" if df["auto_score"].notna().any() else "n/a")
    k[5].metric("Knowledge gaps", int(df["not_covered"].sum() + (rated["rating"] <= 2).sum()))

    tab_q, tab_u, tab_l, tab_e = st.tabs(["Quality", "Usage", "Learning loop", "Automatic check & export"])

    with tab_q:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Reader ratings**")
            if len(rated):
                dist = rated["rating"].astype(int).value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
                bar(pd.DataFrame({"Stars": [STARS[i] for i in dist.index], "Answers": dist.values}), "Stars", "Answers")
            else:
                st.caption("No ratings yet.")
        with c2:
            st.markdown("**What readers point out**")
            tags = pd.Series([t for ts in rated["tags"] for t in ts]).value_counts()
            if len(tags):
                bar(pd.DataFrame({"Tag": tags.index, "Mentions": tags.values}), "Tag", "Mentions", horizontal=True)
            else:
                st.caption("No tags yet.")
        st.markdown("**Rating by topic**")
        topic_rows = [(t, r["rating"]) for _, r in rated.iterrows() for t in (r["topics"] or ["(no topic)"])]
        if topic_rows:
            tdf = pd.DataFrame(topic_rows, columns=["Topic", "Rating"]).groupby("Topic")["Rating"].agg(["mean", "count"])
            tdf = tdf.rename(columns={"mean": "Average rating", "count": "Rated answers"}).sort_values("Average rating")
            st.dataframe(tdf.style.format({"Average rating": "{:.1f}"}), width="stretch")
        st.markdown("**Latest comments**")
        comments = rated[rated["comment"].fillna("") != ""][["created", "kind", "rating", "comment"]].head(10)
        if len(comments):
            comments = comments.assign(created=comments["created"].dt.strftime("%d %b, %H:%M"),
                                       rating=comments["rating"].astype(int).map(STARS))
            st.dataframe(comments, hide_index=True, width="stretch")
        else:
            st.caption("No comments yet.")

    with tab_u:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Answers and briefings per day**")
            per_day = df.groupby(df["created"].dt.date).size()
            bar(pd.DataFrame({"Day": per_day.index.astype(str), "Count": per_day.values}), "Day", "Count")
        with c2:
            st.markdown("**Most cited articles**")
            cited = pd.Series([i for ids in df["cited_ids"] for i in ids]).value_counts().head(10)
            if len(cited):
                lookup = kb.by_id()
                labels = [f"{i} {kb.intext(lookup[i])}" if i in lookup else i for i in cited.index]
                bar(pd.DataFrame({"Article": labels, "Citations": cited.values}), "Article", "Citations", horizontal=True)
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Topics asked about**")
            topics = pd.Series([t for ts in df["topics"] for t in ts]).value_counts()
            if len(topics):
                bar(pd.DataFrame({"Topic": topics.index, "Answers": topics.values}), "Topic", "Answers", horizontal=True)
        with c4:
            st.markdown("**Briefings by format and channel**")
            d = df[df["kind"] == "delivery"]
            if len(d):
                combo = (d["format"].map(llm.FORMATS).fillna(d["format"]) + " via " + d["channel"].map(llm.CHANNELS).fillna(d["channel"])).value_counts()
                bar(pd.DataFrame({"Briefing": combo.index, "Sent": combo.values}), "Briefing", "Sent", horizontal=True)
            else:
                st.caption("No briefings yet.")
        chats = df[df["kind"] == "chat"]
        if len(chats):
            m = st.columns(3)
            m[0].metric("Median response time", f"{chats['latency_ms'].median() / 1000:.1f} s" if chats["latency_ms"].notna().any() else "n/a")
            m[1].metric("Citations per answer", f"{chats['n_citations'].mean():.1f}")
            m[2].metric("Words per answer", f"{chats['answer_words'].mean():.0f}")

    with tab_l:
        guidance = feedback.learned_guidance(rows)
        st.markdown(
            "The language model is not retrained. RetailMind learns from your ratings in three ways, "
            "and this tab shows exactly what it uses right now."
        )
        st.markdown(f"**1. Style rules from repeated feedback** (from {guidance['n_rated']} rated answers)")
        if guidance["rules"]:
            for r in guidance["rules"]:
                st.markdown(f"- {r}")
        else:
            st.caption("A rule appears once readers give the same feedback tag at least twice.")
        st.markdown("**2. Highly rated answers used as examples**")
        if guidance["examples"]:
            for ex in guidance["examples"]:
                with st.expander(f"{STARS[int(ex['rating'])]}  {ex['question']}"):
                    st.markdown(ex["answer"])
        else:
            st.caption("Answers rated 4 or 5 stars without critical tags become examples for future answers.")
        st.markdown("**3. Knowledge gaps for the team**")
        gaps = df[(df["not_covered"]) | (df["rating"] <= 2)]
        if len(gaps):
            show = gaps[["created", "kind", "question", "rating", "comment"]].copy()
            show["created"] = show["created"].dt.strftime("%d %b, %H:%M")
            show["rating"] = show["rating"].map(lambda v: STARS.get(int(v), "") if pd.notna(v) else "not covered")
            st.dataframe(show, hide_index=True, width="stretch")
            st.caption("Add peer reviewed articles on these questions to the knowledge base to close the gaps.")
        else:
            st.caption("No gaps found yet.")

    with tab_e:
        st.markdown(
            "**Automatic groundedness check.** A second model run compares each answer with the article summaries "
            "it cites and scores from 1 (unsupported) to 5 (fully supported, hypotheses marked)."
        )
        todo = [r for r in rows if r.get("auto_score") in (None, "") and r.get("answer")][:10]
        if st.button(f"Check the {len(todo)} latest unchecked answers", disabled=not todo, type="primary"):
            done = 0
            with st.spinner("Checking answers"):
                for r in todo:
                    try:
                        result = feedback.auto_evaluate(r, llm.ask)
                        store.update_interaction(r["id"], result)
                        done += 1
                    except Exception as exc:
                        st.warning(f"One answer could not be checked: {exc}")
            st.success(f"{done} answers checked.")
            st.rerun()
        scored = df[df["auto_score"].notna()]
        if len(scored):
            dist = scored["auto_score"].astype(int).value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
            bar(pd.DataFrame({"Score": [str(i) for i in dist.index], "Answers": dist.values}), "Score", "Answers")
            low = scored[scored["auto_score"] <= 3][["question", "auto_score", "auto_reason"]].head(10)
            if len(low):
                st.markdown("**Answers with weak grounding**")
                st.dataframe(low, hide_index=True, width="stretch")
        st.divider()
        st.markdown(
            "**Export.** Rated answers in the chat-message JSONL format that evaluation tools and fine-tuning "
            "services expect, plus all data as CSV."
        )
        c1, c2 = st.columns(2)
        jsonl = feedback.export_jsonl(rows)
        c1.download_button("Download rated answers (JSONL)", jsonl or "", file_name="retailmind_rated_answers.jsonl",
                           mime="application/jsonl", disabled=not jsonl, width="stretch")
        csv = df.drop(columns=["created", "email"], errors="ignore").to_csv(index=False)
        c2.download_button("Download all interactions (CSV)", csv, file_name="retailmind_interactions.csv",
                           mime="text/csv", width="stretch")
        st.caption("Email addresses are left out of both exports.")


# ------------------------------------------------------------------ page: knowledge base
def page_kb():
    header("Knowledge base", "The fixed foundation of every answer and every delivery: peer reviewed journal articles only.")
    items = kb.articles()
    c1, c2, c3 = st.columns(3)
    c1.metric("Peer reviewed articles", len(items))
    c2.metric("Topics", len(kb.topics()))
    c3.metric("Read from source", f"{sum(a['checked'] for a in items)} of {len(items)}")
    selected = st.multiselect("Topic", kb.topics(), placeholder="All topics")
    for a in sorted(kb.by_topics(selected), key=lambda x: x["id"]):
        with st.expander(f"{a['id']}  ·  {kb.short_cite(a)}  ·  {a['title']}"):
            check = ":green-badge[:material/verified: Read from source]" if a["checked"] else ":orange-badge[:material/help: Not yet verified]"
            st.markdown(f":gray-badge[{a['topic']}] {check}")
            st.markdown(f"**Mechanism:** {a['mechanism']}")
            st.markdown(f"**Key findings:** {a['findings']}")
            st.markdown(f"**Method and sample:** {a['method']}")
            st.markdown(f"**Limitations:** {a['limitations']}")
            st.markdown(f"**Relevance for REWE (hypothesis):** {a['relevance']}")
            st.markdown(f"**Reference (APA 7):** {kb.reference(a, 'md')}")
            if a.get("url"):
                st.caption(f"Accessed via: {a['url']}")
    st.divider()
    st.subheader("Bibliography (APA 7)")
    ordered = kb.ordered()
    for a in ordered:
        st.markdown(f"**{a['id']}** {kb.reference(a, 'md')}")
    with st.expander("Copy as plain text (for the pitch deck backup slides)"):
        st.code("\n\n".join(f"{a['id']} {kb.reference(a)}" for a in ordered), language=None, wrap_lines=True)


# ------------------------------------------------------------------ page: log
def page_log():
    p = need_profile()
    header("Delivery log", "Everything that was sent to you, scheduled or by hand.")
    try:
        rows = store.list_deliveries(p["email"])
    except Exception as exc:
        st.error(f"Storage is not reachable: {exc}")
        return
    if not rows:
        st.write("No deliveries yet.")
        return
    for d in rows:
        ok = d["status"] == "sent"
        title = (f"{'Sent' if ok else 'Failed'}  ·  {schedule.local_str(d['created_at'])}  ·  "
                 f"{llm.FORMATS.get(d['format'], d['format'])} via {llm.CHANNELS.get(d['channel'], d['channel'])}"
                 f"  ·  {d.get('trigger', '')}")
        with st.expander(title):
            st.caption(d.get("detail", ""))
            if d.get("content"):
                st.markdown(d["content"])
                if ok:
                    rate_delivery(d)


def rate_delivery(d: dict):
    """Briefings are logged as interactions when sent; find that record and rate it."""
    key = f"delivery_rating_{d['id']}"
    item = st.session_state.setdefault(key, {})
    if "interaction_id" not in item:
        match = None
        try:
            for r in store.list_interactions(300):
                if r.get("kind") == "delivery" and r.get("answer") == d.get("content"):
                    match = r
                    break
        except Exception:
            pass
        item["interaction_id"] = match["id"] if match else None
        item["trace"] = trace_from_record(match) if match else None
        if match and match.get("rating"):
            item["rated"] = int(match["rating"])
    pipeline_panel(item.get("trace"), "How this briefing was built")
    if item.get("interaction_id"):
        rating_widget(item, key)


# ------------------------------------------------------------------ page: system check
def page_check():
    header("System check", "Shows which connections are set up and lets you test each one.")
    p = st.session_state.profile

    def row(label, ok, detail):
        c1, c2 = st.columns([1, 3])
        c1.markdown(f"**{label}**")
        c2.markdown(f"{':green-badge[:material/check: Ready]' if ok else ':red-badge[:material/close: Missing]'} {detail}")

    row("Knowledge base", True, f"{len(kb.articles())} articles in {len(kb.topics())} topics")
    row("Language model", config.has("ANTHROPIC_API_KEY"),
        f"Model: {config.get('ANTHROPIC_MODEL', config.DEFAULT_MODEL)}" if config.has("ANTHROPIC_API_KEY") else "ANTHROPIC_API_KEY missing")
    row("Storage", store.backend() == "supabase",
        "Supabase configured" if store.backend() == "supabase" else "Supabase not configured. Automations only live on this computer and the scheduler cannot see them.")
    row("Email", config.has("SMTP_USER", "SMTP_PASSWORD"),
        f"Sender: {config.get('SMTP_USER')}" if config.has("SMTP_USER", "SMTP_PASSWORD") else "SMTP_USER / SMTP_PASSWORD missing")
    row("Telegram", config.has("TELEGRAM_BOT_TOKEN"),
        "Bot token set" + (" and your chat is connected" if p.get("telegram") else ", your chat is not connected yet")
        if config.has("TELEGRAM_BOT_TOKEN") else "TELEGRAM_BOT_TOKEN missing")

    st.divider()
    st.subheader("Live tests")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Test language model", width="stretch"):
        try:
            st.success("Model answered: " + llm.ask("Reply with the single word READY.", [{"role": "user", "content": "Status?"}], 300))
        except Exception as exc:
            st.error(str(exc))
    if c2.button("Test storage", width="stretch"):
        try:
            st.success(store.ping())
        except Exception as exc:
            st.error(str(exc))
    if c3.button("Send test email", width="stretch", disabled=not p["email"]):
        try:
            st.success(channels.send_email(p["email"], "RetailMind AI | Test", "Email delivery works."))
        except Exception as exc:
            st.error(str(exc))
    if c4.button("Send test Telegram", width="stretch", disabled=not p.get("telegram")):
        try:
            st.success(channels.send_telegram(p["telegram"], "*RetailMind AI*\nTelegram delivery works."))
        except Exception as exc:
            st.error(str(exc))
    if not p["email"]:
        st.caption("Save your profile in the sidebar to enable the email test, then connect Telegram there.")

    st.divider()
    st.subheader("Connect your Telegram")
    st.markdown(
        "1. Save your profile in the sidebar.\n"
        "2. Click **Open RetailMind in Telegram** there and press **Start** in Telegram.\n"
        "3. Click **Check connection**. You get a short welcome message in Telegram.\n\n"
        "Each person connects once. The connection is stored with their automations."
    )


# ------------------------------------------------------------------ run
gate()
navigation = st.navigation({
    "Research": [
        st.Page(page_chat, title="Ask the research", icon=":material/forum:", url_path="ask", default=True),
        st.Page(page_claim, title="Claim check", icon=":material/fact_check:", url_path="claim-check"),
        st.Page(page_kb, title="Knowledge base", icon=":material/menu_book:", url_path="knowledge-base"),
    ],
    "Briefings": [
        st.Page(page_automations, title="Automations", icon=":material/schedule_send:", url_path="automations"),
        st.Page(page_log, title="Delivery log", icon=":material/inbox:", url_path="delivery-log"),
    ],
    "Team": [
        st.Page(page_analytics, title="Analytics", icon=":material/insights:", url_path="analytics"),
        st.Page(page_check, title="System check", icon=":material/settings:", url_path="system-check"),
    ],
})
profile_sidebar()
navigation.run()
