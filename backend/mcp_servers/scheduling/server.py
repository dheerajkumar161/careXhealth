"""Scheduling MCP server — exposes the hospital Scheduling Service as deterministic MCP tools."""
from __future__ import annotations

from typing import Any

from mcp_servers.common import create_server, ok

from sqlalchemy import select

from app.core.db import session_scope
from app.core.util import add_days, now, parse_dt, start_of_day
from app.models import Appointment
from mcp_servers.scheduling import service

mcp = create_server("carexhealth-scheduling", "Hospital Scheduling Service: provider availability, holds, bookings, cancellations and rescheduling.")


def _appt(a: Appointment) -> dict[str, Any]:
    d = a.to_dict()
    d["provider"] = a.provider.to_dict() if a.provider else None
    return d


@mcp.tool()
def find_available_slots(provider_id: str, from_date: str, count: int = 3, horizon_days: int = 21, not_before: str | None = None) -> dict:
    """First free slots for a provider on or after `from_date` (ISO datetime)."""
    with session_scope() as s:
        slots = service.find_slots(s, provider_id, parse_dt(from_date), count, horizon_days, parse_dt(not_before) if not_before else None)
    return ok(slots=[service.slot_dict(x) for x in slots])


@mcp.tool()
def find_series_slots(provider_id: str, from_date: str, sessions: int, per_week: int, not_before: str | None = None) -> dict:
    """A recurring series of free slots (e.g. 12 sessions at 3/week) at a consistent time where possible."""
    with session_scope() as s:
        slots = service.find_series_slots(s, provider_id, parse_dt(from_date), sessions, per_week, parse_dt(not_before) if not_before else None)
    return ok(slots=[service.slot_dict(x) for x in slots])


def _book(status: str, **kw: Any) -> dict:
    with session_scope() as s:
        a = service.book(s, start=parse_dt(kw.pop("start")), end=parse_dt(kw.pop("end")), status=status, **kw)
        s.refresh(a)
        return ok(appointment=_appt(a))


@mcp.tool()
def hold_slot(patient_id: str, provider_id: str, start: str, end: str, kind: str, title: str, task_id: str | None = None, referral_id: str | None = None, sequence: int | None = None) -> dict:
    """Place a TENTATIVE hold on a slot (e.g. while a referral awaits the provider's acceptance)."""
    return _book("TENTATIVE", patient_id=patient_id, provider_id=provider_id, start=start, end=end, kind=kind, title=title, task_id=task_id, referral_id=referral_id, sequence=sequence)


@mcp.tool()
def book_slot(
    patient_id: str,
    provider_id: str,
    start: str,
    end: str,
    kind: str,
    title: str,
    task_id: str | None = None,
    referral_id: str | None = None,
    sequence: int | None = None,
    rescheduled_from_id: str | None = None,
) -> dict:
    """Book a confirmed appointment in a free slot. Fails if the slot is no longer free."""
    return _book(
        "BOOKED", patient_id=patient_id, provider_id=provider_id, start=start, end=end, kind=kind, title=title, task_id=task_id, referral_id=referral_id, sequence=sequence, rescheduled_from_id=rescheduled_from_id
    )


@mcp.tool()
def create_recurring_booking(patient_id: str, provider_id: str, slots: list[dict], kind: str, title_prefix: str, referral_id: str | None = None, task_id: str | None = None, tentative: bool = True) -> dict:
    """Hold (or book) a whole multi-session series; sessions are numbered 1..n."""
    out = []
    with session_scope() as s:
        for seq, slot in enumerate(slots, start=1):
            start, end = service.parse_slot(slot)
            title = f"{title_prefix} session {seq}" if len(slots) > 1 else f"{title_prefix} consultation"
            a = service.book(s, patient_id=patient_id, provider_id=provider_id, start=start, end=end, kind=kind, title=title, task_id=task_id, referral_id=referral_id, sequence=seq, status="TENTATIVE" if tentative else "BOOKED")
            out.append(a.id)
    return ok(appointmentIds=out, count=len(out))


@mcp.tool()
def confirm_bookings(referral_id: str) -> dict:
    """Convert a referral's TENTATIVE holds into BOOKED appointments; returns the booked series in order."""
    with session_scope() as s:
        for a in s.scalars(select(Appointment).where(Appointment.referral_id == referral_id, Appointment.status == "TENTATIVE")):
            a.status = "BOOKED"
        s.flush()
        booked = s.scalars(select(Appointment).where(Appointment.referral_id == referral_id, Appointment.status == "BOOKED").order_by(Appointment.starts_at)).all()
        return ok(appointments=[_appt(a) for a in booked])


