"""EHR / Document MCP server — the system of record agents read from and write to (port of lib/services/ehr.ts
plus the audit trail formerly written by lib/agents/events.ts)."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from mcp_servers.common import create_server, ok

from sqlalchemy import delete, select

from app.core.db import session_scope
from app.core.util import dumps, now, parse_json
from app.models import Alert, Appointment, AgentEvent, CarePlan, CareTask, Document, MedicationDose, Observation, Patient, Referral

mcp = create_server("carexhealth-ehr", "Hospital EHR & document store: patient records, longitudinal context, clinical documents and the audit trail.")

AGENTS = {"PLANNING", "EXECUTION", "MONITORING", "COMMUNICATION", "INTELLIGENCE", "SERVICE", "HUMAN"}


def _patient(p: Patient) -> dict[str, Any]:
    d = p.to_dict()
    d["user"] = p.user.lite()
    d["doctor"] = p.doctor.lite()
    d["nurse"] = p.nurse.lite() if p.nurse else None
    return d


def _active_items(s, patient_id: str) -> list[dict[str, Any]]:  # noqa: ANN001
    plans = s.scalars(select(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.status == "ACTIVE").order_by(CarePlan.created_at)).all()
    out = []
    for p in plans:
        for i in p.items:
            if i.included:
                d = i.to_dict()
                d.update(planId=p.id, planKind=p.kind, detailsObj=parse_json(i.details, {}))
                out.append(d)
    return out


@mcp.tool()
def get_patient_records(patient_id: str) -> dict:
    """Patient demographics with treating doctor and assigned nurse."""
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        return ok(patient=_patient(p) if p else None)


@mcp.tool()
def get_active_plan_items(patient_id: str) -> dict:
    """All approved care-plan items currently in force (initial plan + approved amendments)."""
    with session_scope() as s:
        return ok(items=_active_items(s, patient_id))


@mcp.tool()
def get_patient_context(patient_id: str) -> dict:
    """Full longitudinal context (plan, doses, appointments, referrals, observations, alerts, labs, tasks, adherence, latest vitals)."""
    t = now()
    since = t - timedelta(days=7)
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if p is None:
            raise ValueError("Patient not found")
        doses = s.scalars(select(MedicationDose).where(MedicationDose.patient_id == patient_id, MedicationDose.scheduled_at >= since, MedicationDose.scheduled_at <= t + timedelta(days=1)).order_by(MedicationDose.scheduled_at)).all()
        appts = s.scalars(select(Appointment).where(Appointment.patient_id == patient_id, Appointment.status != "CANCELLED").order_by(Appointment.starts_at)).unique().all()
        refs = s.scalars(select(Referral).where(Referral.patient_id == patient_id)).unique().all()
        ref_appts = s.scalars(select(Appointment).where(Appointment.referral_id.in_([r.id for r in refs]))).unique().all() if refs else []
        obs = s.scalars(select(Observation).where(Observation.patient_id == patient_id, Observation.recorded_at >= since).order_by(Observation.recorded_at.desc())).unique().all()
        alerts = s.scalars(select(Alert).where(Alert.patient_id == patient_id).order_by(Alert.created_at.desc()).limit(20)).unique().all()
        labs = s.scalars(select(Document).where(Document.patient_id == patient_id, Document.type == "LAB_REPORT").order_by(Document.created_at.desc()).limit(5)).unique().all()
        tasks = s.scalars(select(CareTask).where(CareTask.patient_id == patient_id).order_by(CareTask.due_date)).all()

        past = [d for d in doses if d.scheduled_at <= t and d.status != "CANCELLED"]
        adherence = round(len([d for d in past if d.status == "TAKEN"]) / len(past) * 100) if past else None
        latest: dict[str, Any] = {}
        for o in obs:
            if o.type not in ("SYMPTOM", "NURSE_NOTE") and o.type not in latest:
                latest[o.type] = o.to_dict()

        def appt(a: Appointment) -> dict[str, Any]:
            d = a.to_dict()
            d["provider"] = a.provider.to_dict()
            return d

        referrals = []
        for r in refs:
            d = r.to_dict()
            d["provider"] = r.provider.to_dict() if r.provider else None
            d["appointments"] = [a.to_dict() for a in ref_appts if a.referral_id == r.id]
            referrals.append(d)
        return ok(
            patient=_patient(p),
            items=_active_items(s, patient_id),
            doses=[d.to_dict() for d in doses],
            appointments=[appt(a) for a in appts],
            referrals=referrals,
            observations=[o.to_dict() for o in obs],
            alerts=[a.to_dict() for a in alerts],
            labs=[d.to_dict() for d in labs],
            tasks=[x.to_dict() for x in tasks],
            adherence=adherence,
            latestVitals=latest,
            now=t.isoformat(),
        )


@mcp.tool()
def store_document(
    patient_id: str,
    type: str,  # noqa: A002
    title: str,
    content: str,
    data: Any = None,
    visible_to_patient: bool = False,
    shared_with_provider_id: str | None = None,
    task_id: str | None = None,
    review_status: str | None = None,
    created_by_id: str | None = None,
    engine: str | None = None,
    replace_existing_of_type: bool = False,
) -> dict:
    """Store a clinical document (markdown content + optional structured JSON data). Optionally replaces the patient's previous document of the same type."""
    with session_scope() as s:
        if replace_existing_of_type:
            s.execute(delete(Document).where(Document.patient_id == patient_id, Document.type == type))
        doc = Document(
            patient_id=patient_id,
            type=type,
            title=title,
            content=content,
            data=None if data is None else dumps(data),
            visible_to_patient=visible_to_patient,
            shared_with_provider_id=shared_with_provider_id,
            task_id=task_id,
            review_status=review_status,
            created_by_id=created_by_id,
            engine=engine,
        )
        s.add(doc)
        s.flush()
        return ok(document=doc.to_dict())


