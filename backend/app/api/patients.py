"""/api/patients — registration, records, discharge notes, observations, chat, intelligence, nurse handover."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select

from app.agents.base import AgentError
from app.agents.orchestrator import orchestrator
from app.auth.deps import require_patient_access, require_role, require_user
from app.auth.security import SessionUser, hash_password
from app.core.constants import OBSERVATION_UNITS
from app.core.db import session_scope
from app.core.i18n import normalize_language
from app.core.util import now, parse_dt, parse_json
from app.services import risk
from app.services.export import fhir_bundle
from app.services.audit import audit
from app.models import ChatMessage, Patient, User
from app.repositories import care_plans, monitoring
from app.schemas.api import CarePlanCreate, ChatIn, IntelligenceRequest, NurseAssign, ObservationCreate, PatientCreate, ReleaseRequestIn
from app.services.records import patient_record, plan_dict

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("")
def list_patients(user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    with session_scope() as s:
        cond = Patient.doctor_id == user.id if user.role == "DOCTOR" else Patient.nurse_id == user.id
        rows = list(s.scalars(select(Patient).where(cond).order_by(Patient.risk_score.desc(), Patient.created_at.desc())).unique())
        patients = [{**p.to_dict(), "riskFactors": parse_json(p.risk_factors, []), "user": {"name": p.user.name, "email": p.user.email}} for p in rows]
        nurses = [{"id": n.id, "name": n.name, "title": n.title} for n in s.scalars(select(User).where(User.role == "NURSE"))] if user.role == "DOCTOR" else []
    return {"patients": patients, "nurses": nurses}


@router.post("")
async def register_patient(body: PatientCreate, doctor: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Doctor registers a patient (creates their portal login) and assigns a nurse."""
    email = body.email.lower().strip()
    with session_scope() as s:
        if s.scalars(select(User).where(User.email == email)).first():
            raise HTTPException(409, "An account with this email already exists")
        if body.nurseId:
            nurse = s.get(User, body.nurseId)
            if nurse is None or nurse.role != "NURSE":
                raise HTTPException(400, "Selected nurse is invalid")
        count = s.scalar(select(func.count()).select_from(Patient)) or 0
        u = User(email=email, name=body.name, phone=body.phone, role="PATIENT", language=normalize_language(body.language), password_hash=hash_password(body.password))
        s.add(u)
        s.flush()
        p = Patient(
            user_id=u.id, mrn=f"CB-{250000 + count + 1}", date_of_birth=parse_dt(body.dateOfBirth), gender=body.gender, diagnosis=body.diagnosis,
            procedure=body.procedure or None, allergies=body.allergies or None, comorbidities=body.comorbidities or None,
            admission_date=parse_dt(body.admissionDate) if body.admissionDate else now(), doctor_id=doctor.id, nurse_id=body.nurseId or None,
        )  # fmt: skip
        s.add(p)
        s.flush()
        patient = p.to_dict()
    await orchestrator.services.call("ehr", "create_audit_event", agent="HUMAN", action=f"Patient registered by {doctor.name}", patient_id=patient["id"], detail=body.diagnosis)
    return {"patient": patient}


@router.get("/{patient_id}")
def get_patient(patient_id: str, user: SessionUser = Depends(require_user)) -> dict:
    require_patient_access(user, patient_id)
    if user.role != "PATIENT":
        audit("RECORD_VIEW", user, entity_type="Patient", entity_id=patient_id, patient_id=patient_id)
    return patient_record(patient_id, user)


