"""Small shared helpers: ids, JSON columns, local-time handling, date formatting (date-fns equivalents)."""
from __future__ import annotations

import json
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Any

# Times are stored as naive *local* datetimes, matching the legacy app (which used local `setHours`).


def new_id() -> str:
    return "c" + secrets.token_hex(12)


def now() -> datetime:
    return datetime.now().replace(microsecond=(datetime.now().microsecond // 1000) * 1000)


def start_of_day(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def add_days(d: datetime, n: float) -> datetime:
    return d + timedelta(days=n)


def _local(d: datetime) -> datetime:
    """Attach / convert to the local zone. Windows cannot convert pre-1970 instants, so fall back to today's offset."""
    try:
        return d.astimezone()
    except (OSError, OverflowError, ValueError):
        tz = datetime.now().astimezone().tzinfo
        return d.replace(tzinfo=tz) if d.tzinfo is None else d.astimezone(tz)


def iso(d: datetime | date | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return (d if d.tzinfo else _local(d)).isoformat(timespec="milliseconds")
    return d.isoformat()


def parse_dt(v: str | datetime | None) -> datetime | None:
    """ISO string (with or without offset) → naive local datetime."""
    if v is None or isinstance(v, datetime):
        return v
    s = v.strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return _local(d).replace(tzinfo=None) if d.tzinfo else d


def parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def extract_json(text: str) -> Any:
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.I).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        m = re.search(r"[\[{]", cleaned)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if m and end > m.start():
            return json.loads(cleaned[m.start() : end + 1])
        raise ValueError("No JSON found in model output") from None


def camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


# ---- date-fns style formatting used in agent messages -------------------------------------------


def _h(d: datetime) -> str:
    return f"{(d.hour % 12) or 12}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def fmt(d: datetime) -> str:
    """'EEE d MMM, h:mm a'"""
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}, {_h(d)}"


def fmt_time(d: datetime) -> str:
    return _h(d)


def fmt_day(d: datetime) -> str:
    """'d MMM'"""
    return f"{d.day} {d.strftime('%b')}"


def fmt_date(d: datetime) -> str:
    """'d MMM yyyy'"""
    return f"{d.day} {d.strftime('%b')} {d.year}"


def fmt_date_time(d: datetime) -> str:
    """'d MMM yyyy, h:mm a'"""
    return f"{fmt_date(d)}, {_h(d)}"


def when(d: datetime) -> str:
    today = start_of_day(now())
    if start_of_day(d) == today:
        return f"Today, {_h(d)}"
    if start_of_day(d) == today + timedelta(days=1):
        return f"Tomorrow, {_h(d)}"
    return fmt(d)


def is_today(d: datetime) -> bool:
    return start_of_day(d) == start_of_day(now())


def distance(d: datetime) -> str:
    """Rough formatDistanceToNow equivalent."""
    secs = abs((now() - d).total_seconds())
    if secs < 60:
        return "less than a minute"
    mins = round(secs / 60)
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''}"
    hrs = round(mins / 60)
    if hrs < 24:
        return f"about {hrs} hour{'s' if hrs != 1 else ''}"
    days = round(hrs / 24)
    return f"{days} day{'s' if days != 1 else ''}"


def age_years(dob: datetime) -> int:
    return int((now() - dob).total_seconds() // (365.25 * 86400))
