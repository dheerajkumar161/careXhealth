"""Alerts, appointments, lab reports, doses, documents (+ PDF), tests."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.agents.orchestrator import orchestrator
from app.auth.deps import PARTNER_ROLES, provider_for, require_department, require_patient_access, require_role
from app.auth.security import SessionUser
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.util import now, parse_json
from app.documents.renderer import render_html, render_pdf
from app.models import Alert, Appointment, CareTask, Document, MedicationDose, Patient, Provider
from app.schemas.api import AlertAction, AppointmentAction, DoseAction, LabReportCreate, LabResult
from app.services.audit import audit
from app.services.records import doc_dict, patient_dict

router = APIRouter(tags=["clinical"])


# ── alerts ──


@router.patch("/api/alerts/{alert_id}")
async def alert_action(alert_id: str, body: AlertAction, user: SessionUser = Depends(require_role("NURSE", "DOCTOR"))) -> dict:
    with session_scope() as s:
        alert = s.get(Alert, alert_id)
        found = (alert.patient_id, alert.status) if alert else None
    if not found:
        raise HTTPException(404, "Alert not found")
    require_patient_access(user, found[0])
    if found[1] == "RESOLVED":
        raise HTTPException(409, "Alert is already resolved")
    audit(f"ALERT_{body.action}", user, entity_type="Alert", entity_id=alert_id, patient_id=found[0])
    note = (body.note or "").strip()
    if body.action == "RESOLVE" and not note:
        raise HTTPException(400, "Please document how the alert was resolved")
    m = orchestrator.monitoring
    if body.action == "ACKNOWLEDGE":
        result = await m.invoke("acknowledge_alert", alert_id=alert_id, user_id=user.id, user_name=user.name)
    elif body.action == "RESOLVE":
        result = await m.invoke("resolve_alert", alert_id=alert_id, user_name=user.name, resolution=note)
    else:
        result = await m.invoke("escalate_alert", alert_id=alert_id, reason=note or f"Manually escalated by {user.name}", by=user.name)
    return {"alert": result}


# ── appointments & lab results ──


@router.patch("/api/appointments/{appointment_id}")
async def appointment_action(appointment_id: str, body: AppointmentAction, user: SessionUser = Depends(require_role("PROVIDER", "TEST_CENTER", "NURSE", "DOCTOR"))) -> dict:
    """Provider (or clinician) marks an appointment attended / missed → Execution agent tracks & reschedules."""
    with session_scope() as s:
        appt = s.get(Appointment, appointment_id)
        if appt is None:
            raise HTTPException(404, "Appointment not found")
        provider_id, patient_id, status, starts_at = appt.provider_id, appt.patient_id, appt.status, appt.starts_at
        owns = user.role == "DOCTOR" and s.scalars(select(Provider.id).where(Provider.id == provider_id, Provider.user_id == user.id)).first() is not None
    if user.role in PARTNER_ROLES:
        if provider_id != provider_for(user).id:
            raise HTTPException(403, "This appointment belongs to another provider")
    elif not owns:
        require_patient_access(user, patient_id)
    if status != "BOOKED":
        raise HTTPException(409, f"Appointment is {status.lower()}")
    if not get_settings().demo_mode and starts_at.timestamp() > now().timestamp() + 12 * 3600:
        raise HTTPException(409, "You can only update appointments on or after their scheduled day")
    if body.action == "COMPLETE":
        result = await orchestrator.execution.invoke("complete_appointment", appointment_id=appointment_id, notes=body.notes)
    else:
        result = await orchestrator.execution.invoke("miss_appointment", appointment_id=appointment_id, reason=body.notes or "Patient did not attend")
    return {"appointment": result}


async def _upload_lab(appointment_id: str, body: LabResult, user: SessionUser) -> dict:
    provider = provider_for(user)
    if provider.type != "TEST_CENTER":
        raise HTTPException(403, "Only test centers can upload reports")
    with session_scope() as s:
        appt = s.get(Appointment, appointment_id)
        if appt is None or appt.provider_id != provider.id or appt.kind != "TEST":
            raise HTTPException(404, "Test booking not found")
        if appt.status == "COMPLETED" and s.scalars(select(Document.id).where(Document.task_id == (appt.task_id or "-"), Document.type == "LAB_REPORT")).first():
            raise HTTPException(409, "A report has already been uploaded for this test")
    if not body.values and not (body.findings or "").strip():
        raise HTTPException(400, "Enter at least one result or a findings note")
    doc = await orchestrator.communication.invoke("process_lab_report", appointment_id=appointment_id, uploaded_by_id=user.id, values=body.values, findings=body.findings)
    return {"document": doc}


@router.post("/api/appointments/{appointment_id}/result")
async def upload_result(appointment_id: str, body: LabResult, user: SessionUser = Depends(require_role("TEST_CENTER"))) -> dict:
    """Test Center uploads a report → Communication & Documentation agent processes, stores and routes it."""
    return await _upload_lab(appointment_id, body, user)


@router.post("/api/lab-reports")
async def lab_report(body: LabReportCreate, user: SessionUser = Depends(require_department("Laboratory"))) -> dict:
    """Same as /api/appointments/{id}/result, for integrations that post the appointment id in the body (Laboratory department only)."""
    if user.role != "TEST_CENTER":
        raise HTTPException(403, "Only test centers can upload reports")
    return await _upload_lab(body.appointmentId, LabResult(values=body.values, findings=body.findings), user)


# ── doses ──


@router.patch("/api/doses/{dose_id}")
async def dose_action(dose_id: str, body: DoseAction, user: SessionUser = Depends(require_role("PATIENT", "NURSE"))) -> dict:
    """Patient (or nurse on their behalf) records a dose → Execution tracks it, Monitoring checks adherence."""
    with session_scope() as s:
        dose = s.get(MedicationDose, dose_id)
        found = (dose.patient_id, dose.status, dose.scheduled_at) if dose else None
    if not found:
        raise HTTPException(404, "Dose not found")
    require_patient_access(user, found[0])
    if found[1] != "PENDING":
        raise HTTPException(409, f"This dose is already {found[1].lower()}")
    if not get_settings().demo_mode and found[2].timestamp() > now().timestamp() + 2 * 3600:
        raise HTTPException(409, "This dose isn't due yet")
    updated = await orchestrator.execution.invoke("record_dose", dose_id=dose_id, status=body.status, note=body.note)
    if body.status == "SKIPPED":
        await orchestrator.monitoring.invoke("evaluate_adherence", patient_id=found[0])
    return {"dose": updated}


# ── documents ──


def _load_doc(document_id: str) -> Document:
    with session_scope() as s:
        doc = s.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@router.patch("/api/documents/{document_id}")
async def review_document(document_id: str, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Doctor marks a lab report as reviewed (decisions are then entered as care-plan amendments)."""
    doc = _load_doc(document_id)
    require_patient_access(user, doc.patient_id)
    if doc.review_status != "PENDING_REVIEW":
        raise HTTPException(409, "Document is not awaiting review")
    with session_scope() as s:
        d = s.get(Document, document_id)
        assert d is not None
        d.review_status, d.reviewed_at = "REVIEWED", now()
        d.content = d.content.replace("Status: **Pending doctor review**", f"Status: **Reviewed by {user.name}**")
        s.flush()
        updated = doc_dict(d)
    await orchestrator.services.call("ehr", "create_audit_event", agent="HUMAN", action=f"{doc.title} reviewed by {user.name}", patient_id=doc.patient_id, level="SUCCESS")
    await orchestrator.services.call("notification", "notify_patient", patient_id=doc.patient_id, type="DOCUMENT", title=f"{doc.title} reviewed", body=f"{user.name} has reviewed your report.")
    return {"document": updated}


