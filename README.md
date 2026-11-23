# RetailMind AI

Research on demand for marketing leaders. A language model answers questions and writes recurring briefings strictly from a curated set of peer reviewed articles on consumer psychology. Users choose topic, timing and channel.

Student prototype, CBS International Business School. Not an official REWE product.

| Part | File | Runs on |
|---|---|---|
| Web app (chat, automations, knowledge base, log, system check) | `app.py` | Streamlit Community Cloud |
| Knowledge base | `knowledge_base.xlsx` | in this repository |
| Grounded generation | `core/llm.py`, `core/engine.py` | Anthropic API |
| Channels: email, Telegram, LinkedIn draft | `core/channels.py` | SMTP, Telegram Bot API |
| Storage | `core/store.py`, `supabase_setup.sql` | Supabase |
| Scheduler | `scheduler.py`, `.github/workflows/scheduler.yml` | GitHub Actions |

Setup: see `ANLEITUNG_EINRICHTUNG.md` (German).

Try it locally without any accounts: `pip install -r requirements.txt` then `streamlit run app.py`. Storage then uses a local file and only the knowledge base page works without keys.
