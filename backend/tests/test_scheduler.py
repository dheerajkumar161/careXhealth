"""APScheduler: persistent jobs in SQLite, restart persistence, and each job body."""
from datetime import timedelta
from functools import partial

from conftest import draft_and_approve

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Appointment, MedicationDose


def test_jobs_persist_across_restart(fresh):  # noqa: ANN001
    import asyncio

    from app.scheduler.jobs import JOBS
    from app.scheduler.scheduler import build_scheduler, register_jobs

    async def first_boot() -> dict:
        s = build_scheduler()
        s.start(paused=True)
        register_jobs(s, 60)
        runs = {j.id: j.next_run_time for j in s.get_jobs()}
        s.shutdown(wait=False)
        return runs

    async def second_boot() -> tuple[dict, int]:
        s = build_scheduler()
        s.start(paused=True)
        before = {j.id: j.next_run_time for j in s.get_jobs()}  # rehydrated from SQLite before registering
        register_jobs(s, 60)  # same cadence → no duplicates, next run times preserved
        count = len(s.get_jobs())
        s.shutdown(wait=False)
        return before, count

    runs = asyncio.run(first_boot())
    assert sorted(runs) == sorted(JOBS)
    restored, count = asyncio.run(second_boot())
    assert restored == runs and count == len(JOBS)
    from sqlalchemy import create_engine, text

    with create_engine(get_settings().database_url).connect() as c:
        assert sorted(r[0] for r in c.execute(text("select id from apscheduler_jobs"))) == sorted(JOBS)


def test_reminder_and_missed_dose_jobs(api):  # noqa: ANN001
    from app.agents.orchestrator import orchestrator
    from app.core.util import iso

    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    with session_scope() as s:
        d = s.query(MedicationDose).filter_by(patient_id=pid, status="PENDING").order_by(MedicationDose.scheduled_at).first()
        dose_id, at = d.id, d.scheduled_at
    portal = doctor.c.portal
    assert portal.call(partial(orchestrator.send_due_dose_reminders, iso(at - timedelta(minutes=10)))) >= 1
    assert any(n["type"] == "REMINDER" for n in patient.get("/api/notifications").json()["items"])
    assert portal.call(partial(orchestrator.send_due_dose_reminders, iso(at - timedelta(minutes=10)))) == 0  # reminded once only
    affected = portal.call(partial(orchestrator.mark_overdue_doses, iso(at + timedelta(hours=3))))
    assert affected == [pid]
    with session_scope() as s:
        assert s.get(MedicationDose, dose_id).status == "MISSED"


def test_missed_appointment_job(api):  # noqa: ANN001
    from app.agents.orchestrator import orchestrator

    doctor = api("doctor")
    pid, _ = draft_and_approve(doctor)
    with session_scope() as s:
        fu = s.query(Appointment).filter_by(patient_id=pid, kind="FOLLOW_UP").first()
        from app.core.util import now

        fu.starts_at, fu.ends_at = now() - timedelta(days=3), now() - timedelta(days=3) + timedelta(minutes=20)
        fu_id = fu.id
    assert doctor.c.portal.call(orchestrator.check_missed_appointments) == 1
    with session_scope() as s:
        assert s.get(Appointment, fu_id).status == "MISSED"
    assert any(a["category"] == "APPOINTMENT" for a in doctor.get(f"/api/patients/{pid}").json()["alerts"])


def test_adherence_and_escalation_jobs_via_cycle_workflow(api):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    for d in [d for d in patient.get("/api/overview").json()["doses"] if d["status"] == "PENDING"][:2]:
        with session_scope() as s:  # skipped without triggering the per-dose adherence check
            row = s.get(MedicationDose, d["id"])
            from app.core.util import now

            row.status, row.recorded_at = "SKIPPED", now()
    out = doctor.post("/api/agents/cycle").json()  # MAF cycle workflow: reminders → doses → appointments → adherence → escalation
    assert set(out) == {"reminders", "patientsChecked", "escalated"} and out["patientsChecked"] == 1
    assert any(a["category"] == "ADHERENCE" for a in doctor.get(f"/api/patients/{pid}").json()["alerts"])
    assert api("patient").post("/api/agents/cycle").status_code == 403
