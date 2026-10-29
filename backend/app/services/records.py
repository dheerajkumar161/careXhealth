"""Role-scoped read models for dashboards (port of lib/records.ts). Every function enforces what the caller may see.

These are read-only API projections (HTTP layer → repositories), not agent operations.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import PARTNER_ROLES, provider_for
from app.auth.security import SessionUser
from app.core.db import session_scope
from app.core.util import now, parse_json
from app.models import AgentEvent, Alert, Appointment, CaregiverAccess, CarePlan, CareTask, Document, MedicationDose, MonitoringRule, NurseReleaseRequest, Observation, Patient, Provider, Referral, User

DAY = timedelta(days=1)


def _adherence(doses: list[Any]) -> int | None:
    t = now()
    past = [d for d in doses if d.scheduled_at <= t and d.status not in ("CANCELLED", "PENDING")]
    return round(len([d for d in past if d.status == "TAKEN"]) / len(past) * 100) if past else None


def name_only(u: User | None) -> dict[str, Any] | None:
    return {"name": u.name} if u else None


def patient_dict(p: Patient) -> dict[str, Any]:
    d = p.to_dict()
    d.update(user=p.user.lite(), doctor=p.doctor.lite(), nurse=p.nurse.lite() if p.nurse else None)
    return d


def patient_name(p: Patient) -> dict[str, Any]:
    return {"user": {"name": p.user.name}}


def safety_findings(plan: CarePlan) -> list[dict[str, Any]]:
    """Deterministic prescribing-safety review of a plan against the patient's allergies, comorbidities and active medicines."""
    from app.agents.safety_rules import check_plan

    items = [{**i.to_dict(), "details": parse_json(i.details, {})} for i in plan.items]
    with session_scope() as s:
        p = s.get(Patient, plan.patient_id)
        if p is None:
            return []
        active = s.scalars(select(CarePlan).where(CarePlan.patient_id == plan.patient_id, CarePlan.status == "ACTIVE", CarePlan.id != plan.id)).all()
        current = [
            (parse_json(i.details, {}).get("name") or i.title) for a in active for i in a.items if i.included and i.category == "MEDICATION" and i.action != "DISCONTINUE"
        ]
        allergies, comorbidities = p.allergies, p.comorbidities
    return [f.to_dict() for f in check_plan(items, allergies=allergies, comorbidities=comorbidities, current_meds=current)]


def plan_dict(plan: CarePlan) -> dict[str, Any]:
    d = plan.to_dict()
    d["items"] = [{**i.to_dict(), "details": parse_json(i.details, {})} for i in plan.items]
    if plan.status == "DRAFT":
        d["safety"] = safety_findings(plan)
    return d


def appt_dict(a: Appointment) -> dict[str, Any]:
    return {**a.to_dict(), "provider": a.provider.to_dict() if a.provider else None}


def referral_dict(r: Referral, appointments: list[Appointment]) -> dict[str, Any]:
    return {**r.to_dict(), "timeline": parse_json(r.timeline, []), "provider": r.provider.to_dict() if r.provider else None, "appointments": [a.to_dict() for a in appointments]}


def alert_dict(a: Alert, patients: dict[str, Patient] | None = None) -> dict[str, Any]:
    d = {**a.to_dict(), "history": parse_json(a.history, []), "assignedTo": {"name": a.assigned_to.name, "role": a.assigned_to.role} if a.assigned_to else None}
    if patients is not None and a.patient_id in patients:
        d["patient"] = patient_name(patients[a.patient_id])
    return d


def doc_dict(d: Document, *, strip_image: bool = True) -> dict[str, Any]:
    out = {**d.to_dict(), "data": parse_json(d.data, None), "createdBy": name_only(d.created_by)}
    if strip_image and d.type == "SOURCE_NOTE" and isinstance(out["data"], dict):
        out["data"].pop("image", None)  # source images can be megabytes — fetched on demand
    return out


def _patients_by_id(s: Session, ids: set[str]) -> dict[str, Patient]:
    return {p.id: p for p in s.scalars(select(Patient).where(Patient.id.in_(ids))).unique()} if ids else {}


