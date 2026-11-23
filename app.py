"""RetailMind AI: research on demand for marketing leaders. Student prototype (CBS)."""
import re

import streamlit as st

import time

import pandas as pd

from core import channels, config, engine, feedback, kb, llm, schedule, store

st.set_page_config(page_title="RetailMind AI", page_icon="🧠", layout="wide")

st.markdown(
    """<style>
    .block-container {padding-top: 2.2rem; max-width: 1100px;}
    .rm-kicker {letter-spacing: .18em; text-transform: uppercase; font-size: .72rem; color: #a07a2c; font-weight: 700;}
    .rm-note {color: #6b6f6c; font-size: .85rem;}
    .rm-pill {display:inline-block; padding:2px 10px; border-radius:12px; font-size:.75rem; margin-right:6px;
              background:#e4efe8; color:#1f6f4a;}
    .rm-pill.warn {background:#fbeed3; color:#8a5a00;}
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
    st.markdown('<div class="rm-kicker">RetailMind AI</div>', unsafe_allow_html=True)
    st.title("Research on demand for marketing leaders")
    st.write("Enter the access code you received with the pitch deck.")
    with st.form("gate_form"):
        entered = st.text_input("Access code", type="password")
        if st.form_submit_button("Enter", type="primary"):
            if entered.strip() == code:
                st.session_state.authed = True
                st.rerun()
            st.error("That code is not correct.")
    st.caption(DISCLAIMER)
    st.stop()


def profile_sidebar() -> dict:
    p = st.session_state.setdefault("profile", {"name": "", "email": "", "telegram": ""})
    with st.sidebar:
        st.markdown('<div class="rm-kicker">RetailMind AI</div>', unsafe_allow_html=True)
        st.markdown("**Research on demand**")
        page = st.radio(
            "Go to",
            ["Ask the research", "Automations", "Knowledge base", "Delivery log", "Analytics", "System check"],
            label_visibility="collapsed",
        )
        st.divider()
        st.markdown("**Your profile**")
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
        st.caption(DISCLAIMER)
    return page


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
        st.markdown("<span class='rm-pill'>connected</span>", unsafe_allow_html=True)
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
    st.markdown('<div class="rm-kicker">RetailMind AI</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p class="rm-note">{lead}</p>', unsafe_allow_html=True)


def source_list(ids):
    lookup = {a["id"]: a for a in kb.articles()}
    for i in ids:
        a = lookup[i]
        flag = "" if a["checked"] else "  ·  not yet verified"
        st.markdown(f"{kb.reference(a, 'md')}{flag}")


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
            st.markdown(m["content"])
            if m.get("sources"):
                with st.expander(f"References, APA 7 ({len(m['sources'])})"):
                    source_list(m["sources"])
            if m["role"] == "assistant" and m.get("interaction_id"):
                rating_widget(m, f"chat_{n}")
    question = st.chat_input("Ask a question about consumer psychology in retail") or st.session_state.pop("pending_question", None)
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        pool = kb.by_topics(selected)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Reading the knowledge base"):
                    guidance = feedback.guidance_prompt(feedback.learned_guidance())
                    started = time.time()
                    answer, ids = llm.answer_with_citations(question, pool, chat, guidance)
                    latency = int((time.time() - started) * 1000)
            except Exception as exc:
                st.error(f"The language model could not be reached: {exc}")
                return
            st.markdown(answer)
            if ids:
                with st.expander(f"References, APA 7 ({len(ids)})"):
                    source_list(ids)
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
        chat.append({"role": "assistant", "content": answer, "sources": ids, "interaction_id": interaction_id})
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
            state = "Active" if s.get("active") else "Paused"
            st.markdown(
                f"<span class='rm-pill{'' if s.get('active') else ' warn'}'>{state}</span>"
                f"<span class='rm-note'>Next: {schedule.local_str(s['next_run_at']) if s.get('active') else 'paused'}"
                f"  ·  Last sent: {schedule.local_str(s.get('last_run_at'))}</span>",
                unsafe_allow_html=True,
            )
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
    st.bar_chart(df, x=x, y=y, color="#1f6f4a", horizontal=horizontal, height=260)


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
    for col in ["rating", "auto_score", "n_citations", "answer_words", "latency_ms"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["created"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert(schedule.TZ)
    for col in ["tags", "cited_ids", "topics"]:
        df[col] = df[col].apply(lambda v: v if isinstance(v, list) else [])
    df["not_covered"] = df["not_covered"].fillna(False).astype(bool)
    rated = df[df["rating"].notna()]

    k = st.columns(6)
    k[0].metric("Chat answers", int((df["kind"] == "chat").sum()))
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
    c1.metric("Articles", len(items))
    c2.metric("Topics", len(kb.topics()))
    c3.metric("Peer reviewed journal articles", f"{len(items)}")
    selected = st.multiselect("Topic", kb.topics(), placeholder="All topics")
    for a in sorted(kb.by_topics(selected), key=lambda x: x["id"]):
        with st.expander(f"{a['id']}  ·  {kb.short_cite(a)}  ·  {a['title']}"):
            pill = "<span class='rm-pill'>read from source</span>" if a["checked"] else "<span class='rm-pill warn'>not yet verified</span>"
            st.markdown(f"<span class='rm-pill'>{a['topic']}</span>{pill}", unsafe_allow_html=True)
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
        if match and match.get("rating"):
            item["rated"] = int(match["rating"])
    if item.get("interaction_id"):
        rating_widget(item, key)


# ------------------------------------------------------------------ page: system check
def page_check():
    header("System check", "Shows which connections are set up and lets you test each one.")
    p = st.session_state.profile

    def row(label, ok, detail):
        c1, c2 = st.columns([1, 3])
        c1.markdown(f"**{label}**")
        c2.markdown(f"{'🟢' if ok else '🔴'} {detail}")

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
page = profile_sidebar()
{
    "Ask the research": page_chat,
    "Automations": page_automations,
    "Knowledge base": page_kb,
    "Delivery log": page_log,
    "Analytics": page_analytics,
    "System check": page_check,
}[page]()