@mcp.tool()
def cancel_booking(appointment_ids: list[str] | None = None, referral_id: str | None = None, task_id: str | None = None, statuses: list[str] | None = None) -> dict:
    """Cancel bookings by id, referral or task (optionally only those in the given statuses). Returns what was cancelled."""
    statuses = statuses or ["BOOKED", "TENTATIVE"]
    with session_scope() as s:
        q = select(Appointment).where(Appointment.status.in_(statuses))
        if appointment_ids is not None:
            q = q.where(Appointment.id.in_(appointment_ids))
        if referral_id:
            q = q.where(Appointment.referral_id == referral_id)
        if task_id:
            q = q.where(Appointment.task_id == task_id)
        if appointment_ids is None and not referral_id and not task_id:
            raise ValueError("Specify appointment_ids, referral_id or task_id")
        rows = s.scalars(q).all()
        for a in rows:
            a.status = "CANCELLED"
        return ok(cancelled=[{"id": a.id, "providerId": a.provider_id, "title": a.title} for a in rows])


@mcp.tool()
def complete_booking(appointment_id: str, notes: str | None = None) -> dict:
    """Mark an appointment as attended/completed."""
    with session_scope() as s:
        a = s.get(Appointment, appointment_id)
        if a is None:
            raise ValueError("Appointment not found")
        a.status = "COMPLETED"
        if notes is not None:
            a.notes = notes
        s.flush()
        return ok(appointment=_appt(a))


@mcp.tool()
def reschedule_booking(appointment_id: str, reason: str = "Patient did not attend", horizon_days: int = 21) -> dict:
    """Mark a booking MISSED and book a replacement slot with the same provider (after the series' last session for referrals)."""
    with session_scope() as s:
        appt = s.get(Appointment, appointment_id)
        if appt is None:
            raise ValueError("Appointment not found")
        appt.status = "MISSED"
        appt.notes = reason
        s.flush()
        start = add_days(start_of_day(now()), 1)
        if appt.referral_id:
            last = s.scalars(
                select(Appointment).where(Appointment.referral_id == appt.referral_id, Appointment.status.in_(["BOOKED", "TENTATIVE"])).order_by(Appointment.starts_at.desc())
            ).first()
            if last:
                start = add_days(start_of_day(last.starts_at), 1)
        slots = service.find_slots(s, appt.provider_id, start, 1, horizon_days)
        replacement = None
        if slots:
            title = appt.title if "(rescheduled)" in appt.title else f"{appt.title} (rescheduled)"
            replacement = service.book(
                s,
                patient_id=appt.patient_id,
                provider_id=appt.provider_id,
                start=slots[0][0],
                end=slots[0][1],
                kind=appt.kind,
                title=title,
                task_id=appt.task_id,
                referral_id=appt.referral_id,
                sequence=appt.sequence,
                rescheduled_from_id=appt.id,
            )
            s.flush()
            s.refresh(replacement)
        return ok(appointment=_appt(appt), replacement=_appt(replacement) if replacement else None)


@mcp.tool()
def get_appointment(appointment_id: str) -> dict:
    """Read one appointment with its provider."""
    with session_scope() as s:
        a = s.get(Appointment, appointment_id)
        return ok(appointment=_appt(a) if a else None)


@mcp.tool()
def list_appointments(patient_id: str | None = None, referral_id: str | None = None, task_id: str | None = None, statuses: list[str] | None = None, upcoming_only: bool = False, limit: int = 200) -> dict:
    """List appointments filtered by patient, referral, task and status (ordered by start time)."""
    with session_scope() as s:
        q = select(Appointment)
        if patient_id:
            q = q.where(Appointment.patient_id == patient_id)
        if referral_id:
            q = q.where(Appointment.referral_id == referral_id)
        if task_id:
            q = q.where(Appointment.task_id == task_id)
        if statuses:
            q = q.where(Appointment.status.in_(statuses))
        if upcoming_only:
            q = q.where(Appointment.starts_at >= now())
        rows = s.scalars(q.order_by(Appointment.starts_at).limit(limit)).unique().all()
        return ok(appointments=[_appt(a) for a in rows])


@mcp.tool()
def find_unconfirmed_appointments(older_than_hours: int = 24) -> dict:
    """BOOKED, non-test appointments whose end time passed more than `older_than_hours` ago without attendance being recorded."""
    cutoff = now().timestamp() - older_than_hours * 3600
    with session_scope() as s:
        rows = s.scalars(select(Appointment).where(Appointment.status == "BOOKED", Appointment.kind != "TEST")).unique().all()
        return ok(appointmentIds=[a.id for a in rows if a.ends_at.timestamp() < cutoff])


if __name__ == "__main__":
    mcp.run("stdio")
