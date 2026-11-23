"""Storage for automations and the delivery log.

Uses Supabase (shared between the web app and the scheduler) when configured,
otherwise a local JSON file so the app can be tried on a laptop.
"""
import json
import os
import uuid

import requests

from . import config, schedule

LOCAL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".local_store.json")


def backend() -> str:
    return "supabase" if config.has("SUPABASE_URL", "SUPABASE_KEY") else "local"


# ---------- Supabase ----------
def _sb(method: str, table: str, params=None, body=None):
    key = config.get("SUPABASE_KEY")
    base = config.get("SUPABASE_URL").rstrip("/")
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
    r = requests.request(method, url, headers=headers, params=params, json=body, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else []


# ---------- local file ----------
def _read():
    if not os.path.exists(LOCAL_FILE):
        return {"subscriptions": [], "deliveries": []}
    with open(LOCAL_FILE, encoding="utf-8") as f:
        return json.load(f)


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


def ping() -> str:
    if backend() == "supabase":
        _sb("GET", "subscriptions", {"select": "id", "limit": "1"})
        _sb("GET", "deliveries", {"select": "id", "limit": "1"})
        return "Supabase reachable, both tables found."
    return "Local file storage (only for trying things out on one computer)."