@router.get("/{patient_id}/export")
def export_record(patient_id: str, format: str = "json", user: SessionUser = Depends(require_role("PATIENT", "CAREGIVER", "DOCTOR", "NURSE"))) -> Response:  # noqa: A002
    """Download the record the caller is allowed to see (plain JSON, or a FHIR R4-style bundle). Audited."""
    require_patient_access(user, patient_id)
    rec = patient_record(patient_id, user)
    for d in rec["documents"]:  # source images are huge and clinician-only
        if isinstance(d.get("data"), dict):
            d["data"].pop("image", None)
    body = fhir_bundle(rec) if format == "fhir" else rec
    audit("RECORD_EXPORT", user, entity_type="Patient", entity_id=patient_id, patient_id=patient_id, detail=format)
    name = f"carexhealth-{rec['patient']['mrn']}-{'fhir' if format == 'fhir' else 'record'}.json"
    return Response(json.dumps(body, indent=2, default=str), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/{patient_id}/care-plans")
async def draft_plan(patient_id: str, body: CarePlanCreate, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Doctor submits discharge instructions (typed and/or photos/scans) or a decision → Care Planning agent drafts a plan."""
    require_patient_access(user, patient_id)
    attachments = [a.model_dump() for a in body.attachments]
    if not attachments and len(body.instructions.strip()) < 10:
        raise HTTPException(400, "Write the instructions in a little more detail, or attach an image of the note")
    try:
        if body.kind == "AMENDMENT":
            result = await orchestrator.planning.invoke("draft_amendment", patient_id=patient_id, doctor_id=user.id, decision=body.instructions, attachments=attachments)
        else:
            result = await orchestrator.planning.invoke("draft_care_plan", patient_id=patient_id, doctor_id=user.id, instructions=body.instructions, attachments=attachments)
    except ValueError as e:
        # Image-reading problems are actionable by the doctor — surface them as a 422, not a server error
        if attachments and ("image" in str(e).lower() or "vision" in str(e).lower()):
            raise HTTPException(422, str(e)) from e
        raise
    plan = care_plans.get(result["planId"])
    return {"plan": plan_dict(plan)}  # type: ignore[arg-type]


@router.post("/{patient_id}/observations")
async def record_observation(patient_id: str, body: ObservationCreate, user: SessionUser = Depends(require_role("PATIENT", "NURSE", "DOCTOR"))) -> dict:
    """Patients and nurses record vitals / symptoms → Monitoring agent evaluates against approved rules."""
    require_patient_access(user, patient_id)
    if body.type == "NURSE_NOTE" and user.role == "PATIENT":
        raise HTTPException(403, "Only clinicians can add nurse notes")
    if body.type in ("SYMPTOM", "NURSE_NOTE"):
        if not (body.text or "").strip():
            raise HTTPException(400, "Please enter a value")
    elif body.value is None:
        raise HTTPException(400, "Please enter a value")
    if body.type == "BP" and body.value2 is None:
        raise HTTPException(400, "Enter both systolic and diastolic values")
    obs = monitoring.create_observation(
        patient_id=patient_id, type=body.type, value=body.value, value2=body.value2, text=body.text, unit=OBSERVATION_UNITS.get(body.type),
        source="PATIENT" if user.role == "PATIENT" else "NURSE", recorded_by_id=user.id,
    )  # fmt: skip
    alerts = await orchestrator.monitoring.invoke("evaluate_observation", observation_id=obs.id)
    risk.refresh(patient_id)
    return {"observation": obs.to_dict(), "alerts": alerts}


@router.get("/{patient_id}/chat")
def chat_history(patient_id: str, user: SessionUser = Depends(require_role("PATIENT", "DOCTOR", "NURSE"))) -> dict:
    require_patient_access(user, patient_id)
    with session_scope() as s:
        msgs = s.scalars(select(ChatMessage).where(ChatMessage.patient_id == patient_id).order_by(ChatMessage.created_at).limit(100))
        return {"messages": [m.to_dict() for m in msgs]}


@router.post("/{patient_id}/chat")
async def chat(patient_id: str, body: ChatIn, user: SessionUser = Depends(require_role("PATIENT"))) -> dict:
    """Patient asks the Communication agent a question (answers are grounded in the approved plan only)."""
    require_patient_access(user, patient_id)
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message is empty")
    return {"reply": await orchestrator.communication.invoke("patient_chat", patient_id=patient_id, message=message)}


@router.post("/{patient_id}/intelligence")
async def intelligence(patient_id: str, body: IntelligenceRequest, user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    """Clinical Intelligence agent: nurse handoff or longitudinal recovery summary."""
    require_patient_access(user, patient_id)
    skill = "nurse_handoff" if body.kind == "HANDOFF" else "recovery_summary"
    return {"document": await orchestrator.intelligence.invoke(skill, patient_id=patient_id, author_id=user.id)}


@router.post("/{patient_id}/nurse-release")
async def request_release(patient_id: str, body: ReleaseRequestIn, user: SessionUser = Depends(require_role("NURSE"))) -> dict:
    """Assigned nurse asks the treating doctor to be released from this patient (handoff is generated automatically)."""
    require_patient_access(user, patient_id)
    try:
        req = await orchestrator.intelligence.invoke("request_release", patient_id=patient_id, nurse_id=user.id, reason=body.reason, suggested_nurse_id=body.suggestedNurseId or None)
    except AgentError as e:
        raise HTTPException(e.status, str(e)) from e
    return {"request": req}


@router.post("/{patient_id}/nurse")
async def assign_nurse(patient_id: str, body: NurseAssign, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Treating doctor assigns a nurse to a patient who has none. Nurses leave only via a release request."""
    require_patient_access(user, patient_id)
    try:
        await orchestrator.intelligence.invoke("assign_nurse", patient_id=patient_id, doctor_id=user.id, to_nurse_id=body.nurseId, reason=body.reason.strip())
    except AgentError as e:
        raise HTTPException(e.status, str(e)) from e
    return {"ok": True}
