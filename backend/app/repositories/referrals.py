"""Referrals (Execution agent state; appointments themselves belong to the Scheduling service)."""
from __future__ import annotations

from typing import Any

from app.core.db import session_scope
from app.core.util import dumps, now, parse_json
from app.models import Referral


def create(**fields: Any) -> Referral:
    with session_scope() as s:
        r = Referral(**fields)
        s.add(r)
        s.flush()
        return r


def get(referral_id: str) -> Referral | None:
    with session_scope() as s:
        return s.get(Referral, referral_id)


def by_task(task_id: str) -> Referral | None:
    from sqlalchemy import select

    with session_scope() as s:
        return s.scalars(select(Referral).where(Referral.task_id == task_id)).first()


def update(referral_id: str, **fields: Any) -> Referral:
    with session_scope() as s:
        r = s.get(Referral, referral_id)
        assert r is not None
        for k, v in fields.items():
            setattr(r, k, v)
        return r


def push_timeline(referral_id: str, status: str, note: str | None = None, **extra: Any) -> Referral:
    """Status change + timeline entry (Created → Sent → Accepted → Scheduled → In treatment → Completed)."""
    with session_scope() as s:
        r = s.get(Referral, referral_id)
        assert r is not None
        timeline = parse_json(r.timeline, [])
        entry: dict[str, Any] = {"status": status, "at": now().astimezone().isoformat(timespec="milliseconds")}
        if note is not None:
            entry["note"] = note
        timeline.append(entry)
        r.status, r.timeline = status, dumps(timeline)
        for k, v in extra.items():
            setattr(r, k, v)
        return r
