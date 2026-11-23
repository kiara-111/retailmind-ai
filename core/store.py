"""Storage for automations and the delivery log.

Uses Supabase (shared between the web app and the scheduler) when configured,
otherwise a local JSON file so the app can be tried on a laptop.
"""
import json
import os
import re
import uuid

import requests

from . import config, schedule

LOCAL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".local_store.json")


def backend() -> str:
    return "supabase" if config.has("SUPABASE_URL", "SUPABASE_KEY") else "local"


# ---------- Supabase ----------
def _sb(method: str, table: str, params=None, body=None):
    key = config.get("SUPABASE_KEY")
    base = config.get("SUPABASE_URL").strip().rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    if base.endswith("/rest/v1"):
        base = base[: -len("/rest/v1")]
    url = base + f"/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if key.startswith("eyJ"):  # legacy service_role JWT; new sb_secret_ keys only go in the apikey header
        headers["Authorization"] = f"Bearer {key}"
    host = re.sub(r"^https?://", "", base).split("/")[0]
    if not re.fullmatch(r"[a-z0-9]{15,30}\.supabase\.co", host):
        raise RuntimeError(
            f"SUPABASE_URL looks wrong ('{host}'). It must have exactly this form: "
            "https://<project-id>.supabase.co  (the project id is the code after /project/ in your Supabase dashboard address)."
        )
    r = requests.request(method, url, headers=headers, params=params, json=body, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase {r.status_code}: {r.text[:300]}")
    if not r.text:
        return []
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(
            f"Supabase answered with a web page instead of data (status {r.status_code}, "
            f"{r.headers.get('content-type', 'unknown type')}). Check SUPABASE_URL: it must be https://<project-id>.supabase.co"
        )


# ---------- local file ----------
def _read():
    if not os.path.exists(LOCAL_FILE):
        return {"subscriptions": [], "deliveries": [], "interactions": []}
    with open(LOCAL_FILE, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("interactions", [])
    return data


def _write(data):
    with open(LOCAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


# ---------- public API ----------
def add_subscription(sub: dict) -> dict:
    sub = dict(sub)
    sub["email"] = sub["email"].strip().lower()
    sub.setdefault("active", True)
    sub.setdefault("covered_ids", [])
    sub["next_run_at"] = schedule.iso(schedule.next_run(sub))
    if backend() == "supabase":
        return _sb("POST", "subscriptions", body=sub)[0]
    data = _read()
    sub["id"] = str(uuid.uuid4())
    sub["created_at"] = schedule.iso(schedule.now_utc())
    sub.setdefault("last_run_at", None)
    data["subscriptions"].append(sub)
    _write(data)
    return sub


def list_subscriptions(email: str) -> list:
    email = email.strip().lower()
    if backend() == "supabase":
        return _sb("GET", "subscriptions", {"select": "*", "email": f"eq.{email}", "order": "created_at.asc"})
    return [s for s in _read()["subscriptions"] if s["email"] == email]


def due_subscriptions() -> list:
    now = schedule.iso(schedule.now_utc())
    if backend() == "supabase":
        return _sb("GET", "subscriptions", {"select": "*", "active": "eq.true", "next_run_at": f"lte.{now}"})
    return [s for s in _read()["subscriptions"] if s.get("active") and s["next_run_at"] <= now]


def update_subscription(sub_id: str, changes: dict):
    if backend() == "supabase":
        _sb("PATCH", "subscriptions", {"id": f"eq.{sub_id}"}, changes)
        return
    data = _read()
    for s in data["subscriptions"]:
        if s["id"] == sub_id:
            s.update(changes)
    _write(data)


def delete_subscription(sub_id: str):
    if backend() == "supabase":
        _sb("DELETE", "subscriptions", {"id": f"eq.{sub_id}"})
        return
    data = _read()
    data["subscriptions"] = [s for s in data["subscriptions"] if s["id"] != sub_id]
    _write(data)


def telegram_chat_id(email: str) -> str:
    """Telegram chat id saved with this person's automations (stored in the column named whatsapp)."""
    for s in list_subscriptions(email):
        value = str(s.get("whatsapp") or "")
        if value.lstrip("-").isdigit():
            return value
    return ""


def set_telegram_chat_id(email: str, chat_id: str):
    email = email.strip().lower()
    if backend() == "supabase":
        _sb("PATCH", "subscriptions", {"email": f"eq.{email}"}, {"whatsapp": chat_id})
        return
    data = _read()
    for s in data["subscriptions"]:
        if s["email"] == email:
            s["whatsapp"] = chat_id
    _write(data)


def log_delivery(entry: dict):
    entry = dict(entry)
    entry["email"] = entry["email"].strip().lower()
    if backend() == "supabase":
        _sb("POST", "deliveries", body=entry)
        return
    data = _read()
    entry["id"] = str(uuid.uuid4())
    entry["created_at"] = schedule.iso(schedule.now_utc())
    data["deliveries"].append(entry)
    _write(data)


def list_deliveries(email: str, limit: int = 30) -> list:
    email = email.strip().lower()
    if backend() == "supabase":
        return _sb(
            "GET", "deliveries",
            {"select": "*", "email": f"eq.{email}", "order": "created_at.desc", "limit": str(limit)},
        )
    rows = [d for d in _read()["deliveries"] if d["email"] == email]
    return sorted(rows, key=lambda d: d["created_at"], reverse=True)[:limit]


# ---------- interactions (answers and their evaluation) ----------
def log_interaction(entry: dict) -> str:
    entry = dict(entry)
    entry["email"] = (entry.get("email") or "anonymous").strip().lower()
    if backend() == "supabase":
        return _sb("POST", "interactions", body=entry)[0]["id"]
    data = _read()
    entry["id"] = str(uuid.uuid4())
    entry["created_at"] = schedule.iso(schedule.now_utc())
    data["interactions"].append(entry)
    _write(data)
    return entry["id"]


def update_interaction(interaction_id: str, changes: dict):
    if backend() == "supabase":
        _sb("PATCH", "interactions", {"id": f"eq.{interaction_id}"}, changes)
        return
    data = _read()
    for row in data["interactions"]:
        if row["id"] == interaction_id:
            row.update(changes)
    _write(data)


def list_interactions(limit: int = 1000) -> list:
    if backend() == "supabase":
        return _sb("GET", "interactions", {"select": "*", "order": "created_at.desc", "limit": str(limit)})
    rows = sorted(_read()["interactions"], key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def all_deliveries(limit: int = 1000) -> list:
    if backend() == "supabase":
        return _sb("GET", "deliveries", {"select": "id,created_at,channel,format,trigger,status", "order": "created_at.desc", "limit": str(limit)})
    return sorted(_read()["deliveries"], key=lambda d: d["created_at"], reverse=True)[:limit]


def ping() -> str:
    if backend() == "supabase":
        _sb("GET", "subscriptions", {"select": "id", "limit": "1"})
        _sb("GET", "deliveries", {"select": "id", "limit": "1"})
        try:
            _sb("GET", "interactions", {"select": "id", "limit": "1"})
        except RuntimeError:
            return "Supabase reachable. The analytics table is missing: run supabase_analytics.sql once in the SQL Editor."
        return "Supabase reachable, all three tables found."
    return "Local file storage (only for trying things out on one computer)."