def release_requests(s: Session, *conditions: Any) -> list[dict[str, Any]]:
    """Release requests with nurse names and the attached handoff summary (clinicians only)."""
    reqs = list(s.scalars(select(NurseReleaseRequest).where(*conditions).order_by(NurseReleaseRequest.created_at.desc()).limit(20)))
    user_ids = {x for r in reqs for x in (r.from_nurse_id, r.to_nurse_id, r.suggested_nurse_id, r.decided_by_id) if x}
    users = {u.id: u.name for u in s.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    doc_ids = {r.handoff_document_id for r in reqs if r.handoff_document_id}
    docs = {d.id: d for d in s.scalars(select(Document).where(Document.id.in_(doc_ids))).unique()} if doc_ids else {}
    patients = _patients_by_id(s, {r.patient_id for r in reqs})
    out = []
    for r in reqs:
        doc = docs.get(r.handoff_document_id or "")
        p = patients.get(r.patient_id)
        out.append(
            {
                **r.to_dict(),
                "patient": {"id": p.id, "user": {"name": p.user.name}} if p else None,
                "fromNurseName": users.get(r.from_nurse_id),
                "toNurseName": users.get(r.to_nurse_id or ""),
                "suggestedNurseName": users.get(r.suggested_nurse_id or ""),
                "decidedByName": users.get(r.decided_by_id or ""),
                "handoff": {"id": doc.id, "title": doc.title, "content": doc.content, "engine": doc.engine, "createdAt": doc.to_dict()["createdAt"]} if doc else None,
            }
        )
    return out


def patient_record(patient_id: str, user: SessionUser) -> dict[str, Any]:
    clinician = user.role in ("DOCTOR", "NURSE")
    partner = user.role in PARTNER_ROLES
    t = now()
    provider = provider_for(user) if partner else None
    with session_scope() as s:
        patient = s.get(Patient, patient_id)
        if patient is None:
            raise HTTPException(404, "Patient not found")
        plans: list[CarePlan] = []
        tasks: list[CareTask] = []
        doses: list[MedicationDose] = []
        observations: list[Observation] = []
        all_doses: list[MedicationDose] = []
        if not partner:
            q = select(CarePlan).where(CarePlan.patient_id == patient_id)
            q = q.where(CarePlan.status == "ACTIVE") if user.role in ("PATIENT", "CAREGIVER") else q.where(CarePlan.status != "REJECTED")
            plans = list(s.scalars(q.order_by(CarePlan.created_at.desc())))
            tasks = list(s.scalars(select(CareTask).where(CareTask.patient_id == patient_id).order_by(CareTask.due_date)))
            doses = list(s.scalars(select(MedicationDose).where(MedicationDose.patient_id == patient_id, MedicationDose.scheduled_at >= t - 7 * DAY, MedicationDose.scheduled_at <= t + 7 * DAY).order_by(MedicationDose.scheduled_at)))
            observations = list(s.scalars(select(Observation).where(Observation.patient_id == patient_id).order_by(Observation.recorded_at.desc()).limit(60)).unique())
            all_doses = list(s.scalars(select(MedicationDose).where(MedicationDose.patient_id == patient_id)))
        aq = select(Appointment).where(Appointment.patient_id == patient_id)
        rq = select(Referral).where(Referral.patient_id == patient_id)
        if provider:
            aq, rq = aq.where(Appointment.provider_id == provider.id), rq.where(Referral.provider_id == provider.id)
        appointments = list(s.scalars(aq.order_by(Appointment.starts_at)).unique())
        refs = list(s.scalars(rq.order_by(Referral.created_at.desc())).unique())
        ref_appts = list(s.scalars(select(Appointment).where(Appointment.referral_id.in_([r.id for r in refs])).order_by(Appointment.starts_at)).unique()) if refs else []
        rules = list(s.scalars(select(MonitoringRule).where(MonitoringRule.patient_id == patient_id, MonitoringRule.active.is_(True)).order_by(MonitoringRule.created_at))) if clinician else []
        alerts = list(s.scalars(select(Alert).where(Alert.patient_id == patient_id).order_by(Alert.created_at.desc())).unique()) if clinician else []
        dq = select(Document).where(Document.patient_id == patient_id)
        if user.role in ("PATIENT", "CAREGIVER"):
            dq = dq.where(Document.visible_to_patient.is_(True))
        if provider:
            dq = dq.where(or_(Document.shared_with_provider_id == provider.id, Document.type == "LAB_REPORT"))
        documents = list(s.scalars(dq.order_by(Document.created_at.desc())).unique())
        events = list(s.scalars(select(AgentEvent).where(AgentEvent.patient_id == patient_id).order_by(AgentEvent.created_at.desc()).limit(120))) if clinician else []
        releases = release_requests(s, NurseReleaseRequest.patient_id == patient_id) if clinician else []
        return {
            "patient": patient_dict(patient),
            "viewer": {"role": user.role, "id": user.id},
            "plans": [plan_dict(p) for p in plans],
            "tasks": [{**x.to_dict(), "meta": parse_json(x.meta, {})} for x in tasks],
            "doses": [d.to_dict() for d in doses],
            "appointments": [appt_dict(a) for a in appointments],
            "referrals": [referral_dict(r, [a for a in ref_appts if a.referral_id == r.id]) for r in refs],
            "observations": [{**o.to_dict(), "recordedBy": {"name": o.recorded_by.name, "role": o.recorded_by.role} if o.recorded_by else None} for o in observations],
            "rules": [r.to_dict() for r in rules],
            "alerts": [alert_dict(a) for a in alerts],
            "documents": [doc_dict(d) for d in documents],
            "events": [e.to_dict() for e in events],
            "releaseRequests": releases,
            "adherence": _adherence([d for d in all_doses if d.scheduled_at >= t - 7 * DAY]),
            "overallAdherence": _adherence(all_doses),
        }


def patient_summaries(s: Session, *conditions: Any) -> list[dict[str, Any]]:
    patients = list(s.scalars(select(Patient).where(*conditions).order_by(Patient.created_at)).unique())
    ids = [p.id for p in patients]
    if not ids:
        return []
    t = now()
    pending_release = set(s.scalars(select(NurseReleaseRequest.patient_id).where(NurseReleaseRequest.patient_id.in_(ids), NurseReleaseRequest.status.in_(["PENDING", "AWAITING_NURSE"]))))
    alerts = list(s.execute(select(Alert.patient_id, Alert.severity).where(Alert.patient_id.in_(ids), Alert.status != "RESOLVED")))
    doses = list(s.scalars(select(MedicationDose).where(MedicationDose.patient_id.in_(ids), MedicationDose.scheduled_at >= t - 7 * DAY, MedicationDose.scheduled_at <= t)))
    appts = list(s.execute(select(Appointment.patient_id, Appointment.title, Appointment.starts_at).where(Appointment.patient_id.in_(ids), Appointment.starts_at >= t, Appointment.status.in_(["BOOKED", "TENTATIVE"])).order_by(Appointment.starts_at)))
    drafts = list(s.execute(select(CarePlan.patient_id, CarePlan.kind).where(CarePlan.patient_id.in_(ids), CarePlan.status == "DRAFT")))
    reviews = list(s.scalars(select(Document.patient_id).where(Document.patient_id.in_(ids), Document.review_status == "PENDING_REVIEW")))
    vitals = list(s.scalars(select(Observation).where(Observation.patient_id.in_(ids), Observation.type.in_(["TEMPERATURE", "BP", "HEART_RATE", "SPO2"])).order_by(Observation.recorded_at.desc()).limit(200)).unique())
    from app.core.util import iso

    out = []
    for p in patients:
        nxt = next((a for a in appts if a[0] == p.id), None)
        draft = next((d for d in drafts if d[0] == p.id), None)
        out.append(
            {
                **patient_dict(p),
                "openAlerts": len([a for a in alerts if a[0] == p.id]),
                "criticalAlerts": len([a for a in alerts if a[0] == p.id and a[1] in ("CRITICAL", "HIGH")]),
                "adherence": _adherence([d for d in doses if d.patient_id == p.id]),
                "nextAppointment": {"patientId": p.id, "title": nxt[1], "startsAt": iso(nxt[2])} if nxt else None,
                "draftPlan": {"patientId": p.id, "kind": draft[1]} if draft else None,
                "pendingReviews": len([r for r in reviews if r == p.id]),
                "pendingRelease": p.id in pending_release,
                "vitals": [o.to_dict() for o in vitals if o.patient_id == p.id][:12],
            }
        )
    return out


def doctor_overview(user: SessionUser) -> dict[str, Any]:
    with session_scope() as s:
        patients = patient_summaries(s, Patient.doctor_id == user.id)
        ids = [p["id"] for p in patients]
        me = s.scalars(select(Provider).where(Provider.user_id == user.id)).first()
        incoming: list[dict[str, Any]] = []
        if me:
            inc = list(s.scalars(select(Referral).where(Referral.provider_id == me.id, Referral.status == "SENT").order_by(Referral.updated_at.desc())).unique())
            pmap = _patients_by_id(s, {r.patient_id for r in inc})
            incoming = [{**r.to_dict(), "patient": {**pmap[r.patient_id].to_dict(), "user": {"name": pmap[r.patient_id].user.name}, "doctor": {"name": pmap[r.patient_id].doctor.name}}} for r in inc]
        pmap = _patients_by_id(s, set(ids))
        alerts = list(s.scalars(select(Alert).where(Alert.patient_id.in_(ids), Alert.status != "RESOLVED").order_by(Alert.escalation_level.desc(), Alert.created_at.desc())).unique()) if ids else []
        reviews = list(s.scalars(select(Document).where(Document.patient_id.in_(ids), Document.review_status == "PENDING_REVIEW").order_by(Document.created_at.desc())).unique()) if ids else []
        refs = list(s.scalars(select(Referral).where(Referral.patient_id.in_(ids)).order_by(Referral.updated_at.desc())).unique()) if ids else []
        ref_appts = list(s.execute(select(Appointment.referral_id, Appointment.status).where(Appointment.referral_id.in_([r.id for r in refs])))) if refs else []
        events = list(s.scalars(select(AgentEvent).where(AgentEvent.patient_id.in_(ids)).order_by(AgentEvent.created_at.desc()).limit(40))) if ids else []
        drafts = list(s.scalars(select(CarePlan).where(CarePlan.patient_id.in_(ids), CarePlan.status == "DRAFT"))) if ids else []
        return {
            "patients": patients,
            "alerts": [alert_dict(a, pmap) for a in alerts],
            "reviews": [{**doc_dict(d), "patient": patient_name(pmap[d.patient_id])} for d in reviews],
            "referrals": [
                {**r.to_dict(), "timeline": parse_json(r.timeline, []), "provider": r.provider.to_dict() if r.provider else None, "patient": patient_name(pmap[r.patient_id]), "appointments": [{"status": st} for rid, st in ref_appts if rid == r.id]}
                for r in refs
            ],
            "incoming": incoming,
            "releases": release_requests(s, NurseReleaseRequest.patient_id.in_(ids), NurseReleaseRequest.status == "PENDING") if ids else [],
            "events": [{**e.to_dict(), "patient": patient_name(pmap[e.patient_id]) if e.patient_id in pmap else None} for e in events],
            "drafts": [{**{k: v for k, v in plan_dict(d).items() if k != "items"}, "patient": patient_name(pmap[d.patient_id])} for d in drafts],
        }


def nurse_overview(user: SessionUser) -> dict[str, Any]:
    with session_scope() as s:
        patients = patient_summaries(s, Patient.nurse_id == user.id)
        ids = [p["id"] for p in patients]
        pmap = _patients_by_id(s, set(ids))
        start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + DAY
        incoming = release_requests(s, NurseReleaseRequest.to_nurse_id == user.id, NurseReleaseRequest.status == "AWAITING_NURSE")
        if not ids:
            return {"patients": [], "alerts": [], "appointmentsToday": [], "dosesToday": [], "handoffs": [], "events": [], "incomingHandoffs": incoming}
        alerts = list(s.scalars(select(Alert).where(Alert.patient_id.in_(ids), Alert.status != "RESOLVED").order_by(Alert.created_at.desc())).unique())
        appts = list(s.scalars(select(Appointment).where(Appointment.patient_id.in_(ids), Appointment.starts_at >= start, Appointment.starts_at < end, Appointment.status != "CANCELLED").order_by(Appointment.starts_at)).unique())
        doses = list(s.scalars(select(MedicationDose).where(MedicationDose.patient_id.in_(ids), MedicationDose.scheduled_at >= start, MedicationDose.scheduled_at < end, MedicationDose.status != "CANCELLED").order_by(MedicationDose.scheduled_at)))
        handoffs = list(s.scalars(select(Document).where(Document.patient_id.in_(ids), Document.type == "NURSE_HANDOFF").order_by(Document.created_at.desc()).limit(12)).unique())
        events = list(s.scalars(select(AgentEvent).where(AgentEvent.patient_id.in_(ids)).order_by(AgentEvent.created_at.desc()).limit(30)))
        return {
            "patients": patients,
            "alerts": [alert_dict(a, pmap) for a in alerts],
            "appointmentsToday": [{**appt_dict(a), "patient": patient_name(pmap[a.patient_id])} for a in appts],
            "dosesToday": [{**d.to_dict(), "patient": patient_name(pmap[d.patient_id])} for d in doses],
            "handoffs": [{**doc_dict(d), "patient": patient_name(pmap[d.patient_id])} for d in handoffs],
            "events": [{**e.to_dict(), "patient": patient_name(pmap[e.patient_id]) if e.patient_id in pmap else None} for e in events],
            "incomingHandoffs": incoming,
        }


def patient_overview(user: SessionUser) -> dict[str, Any]:
    with session_scope() as s:
        if user.role == "CAREGIVER":  # read-only view of the patient who granted access
            pid = s.scalars(select(CaregiverAccess.patient_id).where(CaregiverAccess.caregiver_id == user.id, CaregiverAccess.status == "ACTIVE").order_by(CaregiverAccess.accepted_at.desc())).first()
        else:
            pid = s.scalars(select(Patient.id).where(Patient.user_id == user.id)).first()
    if not pid:
        raise HTTPException(404, "No patient record linked to this account")
    return patient_record(pid, user)


def provider_overview(user: SessionUser) -> dict[str, Any]:
    """Test panels for TEST appointments are attached by the API layer via the Test Center MCP server."""
    provider = provider_for(user)
    is_lab = provider.type == "TEST_CENTER"
    with session_scope() as s:
        refs = list(
            s.scalars(select(Referral).where(or_(Referral.provider_id == provider.id, Referral.declined_provider_ids.contains(provider.id))).order_by(Referral.updated_at.desc())).unique()
        )
        appts = list(s.scalars(select(Appointment).where(Appointment.provider_id == provider.id, Appointment.status != "CANCELLED").order_by(Appointment.starts_at)).unique())
        pmap = _patients_by_id(s, {r.patient_id for r in refs} | {a.patient_id for a in appts})
        task_ids = {a.task_id for a in appts if a.task_id}
        task_meta = {t.id: parse_json(t.meta, {}) for t in s.scalars(select(CareTask).where(CareTask.id.in_(task_ids)))} if task_ids else {}
        documents = list(s.scalars(select(Document).where(Document.shared_with_provider_id == provider.id).order_by(Document.created_at.desc())).unique())

        def appt_view(a: Appointment) -> dict[str, Any]:
            meta = task_meta.get(a.task_id or "", {})
            p = pmap[a.patient_id]
            return {
                **a.to_dict(),
                "patient": {**p.to_dict(), "user": p.user.lite()},
                "task": {"meta": meta} if a.task_id else None,
                "panelQuery": str(meta.get("testName") or a.title) if a.kind == "TEST" else None,
            }

        return {
            "provider": provider.to_dict(),
            "isLab": is_lab,
            "referrals": [
                {
                    **r.to_dict(),
                    "timeline": parse_json(r.timeline, []),
                    "declinedByMe": r.provider_id != provider.id,
                    "patient": {**pmap[r.patient_id].to_dict(), "user": pmap[r.patient_id].user.lite(), "doctor": pmap[r.patient_id].doctor.lite()},
                    "appointments": [a.to_dict() for a in appts if a.referral_id == r.id],
                }
                for r in refs
            ],
            "appointments": [appt_view(a) for a in appts],
            "documents": [doc_dict(d) for d in documents],
        }

