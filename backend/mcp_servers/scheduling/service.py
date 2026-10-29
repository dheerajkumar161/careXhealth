"""Hospital Scheduling Service — provider availability and slot booking (port of lib/services/scheduling.ts)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.util import parse_dt, start_of_day
from app.models import Appointment, Provider

ACTIVE = ("TENTATIVE", "BOOKED", "COMPLETED")

Slot = tuple[datetime, datetime]

PATTERN: dict[int, list[int]] = {1: [2], 2: [1, 4], 3: [1, 3, 5], 4: [1, 2, 4, 5], 5: [1, 2, 3, 4, 5], 6: [1, 2, 3, 4, 5, 6], 7: [0, 1, 2, 3, 4, 5, 6]}


def js_weekday(d: datetime) -> int:
    """JS getDay(): 0 = Sunday."""
    return (d.weekday() + 1) % 7


def _busy(s: Session, provider_id: str, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    rows = s.execute(
        select(Appointment.starts_at, Appointment.ends_at).where(
            Appointment.provider_id == provider_id, Appointment.status.in_(ACTIVE), Appointment.starts_at < end, Appointment.ends_at > start
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


def _day_slots(p: Provider, day: datetime) -> list[Slot]:
    out: list[Slot] = []
    t = day.replace(hour=p.work_start_hour, minute=0, second=0, microsecond=0)
    end = day.replace(hour=p.work_end_hour, minute=0, second=0, microsecond=0)
    step = timedelta(minutes=p.slot_minutes)
    while t + step <= end:
        out.append((t, t + step))
        t += step
    return out


def _work_days(p: Provider) -> list[int]:
    return [int(x) for x in p.work_days.split(",") if x.strip()]


def _overlaps(slot: Slot, taken: list[tuple[datetime, datetime]]) -> bool:
    return any(b[0] < slot[1] and b[1] > slot[0] for b in taken)


def find_slots(s: Session, provider_id: str, start: datetime, count: int = 3, horizon_days: int = 21, not_before: datetime | None = None) -> list[Slot]:
    """First free slots on or after `start` (searches up to `horizon_days`)."""
    p = s.get(Provider, provider_id)
    if p is None:
        raise ValueError("Provider not found")
    not_before = not_before or datetime.now()
    horizon = start + timedelta(days=horizon_days)
    taken = _busy(s, provider_id, start, horizon)
    result: list[Slot] = []
    day = start_of_day(start)
    while day < horizon and len(result) < count:
        if js_weekday(day) in _work_days(p):
            for slot in _day_slots(p, day):
                if slot[0] < start or slot[0] < not_before or _overlaps(slot, taken):
                    continue
                result.append(slot)
                if len(result) >= count:
                    break
        day += timedelta(days=1)
    return result


def find_series_slots(s: Session, provider_id: str, start: datetime, sessions: int, per_week: int, not_before: datetime | None = None) -> list[Slot]:
    """Finds a recurring series (e.g. 12 sessions at 3/week), keeping a consistent time where possible."""
    p = s.get(Provider, provider_id)
    if p is None:
        raise ValueError("Provider not found")
    not_before = not_before or datetime.now()
    wanted = [d for d in PATTERN.get(min(max(per_week, 1), 7), [1, 3, 5]) if d in _work_days(p)]
    days = wanted or _work_days(p)
    horizon = start + timedelta(days=(math.ceil(sessions / max(per_week, 1)) + 6) * 7)
    taken = _busy(s, provider_id, start, horizon)
    preferred_hour = min(p.work_start_hour + 1, p.work_end_hour - 1)
    out: list[Slot] = []
    day = start_of_day(start)
    while len(out) < sessions and day < horizon:
        if js_weekday(day) in days:
            free = [sl for sl in _day_slots(p, day) if sl[0] >= start and sl[0] >= not_before and not _overlaps(sl, taken)]
            pick = next((sl for sl in free if sl[0].hour >= preferred_hour), free[0] if free else None)
            if pick:
                out.append(pick)
        day += timedelta(days=1)
    return out


def book(
    s: Session,
    *,
    patient_id: str,
    provider_id: str,
    start: datetime,
    end: datetime,
    kind: str,
    title: str,
    task_id: str | None = None,
    referral_id: str | None = None,
    sequence: int | None = None,
    status: str = "BOOKED",
    rescheduled_from_id: str | None = None,
) -> Appointment:
    provider = s.get(Provider, provider_id)
    if provider is None:
        raise ValueError("Provider not found")
    if _busy(s, provider_id, start, end):
        raise ValueError("Slot no longer available")
    appt = Appointment(
        patient_id=patient_id,
        provider_id=provider_id,
        task_id=task_id,
        referral_id=referral_id,
        kind=kind,
        title=title,
        starts_at=start,
        ends_at=end,
        location=f"{provider.organization}, {provider.location}",
        sequence=sequence,
        status=status,
        rescheduled_from_id=rescheduled_from_id,
    )
    s.add(appt)
    s.flush()
    return appt


def slot_dict(slot: Slot) -> dict[str, str]:
    from app.core.util import iso

    return {"start": iso(slot[0]), "end": iso(slot[1])}  # type: ignore[dict-item]


def parse_slot(v: dict) -> Slot:
    return parse_dt(v["start"]), parse_dt(v["end"])  # type: ignore[return-value]