@router.get("/api/documents/{document_id}/image")
def source_image(document_id: str, user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    """Original image behind a SOURCE_NOTE (clinicians only) — kept out of dashboard payloads because of its size."""
    doc = _load_doc(document_id)
    if doc.type != "SOURCE_NOTE":
        raise HTTPException(404, "Image not found")
    require_patient_access(user, doc.patient_id)
    data = parse_json(doc.data, {})
    if not data.get("image"):
        raise HTTPException(404, "Image not found")
    audit("DOCUMENT_IMAGE_VIEW", user, entity_type="Document", entity_id=document_id, patient_id=doc.patient_id)
    return {"name": data.get("name"), "dataUrl": data["image"]}


@router.get("/api/documents/{document_id}/pdf")
def document_pdf(document_id: str, user: SessionUser = Depends(require_role("DOCTOR", "NURSE", "PATIENT", "CAREGIVER", "PROVIDER", "TEST_CENTER"))) -> Response:
    """Jinja2 → HTML → PDF rendering of any document the caller may read."""
    doc = _load_doc(document_id)
    with session_scope() as s:
        my_provider = s.scalars(select(Provider.id).where(Provider.user_id == user.id)).first()
    shared_with_me = my_provider is not None and doc.shared_with_provider_id == my_provider
    # A receiving specialist reads the referral package shared with them (they have no other access to the record)
    if not shared_with_me:
        require_patient_access(user, doc.patient_id)
        if user.role in ("PATIENT", "CAREGIVER") and not doc.visible_to_patient:
            raise HTTPException(403, "This document is not shared with you")
        if user.role in PARTNER_ROLES and doc.type != "LAB_REPORT":
            raise HTTPException(403, "This document is not shared with you")
    with session_scope() as s:
        patient = patient_dict(s.get(Patient, doc.patient_id))  # type: ignore[arg-type]
    audit("DOCUMENT_DOWNLOAD", user, entity_type="Document", entity_id=document_id, patient_id=doc.patient_id)
    pdf = render_pdf(render_html(doc_dict(doc, strip_image=True), patient))
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{doc.title}.pdf")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


# ── tests ──


@router.get("/api/tests")
def tests(user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    """Every investigation ordered for the doctor's (or nurse's) patients, with booking and report status."""
    with session_scope() as s:
        cond = Patient.doctor_id == user.id if user.role == "DOCTOR" else Patient.nurse_id == user.id
        patients = {p.id: p for p in s.scalars(select(Patient).where(cond)).unique()}
        rows = list(s.scalars(select(CareTask).where(CareTask.type == "INVESTIGATION", CareTask.patient_id.in_(list(patients))).order_by(CareTask.due_date))) if patients else []
        ids = [t.id for t in rows]
        appts = list(s.scalars(select(Appointment).where(Appointment.task_id.in_(ids)).order_by(Appointment.starts_at.desc())).unique()) if ids else []
        docs = list(s.scalars(select(Document).where(Document.task_id.in_(ids), Document.type == "LAB_REPORT").order_by(Document.created_at.desc())).unique()) if ids else []
        out = []
        for t in rows:
            p = patients[t.patient_id]
            out.append(
                {
                    **t.to_dict(),
                    "meta": parse_json(t.meta, {}),
                    "patient": {"id": p.id, "mrn": p.mrn, "user": {"name": p.user.name}},
                    "appointments": [{**a.to_dict(), "provider": {"name": a.provider.name, "organization": a.provider.organization}} for a in appts if a.task_id == t.id],
                    "documents": [{**d.to_dict(), "data": parse_json(d.data, None)} for d in docs if d.task_id == t.id],
                }
            )
    return {"tests": out}
