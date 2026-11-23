"""RetailMind AI: research on demand for marketing leaders. Student prototype (CBS)."""
import re

import streamlit as st

from core import channels, config, engine, kb, llm, schedule, store

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
            ["Ask the research", "Automations", "Knowledge base", "Delivery log", "System check"],
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
    st.link_button("Open RetailMind in Telegram", link, use_container_width=True)
    st.caption(f"No QR scanner? In Telegram open @{channels.bot_username()} and send:")
    st.code(f"/start {channels.connect_code(p['email'])}", language=None)
    if st.button("Check connection", use_container_width=True):
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
            if col.button(ex, use_container_width=True):
                st.session_state.pending_question = ex
                st.rerun()
    for m in chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("sources"):
                with st.expander(f"References, APA 7 ({len(m['sources'])})"):
                    source_list(m["sources"])
    question = st.chat_input("Ask a question about consumer psychology in retail") or st.session_state.pop("pending_question", None)
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        pool = kb.by_topics(selected)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Reading the knowledge base"):
                    answer, ids = llm.answer_with_citations(question, pool, chat)
            except Exception as exc:
                st.error(f"The language model could not be reached: {exc}")
                return
            st.markdown(answer)
            if ids:
                with st.expander(f"References, APA 7 ({len(ids)})"):
                    source_list(ids)
        chat.append({"role": "user", "content": question})
        chat.append({"role": "assistant", "content": answer, "sources": ids})
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
            if c2.button("Add", key=f"preset_{label}", use_container_width=True):
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
            if c1.button("Send now", key=f"now_{s['id']}", type="primary", use_container_width=True):
                with st.spinner("Writing and sending"):
                    st.session_state[f"result_{s['id']}"] = engine.run(s, trigger="manual")
            if c2.button("Resume" if not s.get("active") else "Pause", key=f"tog_{s['id']}", use_container_width=True):
                changes = {"active": not s.get("active")}
                if changes["active"]:
                    changes["next_run_at"] = schedule.iso(schedule.next_run({**s, "next_run_at": None}))
                store.update_subscription(s["id"], changes)
                st.rerun()
            if c3.button("Delete", key=f"del_{s['id']}", use_container_width=True):
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
    if c1.button("Test language model", use_container_width=True):
        try:
            st.success("Model answered: " + llm.ask("Reply with the single word READY.", [{"role": "user", "content": "Status?"}], 300))
        except Exception as exc:
            st.error(str(exc))
    if c2.button("Test storage", use_container_width=True):
        try:
            st.success(store.ping())
        except Exception as exc:
            st.error(str(exc))
    if c3.button("Send test email", use_container_width=True, disabled=not p["email"]):
        try:
            st.success(channels.send_email(p["email"], "RetailMind AI | Test", "Email delivery works."))
        except Exception as exc:
            st.error(str(exc))
    if c4.button("Send test Telegram", use_container_width=True, disabled=not p.get("telegram")):
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
    "System check": page_check,
}[page]()
