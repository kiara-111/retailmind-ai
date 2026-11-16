"""Timing logic for automations. All times are entered in Europe/Berlin and stored in UTC."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TIMEZONE)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _at_hour(day, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=TZ)


def next_run(sub: dict, after: datetime = None) -> datetime:
    """Next send time strictly after `after`."""
    after = after or now_utc()
    local = after.astimezone(TZ)
    hour = int(sub.get("hour", 8))
    freq = sub.get("freq_type", "weekly")

    if freq == "every_n_days" and sub.get("next_run_at"):
        step = timedelta(days=max(1, int(sub.get("interval_days") or 3)))
        prev_local = parse(sub["next_run_at"]).astimezone(TZ)
        candidate = _at_hour(prev_local.date(), hour)
        while candidate <= after:
            candidate = _at_hour((candidate + step).date(), hour)
        return candidate.astimezone(timezone.utc)

    for offset in range(0, 9):
        day = (local + timedelta(days=offset)).date()
        candidate = _at_hour(day, hour)
        if candidate <= after:
            continue
        if freq == "weekly" and candidate.weekday() != int(sub.get("weekday", 0)):
            continue
        return candidate.astimezone(timezone.utc)
    raise ValueError("Could not compute next run")


def describe(sub: dict) -> str:
    hour = f"{int(sub.get('hour', 8)):02d}:00"
    freq = sub.get("freq_type")
    if freq == "daily":
        return f"Every day at {hour}"
    if freq == "every_n_days":
        return f"Every {int(sub.get('interval_days') or 3)} days at {hour}"
    return f"Every {WEEKDAYS[int(sub.get('weekday', 0))]} at {hour}"


def local_str(ts: str) -> str:
    if not ts:
        return "never"
    return parse(ts).astimezone(TZ).strftime("%a %d %b %Y, %H:%M")