@mcp.tool()
def get_documents(patient_id: str, types: list[str] | None = None, limit: int = 20, include_data: bool = True) -> dict:
    """A patient's documents, newest first."""
    with session_scope() as s:
        q = select(Document).where(Document.patient_id == patient_id)
        if types:
            q = q.where(Document.type.in_(types))
        docs = s.scalars(q.order_by(Document.created_at.desc()).limit(limit)).unique().all()
        return ok(documents=[d.to_dict(exclude=() if include_data else ("data",)) for d in docs])


@mcp.tool()
def get_document(document_id: str) -> dict:
    """One document by id."""
    with session_scope() as s:
        d = s.get(Document, document_id)
        return ok(document=d.to_dict() if d else None)


@mcp.tool()
def update_patient_record(patient_id: str, status: str | None = None, discharge_date: str | None = None, risk_level: str | None = None, nurse_id: str | None = None) -> dict:
    """Update the patient's record: care status, discharge date, risk level or assigned nurse."""
    from app.core.util import parse_dt

    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if p is None:
            raise ValueError("Patient not found")
        if status is not None:
            p.status = status
        if discharge_date is not None:
            p.discharge_date = parse_dt(discharge_date)
        if risk_level is not None:
            p.risk_level = risk_level
        if nurse_id is not None:
            p.nurse_id = nurse_id
        s.flush()
        return ok(patient=_patient(p))


@mcp.tool()
def create_audit_event(agent: str, action: str, patient_id: str | None = None, detail: str | None = None, level: str = "INFO") -> dict:
    """Append to the auditable agent-activity log (agent actions, human approvals, bookings, alerts, escalations, documents...)."""
    if agent not in AGENTS:
        raise ValueError(f"Unknown agent {agent}")
    with session_scope() as s:
        e = AgentEvent(agent=agent, action=action, patient_id=patient_id, detail=detail, level=level)
        s.add(e)
        s.flush()
        return ok(eventId=e.id)


if __name__ == "__main__":
    mcp.run("stdio")
