"""Care tasks and medication doses (Execution agent state)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update

from app.core.db import session_scope
from app.core.util import dumps, now
from app.models import CareTask, MedicationDose


def create_task(**fields: Any) -> CareTask:
    if "meta" in fields and not isinstance(fields["meta"], str):
        fields["meta"] = dumps(fields["meta"])
    with session_scope() as s:
        t = CareTask(**fields)
        s.add(t)
        s.flush()
        return t


def get_task(task_id: str) -> CareTask | None:
    with session_scope() as s:
        return s.get(CareTask, task_id)


def update_task(task_id: str, **fields: Any) -> None:
    if "meta" in fields and not isinstance(fields["meta"], str):
        fields["meta"] = dumps(fields["meta"])
    with session_scope() as s:
        t = s.get(CareTask, task_id)
        if t:
            for k, v in fields.items():
                setattr(t, k, v)


def tasks_for_item(item_id: str) -> list[CareTask]:
    with session_scope() as s:
        return list(s.scalars(select(CareTask).where(CareTask.item_id == item_id)))


def active_medication_tasks(patient_id: str) -> list[CareTask]:
    with session_scope() as s:
        return list(s.scalars(select(CareTask).where(CareTask.patient_id == patient_id, CareTask.type == "MEDICATION", CareTask.status.in_(["IN_PROGRESS", "PENDING", "SCHEDULED"]))))


def cancel_open_tasks(patient_id: str) -> None:
    with session_scope() as s:
        s.execute(update(CareTask).where(CareTask.patient_id == patient_id, CareTask.status.in_(["PENDING", "SCHEDULED"])).values(status="CANCELLED"))


def create_doses(patient_id: str, task_id: str, medication: str, dose: str | None, times: list[datetime]) -> None:
    with session_scope() as s:
        s.add_all([MedicationDose(patient_id=patient_id, task_id=task_id, medication=medication, dose=dose, scheduled_at=t) for t in times])


def cancel_pending_doses(*, patient_id: str | None = None, task_id: str | None = None) -> int:
    with session_scope() as s:
        q = update(MedicationDose).where(MedicationDose.status == "PENDING")
        q = q.where(MedicationDose.patient_id == patient_id) if patient_id else q.where(MedicationDose.task_id == task_id)
        return s.execute(q.values(status="CANCELLED")).rowcount or 0


def get_dose(dose_id: str) -> MedicationDose | None:
    with session_scope() as s:
        return s.get(MedicationDose, dose_id)


def record_dose(dose_id: str, status: str, note: str | None) -> MedicationDose:
    with session_scope() as s:
        d = s.get(MedicationDose, dose_id)
        assert d is not None
        d.status, d.recorded_at, d.note = status, now(), note
        return d


def overdue_doses(cutoff: datetime) -> list[MedicationDose]:
    with session_scope() as s:
        return list(s.scalars(select(MedicationDose).where(MedicationDose.status == "PENDING", MedicationDose.scheduled_at < cutoff)))


def mark_dose(dose_id: str, status: str) -> None:
    with session_scope() as s:
        d = s.get(MedicationDose, dose_id)
        if d:
            d.status = status


def complete_finished_courses() -> None:
    """Close medication tasks that have no pending doses left."""
    with session_scope() as s:
        for t in s.scalars(select(CareTask).where(CareTask.type == "MEDICATION", CareTask.status == "IN_PROGRESS")):
            left = s.scalar(select(func.count()).select_from(MedicationDose).where(MedicationDose.task_id == t.id, MedicationDose.status == "PENDING"))
            if left == 0:
                t.status = "COMPLETED"


def doses_due_for_reminder(t: datetime) -> list[MedicationDose]:
    with session_scope() as s:
        return list(
            s.scalars(
                select(MedicationDose).where(
                    MedicationDose.status == "PENDING",
                    MedicationDose.reminder_sent.is_(False),
                    MedicationDose.scheduled_at <= t + timedelta(minutes=30),
                    MedicationDose.scheduled_at >= t - timedelta(minutes=60),
                )
            )
        )


def mark_reminded(dose_id: str) -> None:
    with session_scope() as s:
        d = s.get(MedicationDose, dose_id)
        if d:
            d.reminder_sent = True


def missed_or_skipped(patient_id: str, since: datetime, until: datetime) -> list[MedicationDose]:
    with session_scope() as s:
        return list(
            s.scalars(
                select(MedicationDose).where(
                    MedicationDose.patient_id == patient_id,
                    or_(
                        (MedicationDose.status == "MISSED") & (MedicationDose.scheduled_at >= since) & (MedicationDose.scheduled_at <= until),
                        (MedicationDose.status == "SKIPPED") & (MedicationDose.recorded_at >= since),
                    ),
                )
            )
        )
